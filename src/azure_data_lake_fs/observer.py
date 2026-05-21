"""Service Bus-backed change observation."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from typing import Any, Protocol


class QueueReceiver(Protocol):
    def receive_messages(
        self, max_message_count: int, max_wait_time: int
    ) -> Iterable[Any]:
        """Receive queue messages."""

    def complete_message(self, message: Any) -> None:
        """Complete/acknowledge a message."""

    def close(self) -> None:
        """Close resources."""


class QueueReceiverFactory(Protocol):
    def __call__(self) -> QueueReceiver:
        """Create a queue receiver."""


class ChangeObserver:
    """Runs a queue polling process to observe file-system changes."""

    def __init__(
        self,
        receiver_factory: QueueReceiverFactory,
        max_wait_time_seconds: int,
    ) -> None:
        self._receiver_factory = receiver_factory
        self._max_wait_time_seconds = max_wait_time_seconds
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run_once(self, handler: Callable[[Any], None]) -> int:
        receiver = self._receiver_factory()
        processed = 0
        try:
            messages = receiver.receive_messages(
                max_message_count=50,
                max_wait_time=self._max_wait_time_seconds,
            )
            for message in messages:
                handler(message)
                receiver.complete_message(message)
                processed += 1
        finally:
            receiver.close()
        return processed

    def run_forever(
        self,
        handler: Callable[[Any], None],
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self._stop_event.clear()
        while not self._stop_event.is_set():
            self.run_once(handler)
            self._stop_event.wait(poll_interval_seconds)
