"""Thread-safe Server-Sent Events (SSE) broker for real-time updates."""

import json
import queue
import threading
from datetime import datetime, timezone
from typing import Any


class EventBroker:
    """Broadcasts live domain events (cart, order, KDS, menu) to connected SSE clients."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: set[queue.Queue[str]] = set()

    def subscribe(self) -> queue.Queue[str]:
        """Register a new client queue and return it."""
        q: queue.Queue[str] = queue.Queue(maxsize=100)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: queue.Queue[str]) -> None:
        """Remove a client queue on disconnect."""
        with self._lock:
            self._subscribers.discard(q)

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        """Send a serialized SSE event frame to all active subscribers."""
        envelope = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        frame = f"event: {event_type}\ndata: {json.dumps(envelope)}\n\n"
        with self._lock:
            stale: list[queue.Queue[str]] = []
            for sub in self._subscribers:
                try:
                    sub.put_nowait(frame)
                except queue.Full:
                    stale.append(sub)
            for sub in stale:
                self._subscribers.discard(sub)

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)
