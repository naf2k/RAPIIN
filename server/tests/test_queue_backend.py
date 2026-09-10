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


def test_redis_queue_round_trip(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr("beresin.queue_backend.redis_client", lambda: fake)
    assert enqueue_conversation_task(42)
    assert dequeue_conversation_task(timeout=0) == 42
    assert dequeue_conversation_task(timeout=0) is None
    assert redis_ready()
