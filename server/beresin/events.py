"""Task event bus for streaming progress to the UI (SSE).

The worker publishes status/progress updates; the user API exposes them as
Server-Sent Events. When Redis is configured the events are fanned out through
pub/sub so the queue worker and the API can live in separate processes.
Delivery stays best-effort: if the process or Redis restarts, the frontend
falls back to task polling.
"""
from __future__ import annotations

import json
import queue
import threading
import time

from .config import settings

CHANNEL_PREFIX = "beresin:task-events:"

_SUBSCRIBERS: dict[int, list[queue.Queue]] = {}
_LOCK = threading.Lock()
_LISTENER_STARTED = False
_LISTENER_LOCK = threading.Lock()
_PUBLISH_CLIENT = None
_PUBLISH_LOCK = threading.Lock()


def _channel(task_id: int) -> str:
    return f"{CHANNEL_PREFIX}{task_id}"


def _redis_client():
    """Dedicated client: the queue client's socket timeout would abort a pub/sub read."""
    if not settings.beresin_redis_url:
        return None
    try:
        from redis import Redis

        return Redis.from_url(settings.beresin_redis_url, decode_responses=True)
    except Exception:  # noqa: BLE001 - Redis is an optional accelerator
        return None


def _publish_client():
    global _PUBLISH_CLIENT
    with _PUBLISH_LOCK:
        if _PUBLISH_CLIENT is None:
            _PUBLISH_CLIENT = _redis_client()
        return _PUBLISH_CLIENT


def _deliver(task_id: int, event: dict) -> None:
    with _LOCK:
        subs = list(_SUBSCRIBERS.get(task_id, []))
    for q in subs:
        try:
            q.put_nowait(event)
        except queue.Full:
            pass


def _ensure_listener() -> None:
    """Start one shared subscriber that fans Redis events into local queues."""
    global _LISTENER_STARTED
    with _LISTENER_LOCK:
        if _LISTENER_STARTED:
            return
        client = _redis_client()
        if client is None:
            return
        _LISTENER_STARTED = True

    def run() -> None:
        from redis.exceptions import RedisError

        while True:
            try:
                pubsub = client.pubsub()
                pubsub.psubscribe(f"{CHANNEL_PREFIX}*")
                for message in pubsub.listen():
                    if message.get("type") != "pmessage":
                        continue
                    channel = message.get("channel") or ""
                    if not channel.startswith(CHANNEL_PREFIX):
                        continue
                    try:
                        task_id = int(channel[len(CHANNEL_PREFIX) :])
                    except (TypeError, ValueError):
                        continue
                    try:
                        event = json.loads(message.get("data") or "{}")
                    except (TypeError, ValueError):
                        continue
                    if isinstance(event, dict):
                        _deliver(task_id, event)
            except (RedisError, OSError):
                # Redis restarts and host sleep/wake must not kill the bridge.
                time.sleep(1.0)

    threading.Thread(target=run, name="beresin-sse-bridge", daemon=True).start()


def subscribe(task_id: int) -> queue.Queue:
    q: queue.Queue = queue.Queue(maxsize=200)
    with _LOCK:
        _SUBSCRIBERS.setdefault(task_id, []).append(q)
    _ensure_listener()
    return q


def unsubscribe(task_id: int, q: queue.Queue) -> None:
    with _LOCK:
        subs = _SUBSCRIBERS.get(task_id)
        if subs and q in subs:
            subs.remove(q)
        if subs is not None and not subs:
            _SUBSCRIBERS.pop(task_id, None)


def publish(task_id: int, event: dict) -> None:
    """Fan the event out to every process holding a subscriber for this task."""
    client = _publish_client()
    if client is not None:
        try:
            client.publish(_channel(task_id), json.dumps(event, ensure_ascii=False))
            return
        except Exception:  # noqa: BLE001 - fall back to in-process delivery
            pass
    _deliver(task_id, event)
