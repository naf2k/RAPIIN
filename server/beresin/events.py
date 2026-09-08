"""In-process task event bus for streaming progress to the UI (SSE).

The worker publishes status/progress updates; the user API exposes them as
Server-Sent Events. In-memory only: if the process restarts, the frontend
falls back to task polling.
"""
from __future__ import annotations

import queue
import threading

_SUBSCRIBERS: dict[int, list[queue.Queue]] = {}
_LOCK = threading.Lock()


def subscribe(task_id: int) -> queue.Queue:
    q: queue.Queue = queue.Queue(maxsize=200)
    with _LOCK:
        _SUBSCRIBERS.setdefault(task_id, []).append(q)
    return q


def unsubscribe(task_id: int, q: queue.Queue) -> None:
    with _LOCK:
        subs = _SUBSCRIBERS.get(task_id)
        if subs and q in subs:
            subs.remove(q)
        if subs is not None and not subs:
            _SUBSCRIBERS.pop(task_id, None)


def publish(task_id: int, event: dict) -> None:
    with _LOCK:
        subs = list(_SUBSCRIBERS.get(task_id, []))
    for q in subs:
        try:
            q.put_nowait(event)
        except queue.Full:
            pass
