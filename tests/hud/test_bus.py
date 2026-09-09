import asyncio
from lingua.hud.events import LogEvent
from lingua.hud.bus import EventBus


def test_subscribe_returns_queue():
    bus = EventBus()
    q = bus.subscribe()
    assert isinstance(q, asyncio.Queue)


def test_publish_reaches_subscriber():
    bus = EventBus()
    q = bus.subscribe()
    bus.publish(LogEvent(ts=0.0, level="info", message="hi"))
    e = q.get_nowait()
    assert e.message == "hi"


def test_multiple_subscribers_each_receive():
    bus = EventBus()
    q1 = bus.subscribe()
    q2 = bus.subscribe()
    bus.publish(LogEvent(ts=0.0, level="info", message="x"))
    assert q1.get_nowait().message == "x"
    assert q2.get_nowait().message == "x"


def test_burst_publish_does_not_drop():
    bus = EventBus()
    q = bus.subscribe()
    for i in range(10_000):
        bus.publish(LogEvent(ts=0.0, level="info", message=str(i)))
    received = [q.get_nowait().message for _ in range(10_000)]
    assert received == [str(i) for i in range(10_000)]
