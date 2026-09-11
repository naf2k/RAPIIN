import time

from redis.exceptions import TimeoutError as RedisTimeoutError

from beresin.queue_backend import dequeue_conversation_task, enqueue_conversation_task, redis_ready


class FakeRedis:
    def __init__(self):
        self.items = []

    def lpush(self, key, value):
        self.items.insert(0, (key, value))

    def brpop(self, key, timeout):
        if not self.items:
            return None
        _, value = self.items.pop()
        return key, value

    def ping(self):
        return True


class FailingRedis:
    """Simulates a stale connection, e.g. after host sleep/wake or a restart."""

    def lpush(self, key, value):
        raise RedisTimeoutError("Timeout reading from socket")

    def brpop(self, key, timeout):
        raise RedisTimeoutError("Timeout reading from socket")

    def ping(self):
        raise RedisTimeoutError("Timeout reading from socket")


def test_redis_queue_round_trip(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr("beresin.queue_backend.redis_client", lambda: fake)
    assert enqueue_conversation_task(42)
    assert dequeue_conversation_task(timeout=0) == 42
    assert dequeue_conversation_task(timeout=0) is None
    assert redis_ready()


def test_blocking_read_outlasts_brpop_timeout(monkeypatch):
    """BRPOP must not race its own socket timeout.

    Regression: socket_timeout equalled the blocking timeout, so an empty
    queue raised TimeoutError instead of returning None.
    """
    from beresin.queue_backend import SOCKET_TIMEOUT_SECONDS, redis_client

    captured = {}

    class FakeRedisModule:
        @staticmethod
        def from_url(url, **kwargs):
            captured.update(kwargs)
            return FakeRedis()

    monkeypatch.setattr("beresin.config.settings.beresin_redis_url", "redis://127.0.0.1:6379/0")
    monkeypatch.setitem(__import__("sys").modules, "redis", type("m", (), {"Redis": FakeRedisModule}))
    redis_client()
    assert captured["socket_timeout"] == SOCKET_TIMEOUT_SECONDS
    assert SOCKET_TIMEOUT_SECONDS > 5, "must outlast the default BRPOP timeout"


def test_transient_redis_failure_is_not_fatal(monkeypatch):
    monkeypatch.setattr("beresin.queue_backend.redis_client", lambda: FailingRedis())
    assert enqueue_conversation_task(7) is False
    assert dequeue_conversation_task(timeout=2) is None
    assert redis_ready() is False


def test_queue_worker_survives_transient_redis_failure(monkeypatch):
    """Regression: a Redis timeout killed the worker process.

    The poll loop must log, back off, and keep consuming instead of dying and
    relying on launchd to restart it.
    """
    import threading

    from beresin import worker

    stop = threading.Event()
    calls = []

    def failing_then_stopping(timeout=5):
        calls.append(timeout)
        if len(calls) == 1:
            raise RedisTimeoutError("Timeout reading from socket")
        stop.set()
        return None

    monkeypatch.setattr("beresin.queue_backend.dequeue_conversation_task", failing_then_stopping)
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    worker.run_queue_worker(stop_event=stop)
    assert len(calls) == 2, "worker must keep polling after a transient failure"
