"""Hermes Core - the agent loop behind RAPIIN.

Pipeline per PRD section 12:
User message -> context -> intent -> planning -> tool selection ->
permission check -> approval gate -> execute -> verify -> natural response.
"""
from __future__ import annotations

import json

from ..approval import create_approval
from ..audit import record_audit
from ..config import settings
from ..permissions import PermissionEngine, check_path_allowed, resolve_path, sandbox_root
from ..tasks import update_task
from ..redaction import redact_text
from .prompts import SUPERVISOR_SYSTEM_PROMPT, USER_SYSTEM_PROMPT


class HermesCore:
    def __init__(self, provider):
        self.provider = provider

    # ------------------------------------------------------------------ user

    def _user_prompt_with_context(self, roots: list[str]) -> str:
        listing = "\n".join(f"- {root}" for root in roots)
        return (
            USER_SYSTEM_PROMPT
            + "\n\nLokasi kerja file Anda saat ini adalah:\n"
            + listing + "\n"
            + "- Gunakan path absolut dari salah satu folder tersebut saat memanggil tool.\n"
            + "- Pilih folder yang paling sesuai dengan permintaan user.\n"
            + "- Jangan mengakses path di luar daftar tersebut."
        )

    def run_user_conversation(
        self,
        conn,
        *,
        user_id: int,
        conversation_history: list[dict],
        task_id: int | None,
        device_id: int | None,
        permissions: PermissionEngine | None = None,
        on_delta=None,
    ) -> dict:
        permissions = permissions or PermissionEngine(role="USER")
        device = conn.execute("SELECT workspace_root, allowed_roots FROM devices WHERE id=? AND user_id=?", (device_id, user_id)).fetchone() if device_id else None
        roots = []
        if device and device["allowed_roots"]:
            try:
                roots = json.loads(device["allowed_roots"])
            except (TypeError, json.JSONDecodeError):
                roots = []
        if not roots:
            roots = [device["workspace_root"]] if device and device["workspace_root"] else ["workspace yang dikonfigurasi pada Desktop Agent"]
        system = {"role": "system", "content": self._user_prompt_with_context(roots)}
        history = [
            {"role": m["role"], "content": redact_text(m["content"])}
            for m in conversation_history
            if m["role"] in {"user", "assistant"} and m["content"]
        ]
        messages = [system] + history

        user_turns = [m["content"] for m in history if m["role"] == "user"]
        latest_user_text = user_turns[-1] if user_turns else ""
        context_text = user_turns[-2] if len(user_turns) > 1 else ""
        tools = self.provider.tools_schema() if tool_include_for_task(latest_user_text, context_text) else []
        final_answer = None
        tool_events: list[dict] = []

        for iteration in range(settings.ai_max_iterations):
            if task_id:
                row = conn.execute("SELECT cancel_requested FROM tasks WHERE id = ?", (task_id,)).fetchone()
                if row and row["cancel_requested"]:
                    return {"final_response": "Task dibatalkan sebelum perubahan berikutnya dijalankan.", "tool_events": tool_events, "cancelled": True}
            # Never hold a SQLite write transaction while waiting on an
            # external provider. Otherwise heartbeats and status endpoints can
            # exhaust the HTTP threadpool behind the same database lock.
            conn.commit()
            if on_delta and hasattr(self.provider, "chat_stream"):
                result = self.provider.chat_stream(messages, tools=tools, on_delta=on_delta)
            else:
                result = self.provider.chat(messages, tools=tools)
            if task_id and result.get("latency_ms") is not None:
                from ..metrics import record_metric
                record_metric(conn, "ai_response_latency_ms", result["latency_ms"], {"role": "user"})
            message = result["message"]
            # Keep the full assistant message including any tool_calls so the
            # model can correlate the following tool results correctly.
            assistant_msg = {"role": "assistant", "content": message.get("content")}
            if message.get("tool_calls"):
                assistant_msg["tool_calls"] = message["tool_calls"]
            messages.append(assistant_msg)

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                final_answer = message.get("content") or ""
                break

            for call in tool_calls:
                call_id = call.get("id") or f"call_{len(messages)}"
                name = call.get("function", {}).get("name", "")
                try:
                    raw_args = call.get("function", {}).get("arguments", "{}")
                    arguments = json.loads(raw_args) if raw_args else {}
                except json.JSONDecodeError:
                    arguments = {}

                approval_kind = permissions.action_approval_kind(name, count=_count_args(arguments))

                # Permission / approval gate
                if approval_kind == "SUPERVISOR":
                    tool_events.append(_pending_supervisor_approval(conn, user_id, task_id, name, arguments))
                    messages.append(
                        self.provider.tool_result_message(
                            call_id,
                            json.dumps({
                                "status": "WAITING_APPROVAL",
                                "message": "Operasi membutuhkan persetujuan supervisor dan belum dijalankan.",
                            }, ensure_ascii=False),
                            name=name,
                        )
                    )
                    continue

                if approval_kind == "USER":
                    tool_events.append(_pending_user_approval(conn, user_id, task_id, name, arguments))
                    messages.append(
                        self.provider.tool_result_message(
                            call_id,
                            json.dumps({
                                "status": "WAITING_APPROVAL",
                                "message": "Operasi memerlukan persetujuan Anda dan belum dijalankan.",
                            }, ensure_ascii=False),
                            name=name,
                        )
                    )
                    continue

                # Automatic / safe path
                try:
                    from ..ops_incidents import operations_frozen
                    if operations_frozen(conn):
                        raise ToolExecutionBlocked("Operations Center sedang dalam emergency pause. Tidak ada tool yang dijalankan.")
                    output = self._execute_tool(conn, user_id, task_id, device_id, name, arguments, permissions)
                    tool_events.append({"tool": name, "status": "OK", "result": output})
                    from ..redaction import redact_value
                    content = json.dumps(redact_value({"status": "OK", **output}), ensure_ascii=False)
                    if task_id:
                        total = output.get("file_count") or output.get("planned_count") or output.get("count")
                        processed = output.get("processed_count") or output.get("verified_count") or total
                        if isinstance(total, int):
                            update_task(conn, task_id, processed_count=int(processed or 0), total_count=total)
                except ToolExecutionBlocked as exc:
                    tool_events.append({"tool": name, "status": "BLOCKED", "error": str(exc)})
                    content = json.dumps({"status": "BLOCKED", "message": str(exc)}, ensure_ascii=False)
                except Exception as exc:
                    tool_events.append({"tool": name, "status": "ERROR", "error": str(exc)})
                    content = json.dumps({"status": "ERROR", "message": str(exc)}, ensure_ascii=False)

                messages.append(self.provider.tool_result_message(call_id, content, name=name))

            if task_id:
                update_task(conn, task_id, progress=min(99, iteration * 12))

        if not final_answer:
            final_answer = "Maaf, saya belum dapat menyelesaikan permintaan tersebut. Silakan coba lagi."

        return {"final_response": final_answer, "tool_events": tool_events}

    # ------------------------------------------------------------- supervisor

    def run_supervisor_question(
        self,
        messages: list[dict],
        monitoring_context: dict,
        max_tokens: int = 700,
    ) -> str:
        system_content = SUPERVISOR_SYSTEM_PROMPT + "\n\nData monitoring saat ini:\n" + json.dumps(
            monitoring_context, ensure_ascii=False, default=str
        )
        system = {"role": "system", "content": system_content}
        result = self.provider.chat([system] + messages, max_tokens=max_tokens)
        return result["message"].get("content") or ""

    # ----------------------------------------------------------------- tools

    # Tools that read files on the employee computer, plus folder creation.
    # When a registered device agent is online these run locally on that
    # computer (PRD section 8). They never fall back to the server filesystem:
    # that could mutate or inspect the wrong machine while pretending success
    # to the user.
    DEVICE_DELEGATED_TOOLS = {
        "filesystem_scanner", "metadata_extractor", "file_search",
        "duplicate_detector", "document_parser", "pdf_parser", "spreadsheet_parser",
        "verification", "file_classifier", "semantic_indexer", "semantic_search",
        "folder_organizer", "file_mkdir",
    }

    def _execute_tool(self, conn, user_id, task_id, device_id, name, arguments, permissions):
        from ..tools.registry import execute_tool

        # Device paths are meaningful on the employee computer, not on the
        # server. Every delegated local tool enforces the registered agent
        # workspace itself; server-side validation applies only to server tools.
        if name not in self.DEVICE_DELEGATED_TOOLS:
            _validate_tool_paths(arguments)

        # Try to delegate to the employee's device agent first.
        if name in self.DEVICE_DELEGATED_TOOLS:
            delegated = self._try_delegate_to_device(conn, user_id, task_id, device_id, name, arguments)
            if delegated is not None:
                return delegated
            raise ToolExecutionBlocked("Desktop Agent tidak tersedia atau tidak merespons. Task tidak dijalankan pada server.")

        return execute_tool(conn, user_id=user_id, task_id=task_id, device_id=device_id, name=name, arguments=arguments)

    def _try_delegate_to_device(self, conn, user_id, task_id, device_id, name, arguments):
        """Queue a job on an online device and wait briefly for its result.

        The current transaction is committed first so the desktop agent (a
        separate process) can see the job and write its result back. Returns
        the tool result on success, an error dict on agent failure, or None so
        the caller falls back to local execution after the wait budget.
        """
        import json
        import time

        from ..agent_jobs import WAIT_BUDGET_SECONDS, enqueue_job, get_job
        from ..database import connect

        if not device_id:
            return None
        device = conn.execute(
            "SELECT * FROM devices WHERE id = ? AND status = 'ONLINE'", (device_id,)
        ).fetchone()
        if not device:
            return None

        # Commit pending work so the job row is visible to the agent.
        try:
            conn.commit()
            job_id = enqueue_job(
                conn,
                task_id=task_id,
                device_id=device_id,
                user_id=user_id,
                kind=name,
                payload={"tool": name, "arguments": arguments},
            )
            conn.commit()
        except Exception:  # noqa: BLE001
            conn.rollback()
            return None

        # Poll through a separate read connection so the agent can write.
        poll_conn = connect()
        try:
            deadline = time.monotonic() + WAIT_BUDGET_SECONDS
            while time.monotonic() < deadline:
                time.sleep(1.0)
                try:
                    job = get_job(poll_conn, job_id)
                except Exception:  # noqa: BLE001
                    return None
                if not job:
                    return None
                if job["status"] == "SUCCEEDED":
                    result = json.loads(job["result_json"] or "{}")
                    if isinstance(result, dict) and result.get("tool_result") is not None:
                        return result["tool_result"]
                    return result
                if job["status"] == "FAILED":
                    return {
                        "status": "ERROR",
                        "message": job.get("error") or "Operasi pada perangkat gagal.",
                    }
                # CLAIMED/PENDING: keep waiting.
        finally:
            poll_conn.close()
        return None

    def audit_event(self, conn, *, actor, role, user_id, device_id, action, resource, result="SUCCESS", error=None):
        record_audit(
            conn,
            actor=actor,
            actor_role=role,
            user_id=user_id,
            device_id=device_id,
            action=action,
            resource=resource,
            result=result,
            error=error,
        )


class ToolExecutionBlocked(Exception):
    pass


def _count_args(arguments: dict) -> int:
    paths = arguments.get("paths") or arguments.get("files") or []
    if isinstance(paths, list):
        return len(paths)
    if isinstance(arguments.get("count"), int):
        return arguments["count"]
    return 1


def _validate_tool_paths(arguments: dict) -> None:
    root = sandbox_root()
    candidates: list[str] = []
    for key in ("path", "source", "destination", "target", "directory"):
        if arguments.get(key):
            candidates.append(str(arguments[key]))
    if isinstance(arguments.get("paths"), list):
        candidates.extend(str(p) for p in arguments["paths"])
    if isinstance(arguments.get("files"), list):
        candidates.extend(str(p) for p in arguments["files"])
    for raw in candidates:
        allowed, reason = check_path_allowed(root, raw)
        if not allowed:
            raise ToolExecutionBlocked(reason)


def _pending_user_approval(conn, user_id, task_id, name, arguments) -> dict:
    approval_id = create_approval(
        conn,
        task_id=task_id,
        user_id=user_id,
        requested_by="RAPIIN",
        kind="USER",
        action=_describe_action(name, arguments),
        scope=_scope_of(arguments),
        risk=_risk_of(name),
        tool_name=name,
        tool_args=arguments,
    )
    return {"tool": name, "status": "WAITING_USER_APPROVAL", "approval_id": approval_id}


def _pending_supervisor_approval(conn, user_id, task_id, name, arguments) -> dict:
    approval_id = create_approval(
        conn,
        task_id=task_id,
        user_id=user_id,
        requested_by="RAPIIN",
        kind="SUPERVISOR",
        action=_describe_action(name, arguments),
        scope=_scope_of(arguments),
        risk=_risk_of(name),
        tool_name=name,
        tool_args=arguments,
    )
    return {"tool": name, "status": "WAITING_SUPERVISOR_APPROVAL", "approval_id": approval_id}


def _target_paths(arguments: dict) -> list[str]:
    """Collect the actual file paths an action will touch, most specific first.

    `paths`/`files`/`moves` name the real files; a lone `source`/`path` may be
    a parent folder, so it is only a fallback.
    """
    for key in ("paths", "files"):
        value = arguments.get(key)
        if isinstance(value, list) and value:
            return [str(item) for item in value]
    moves = arguments.get("moves")
    if isinstance(moves, list) and moves:
        collected = []
        for move in moves:
            if isinstance(move, dict) and move.get("source"):
                collected.append(str(move["source"]))
            elif isinstance(move, str):
                collected.append(move)
        if collected:
            return collected
    for key in ("source", "path"):
        value = arguments.get(key)
        if value and isinstance(value, str):
            return [value]
    return []


def _short_path(path: str, keep: int = 2) -> str:
    """Shorten a path to its last segments so approval cards stay readable."""
    text = str(path)
    parts = [part for part in text.replace("\\", "/").split("/") if part]
    if len(parts) <= keep + 1:
        return text
    return "…/" + "/".join(parts[-keep:])


def _describe_action(name: str, arguments: dict) -> str:
    summary = {
        "file_move": "Memindahkan file",
        "file_copy": "Menyalin file",
        "file_rename": "Mengubah nama file",
        "file_delete": "Menghapus file",
        "file_mkdir": "Membuat folder",
        "file_write": "Membuat file",
        "file_edit": "Mengubah file",
        "batch_executor": "Operasi massal pada banyak file",
        "bulk_delete": "Menghapus banyak file sekaligus",
    }
    label = summary.get(name, name)
    targets = _target_paths(arguments)
    if not targets:
        return label
    destination = arguments.get("destination")
    show_destination = (
        isinstance(destination, str) and bool(destination)
        and name in {"file_move", "file_copy", "batch_executor"}
    )
    # Destructive actions always name the files: a count alone would hide
    # what is about to be permanently removed.
    if name in {"file_delete", "bulk_delete"}:
        shown = ", ".join(_short_path(path) for path in targets[:5])
        if len(targets) > 5:
            shown += f" +{len(targets) - 5} lainnya"
        return f"{label} ({shown})"
    if len(targets) == 1:
        text = f"{label} ({_short_path(targets[0])}"
        if show_destination:
            text += f" → {_short_path(destination)}"
        return text + ")"
    text = f"{label} ({len(targets)} file"
    if show_destination:
        text += f" → {_short_path(destination)}"
    return text + ")"


def _scope_of(arguments: dict) -> str | None:
    targets = _target_paths(arguments)
    if targets:
        return ", ".join(targets[:10])
    for key in ("directory", "destination"):
        value = arguments.get(key)
        if value:
            if isinstance(value, list):
                return ", ".join(str(v) for v in value[:10])
            return str(value)
    return None


def _risk_of(name: str) -> str:
    if name in {"file_delete", "bulk_delete"}:
        return "Penghapusan permanen"
    return "Perubahan file"


def tool_include_for_task(text: str, prior_user_text: str = "") -> bool:
    """Expose filesystem capabilities only for an explicit file-related turn."""
    normalized = text.casefold()
    signals = (
        "file", "folder", "dokumen", "pdf", "spreadsheet", "excel", "arsip",
        "duplikat", "download", "desktop", "scan", "cari", "pindah", "salin",
        "rename", "ubah nama", "ubah isi", "hapus", "rapikan", "bereskan", "kelompokkan",
        "indeks", "drive", "berkas", "edit", "mkdir", "file baru", "folder baru",
    )
    if any(signal in normalized for signal in signals):
        return True
    referential = ("itu", "tadi", "lanjut", "yang sama", "tersebut")
    return any(word in normalized for word in referential) and any(signal in prior_user_text.casefold() for signal in signals)
