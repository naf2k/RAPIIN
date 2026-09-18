"""Approval card labels and duplicate-request reuse.

Regression tests for two field findings:
1. A single-file move card showed the parent folder instead of `file → destination`.
2. One operation could produce two identical cards; deciding one then broke the task.
"""
from .test_auth import _register_user


def _user_id(client):
    reg = _register_user(client)
    assert reg.status_code == 200, reg.text
    return reg.json()["user_id"]


def _task_id(user_id, device_id=None):
    from rapiin.database import db_session
    from rapiin.tasks import create_task

    with db_session() as conn:
        return create_task(conn, user_id=user_id, device_id=device_id, type="conversation")


def test_describe_single_move_shows_file_and_destination():
    from rapiin.agent.core import _describe_action

    action = _describe_action(
        "file_move",
        {
            "source": "/Users/andi/Downloads/_uji_rapiin",
            "paths": ["/Users/andi/Downloads/_uji_rapiin/foto-kantor.png"],
            "destination": "/Users/andi/Downloads/_uji_rapiin/arsip",
        },
    )
    assert action.startswith("Memindahkan file (")
    assert "foto-kantor.png" in action
    assert "arsip" in action
    assert "_uji_rapiin)" not in action


def test_describe_multi_move_shows_count():
    from rapiin.agent.core import _describe_action

    action = _describe_action(
        "file_move",
        {
            "paths": [f"/data/f{i}.txt" for i in range(4)],
            "destination": "/data/arsip",
        },
    )
    assert action == "Memindahkan file (4 file → /data/arsip)"


def test_describe_delete_lists_files():
    from rapiin.agent.core import _describe_action

    action = _describe_action("file_delete", {"paths": ["/data/a.txt", "/data/b.txt"]})
    assert action == "Menghapus file (/data/a.txt, /data/b.txt)"


def test_describe_unknown_action_without_target():
    from rapiin.agent.core import _describe_action

    assert _describe_action("file_search", {}) == "file_search"


def test_scope_prefers_file_list_over_folder():
    from rapiin.agent.core import _scope_of

    scope = _scope_of(
        {
            "source": "/data/inbox",
            "paths": ["/data/inbox/a.txt"],
            "destination": "/data/arsip",
        }
    )
    assert scope == "/data/inbox/a.txt"


def test_identical_request_reuses_pending_approval(client):
    user_id = _user_id(client)
    from rapiin.approval import create_approval, get_approval
    from rapiin.database import db_session

    args = {"paths": ["/data/a.txt"], "destination": "/data/arsip"}
    task_id = _task_id(user_id)
    with db_session() as conn:
        first = create_approval(
            conn, task_id=task_id, user_id=user_id, requested_by="RAPIIN", kind="USER",
            action="x", tool_name="file_move", tool_args=args,
        )
        second = create_approval(
            conn, task_id=task_id, user_id=user_id, requested_by="RAPIIN", kind="USER",
            action="x", tool_name="file_move", tool_args=args,
        )
        rows = conn.execute(
            "SELECT COUNT(*) AS n FROM approvals WHERE user_id = ? AND status = 'PENDING'",
            (user_id,),
        ).fetchone()["n"]
    assert first == second
    assert rows == 1
    with db_session() as conn:
        assert get_approval(conn, first)["status"] == "PENDING"


def test_different_args_or_task_create_new_approval(client):
    user_id = _user_id(client)
    from rapiin.approval import create_approval
    from rapiin.database import db_session

    task_a = _task_id(user_id)
    task_b = _task_id(user_id)
    with db_session() as conn:
        base = create_approval(
            conn, task_id=task_a, user_id=user_id, requested_by="RAPIIN", kind="USER",
            action="x", tool_name="file_move",
            tool_args={"paths": ["/data/a.txt"], "destination": "/data/arsip"},
        )
        other_args = create_approval(
            conn, task_id=task_a, user_id=user_id, requested_by="RAPIIN", kind="USER",
            action="x", tool_name="file_move",
            tool_args={"paths": ["/data/b.txt"], "destination": "/data/arsip"},
        )
        other_task = create_approval(
            conn, task_id=task_b, user_id=user_id, requested_by="RAPIIN", kind="USER",
            action="x", tool_name="file_move",
            tool_args={"paths": ["/data/a.txt"], "destination": "/data/arsip"},
        )
    assert len({base, other_args, other_task}) == 3


def test_reuse_across_tasks_when_any_task(client):
    user_id = _user_id(client)
    from rapiin.approval import create_approval, find_reusable_approval
    from rapiin.database import db_session

    args = {"paths": ["/data/a.txt"], "destination": "/data/arsip"}
    task_a = _task_id(user_id)
    task_b = _task_id(user_id)
    with db_session() as conn:
        first = create_approval(
            conn, task_id=task_a, user_id=user_id, requested_by="RAPIIN", kind="USER",
            action="x", tool_name="file_move", tool_args=args,
        )
        same_task = find_reusable_approval(
            conn, user_id=user_id, kind="USER", tool_name="file_move", tool_args=args, task_id=task_a,
        )
        other_task = find_reusable_approval(
            conn, user_id=user_id, kind="USER", tool_name="file_move", tool_args=args, task_id=task_b,
        )
        any_task = find_reusable_approval(
            conn, user_id=user_id, kind="USER", tool_name="file_move", tool_args=args, any_task=True,
        )
    assert same_task == first
    assert other_task is None
    assert any_task == first


def test_concurrent_identical_requests_yield_single_approval(client):
    import threading

    user_id = _user_id(client)
    from rapiin.approval import create_approval
    from rapiin.database import db_session

    args = {"paths": ["/data/a.txt"], "destination": "/data/arsip"}
    with db_session() as conn:
        from rapiin.tasks import create_task
        task_id = create_task(conn, user_id=user_id, device_id=None, type="conversation")

    results: list = []
    errors: list = []

    def worker():
        try:
            with db_session() as conn:
                results.append(create_approval(
                    conn, task_id=task_id, user_id=user_id, requested_by="RAPIIN", kind="USER",
                    action="x", tool_name="file_move", tool_args=args,
                ))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not errors
    assert len(results) == 8
    assert len(set(results)) == 1
    with db_session() as conn:
        rows = conn.execute(
            "SELECT COUNT(*) AS n FROM approvals WHERE user_id = ? AND status = 'PENDING'",
            (user_id,),
        ).fetchone()["n"]
    assert rows == 1


def test_expired_approval_is_not_reused(client):
    user_id = _user_id(client)
    from rapiin.approval import create_approval
    from rapiin.database import db_session

    args = {"paths": ["/data/a.txt"], "destination": "/data/arsip"}
    task_id = _task_id(user_id)
    with db_session() as conn:
        first = create_approval(
            conn, task_id=task_id, user_id=user_id, requested_by="RAPIIN", kind="USER",
            action="x", tool_name="file_move", tool_args=args,
        )
        conn.execute(
            "UPDATE approvals SET expires_at = '2000-01-01T00:00:00+00:00' WHERE id = ?",
            (first,),
        )
    with db_session() as conn:
        second = create_approval(
            conn, task_id=task_id, user_id=user_id, requested_by="RAPIIN", kind="USER",
            action="x", tool_name="file_move", tool_args=args,
        )
    assert second != first
