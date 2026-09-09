from __future__ import annotations
import asyncio
from queue import Queue
from threading import Lock

from .events import Event


class EventBus:
    """Thread-safe + asyncio-safe event bus.

    `publish()` is non-blocking and may be called from any thread.
    `subscribe()` returns an `asyncio.Queue` for an async consumer.
    """

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[Event]] = []
        self._lock = Lock()

    def subscribe(self) -> asyncio.Queue[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue()
        with self._lock:
            self._subscribers.append(q)
        return q

    def publish(self, event: Event) -> None:
        with self._lock:
            subs = list(self._subscribers)
        for q in subs:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Drop on overflow — HUD coalesces anyway.
                pass
