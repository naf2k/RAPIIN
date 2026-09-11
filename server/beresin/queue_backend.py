"""Optional Redis transport; the database remains the durable job source of truth."""
from __future__ import annotations

from .config import settings

QUEUE_KEY = "beresin:conversation-jobs:v1"
# BRPOP blocks server-side for its own timeout; the socket read must outlast
# that, otherwise an empty queue raises a read timeout instead of returning None.
SOCKET_TIMEOUT_SECONDS = 15


def redis_client():
    if not settings.beresin_redis_url:
        return None
    from redis import Redis
    return Redis.from_url(settings.beresin_redis_url, decode_responses=True, socket_timeout=SOCKET_TIMEOUT_SECONDS)


def enqueue_conversation_task(task_id: int) -> bool:
    from redis.exceptions import RedisError
    client = redis_client()
    if client is None:
        return False
    try:
        client.lpush(QUEUE_KEY, str(task_id))
    except RedisError:
        # Returning False lets the caller fall back to an in-process thread
        # instead of dropping the task when Redis is unavailable.
        return False
    return True


def dequeue_conversation_task(timeout: int = 5) -> int | None:
    """Pop the next task id, treating a transient Redis failure as "no work".

    The poll loop must outlive Redis restarts and host sleep/wake, so a stale
    connection returns None and the worker retries on its next tick.
    """
    from redis.exceptions import RedisError
    client = redis_client()
    if client is None:
        return None
    try:
        item = client.brpop(QUEUE_KEY, timeout=timeout)
    except RedisError:
        return None
    return int(item[1]) if item else None


def redis_ready() -> bool:
    from redis.exceptions import RedisError
    client = redis_client()
    if client is None:
        return True
    try:
        return bool(client.ping())
    except RedisError:
        return False
