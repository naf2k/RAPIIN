"""Optional Redis transport; the database remains the durable job source of truth."""
from __future__ import annotations

from .config import settings

QUEUE_KEY = "beresin:conversation-jobs:v1"


def redis_client():
    if not settings.beresin_redis_url:
        return None
    from redis import Redis
    return Redis.from_url(settings.beresin_redis_url, decode_responses=True, socket_timeout=5)


def enqueue_conversation_task(task_id: int) -> bool:
    client = redis_client()
    if client is None:
        return False
    client.lpush(QUEUE_KEY, str(task_id))
    return True


def dequeue_conversation_task(timeout: int = 5) -> int | None:
    client = redis_client()
    if client is None:
        return None
    item = client.brpop(QUEUE_KEY, timeout=timeout)
    return int(item[1]) if item else None


def redis_ready() -> bool:
    client = redis_client()
    return True if client is None else bool(client.ping())
