"""Chat flow tests using a fake provider so no external AI is called."""
import time

from .test_auth import _register_user


class DummyProvider:
    """Fake provider that returns a fixed assistant reply without tools."""

    def chat(self, messages, tools=None, max_tokens=None):
        return {
            "message": {
                "role": "assistant",
                "content": "Baik, saya sudah mencatat permintaan Anda.",
            },
            "latency_ms": 1,
            "raw": {},
        }

    def tools_schema(self):
        return []

    def tool_result_message(self, call_id, content, name=""):
        msg = {"role": "tool", "tool_call_id": call_id, "content": content}
        if name:
            msg["name"] = name
        return msg


def _login(client, email):
    return client.post(
        "/api/auth/login", json={"email": email, "password": "Password123!"}
    ).json()["token"]


def _wait_task(client, token, task_id, timeout=15):
    """Poll the async task until it finishes (test helper)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = client.get(f"/api/user/tasks/{task_id}", headers={"Authorization": f"Bearer {token}"}).json()
        if task["status"] in {"COMPLETED", "FAILED", "CANCELLED", "WAITING_APPROVAL"}:
            return task
        time.sleep(0.3)
    raise AssertionError(f"Task {task_id} tidak selesai dalam {timeout}s")


def _patch_provider(monkeypatch):
    import beresin.ai.provider as provider_mod

    monkeypatch.setattr(provider_mod, "get_provider", lambda: DummyProvider())


def test_conversation_flow_with_fake_provider(client, monkeypatch):
    _register_user(client)
    token = _login(client, "andi@example.com")

    conv = client.post(
        "/api/user/conversations",
        json={"title": "Tes chat"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert conv.status_code == 200
    conversation_id = conv.json()["conversation_id"]

    # Patch the provider used by the background worker (async task queue).
    _patch_provider(monkeypatch)

    resp = client.post(
        f"/api/user/conversations/{conversation_id}/messages",
        json={"content": "Halo, tolong rapikan file saya."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "PROCESSING"
    assert body["task_id"]

    task = _wait_task(client, token, body["task_id"])
    assert task["status"] == "COMPLETED", task.get("error")

    msgs = client.get(
        f"/api/user/conversations/{conversation_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert len(msgs) >= 2
    assert msgs[-1]["role"] == "assistant"


def test_tasks_listed_for_user(client, monkeypatch):
    _register_user(client)
    token = _login(client, "andi@example.com")

    _patch_provider(monkeypatch)

    conv = client.post(
        "/api/user/conversations",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    resp = client.post(
        f"/api/user/conversations/{conv['conversation_id']}/messages",
        json={"content": "Buatkan ringkasan kerja."},
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    _wait_task(client, token, resp["task_id"])

    tasks = client.get("/api/user/tasks", headers={"Authorization": f"Bearer {token}"}).json()
    assert len(tasks) >= 1
    assert tasks[0]["status"] in {"COMPLETED", "FAILED", "CANCELLED", "WAITING_APPROVAL"}


def test_casual_chat_hides_filesystem_tools_but_file_request_exposes_them():
    from beresin.agent.core import HermesCore

    seen = []
    class CapturingProvider(DummyProvider):
        def tools_schema(self):
            return [{"type": "function", "function": {"name": "filesystem_scanner"}}]
        def chat(self, messages, tools=None, max_tokens=None):
            seen.append(tools)
            return super().chat(messages, tools=tools, max_tokens=max_tokens)

    import sqlite3
    conn = sqlite3.connect(":memory:")
    HermesCore(CapturingProvider()).run_user_conversation(
        conn, user_id=1, conversation_history=[{"role": "user", "content": "Halo, apa kabar?"}],
        task_id=None, device_id=None,
    )
    HermesCore(CapturingProvider()).run_user_conversation(
        conn, user_id=1, conversation_history=[{"role": "user", "content": "Tolong rapikan folder Downloads"}],
        task_id=None, device_id=None,
    )
    assert seen[0] == []
    assert seen[1][0]["function"]["name"] == "filesystem_scanner"
