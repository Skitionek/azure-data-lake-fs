import threading
import time

from azure_data_lake_fs.observer import ChangeObserver


class FakeReceiver:
    def __init__(self, messages: list[str]) -> None:
        self.messages = messages
        self.completed: list[str] = []
        self.closed = False

    def receive_messages(
        self, max_message_count: int, max_wait_time: int
    ) -> list[str]:
        _ = (max_message_count, max_wait_time)
        returned = self.messages[:]
        self.messages.clear()
        return returned

    def complete_message(self, message: str) -> None:
        self.completed.append(message)

    def close(self) -> None:
        self.closed = True


def test_run_once_processes_and_acks_messages() -> None:
    receiver = FakeReceiver(messages=["m1", "m2"])
    observer = ChangeObserver(
        receiver_factory=lambda: receiver,
        max_wait_time_seconds=1,
    )
    seen: list[str] = []

    processed = observer.run_once(lambda message: seen.append(message))

    assert processed == 2
    assert seen == ["m1", "m2"]
    assert receiver.completed == ["m1", "m2"]
    assert receiver.closed is True


def test_run_forever_can_be_stopped() -> None:
    lock = threading.Lock()
    queue = ["m1", "m2", "m3"]

    def factory() -> FakeReceiver:
        with lock:
            messages = queue[:1]
            if queue:
                queue.pop(0)
            return FakeReceiver(messages=messages)

    observer = ChangeObserver(
        receiver_factory=factory,
        max_wait_time_seconds=1,
    )
    seen: list[str] = []

    thread = threading.Thread(
        target=lambda: observer.run_forever(
            handler=lambda message: seen.append(message), poll_interval_seconds=0.01
        )
    )
    thread.start()
    timeout = time.time() + 1.0
    while len(seen) < 2 and time.time() < timeout:
        time.sleep(0.01)
    observer.stop()
    thread.join(timeout=1)

    assert len(seen) >= 2
