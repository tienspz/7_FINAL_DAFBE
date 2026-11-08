"""In-process publish/subscribe broker for Server-Sent Events.

Each subscriber owns a bounded queue: a slow or abandoned client drops its
oldest messages instead of blocking a refresh or growing without limit.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from typing import Any

from pipeline.util import utc_now_iso


@dataclass(eq=False)
class Subscription:
    """One SSE connection's message queue."""

    queue: "queue.Queue[dict[str, Any]]" = field(
        default_factory=lambda: queue.Queue(maxsize=64)
    )
    closed: bool = False

    def get(self, timeout: float | None = None) -> dict[str, Any] | None:
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        self.closed = True
        while True:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break


class EventBroker:
    """Thread-safe fan-out of backend events to open SSE streams."""

    def __init__(self, *, max_queue: int = 64) -> None:
        self._max_queue = max(1, int(max_queue))
        self._lock = threading.Lock()
        self._subscribers: set[Subscription] = set()

    def subscribe(self) -> Subscription:
        subscription = Subscription(queue=queue.Queue(maxsize=self._max_queue))
        with self._lock:
            self._subscribers.add(subscription)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        with self._lock:
            self._subscribers.discard(subscription)
        subscription.close()

    def publish(self, event: str, data: dict[str, Any]) -> int:
        """Deliver one event and return how many subscribers received it."""
        message = {
            "event": str(event),
            "data": data,
            "published_at": utc_now_iso(),
        }
        with self._lock:
            subscribers = list(self._subscribers)
        delivered = 0
        for subscription in subscribers:
            if subscription.closed:
                continue
            try:
                subscription.queue.put_nowait(message)
            except queue.Full:
                try:
                    subscription.queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    subscription.queue.put_nowait(message)
                except queue.Full:
                    continue
            delivered += 1
        return delivered

    def subscribers(self) -> int:
        with self._lock:
            return len(self._subscribers)
