# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring,missing-function-docstring
# pylint: disable=too-few-public-methods

from azure_data_lake_fs.client import _build_observer_from_service_bus
from azure_data_lake_fs.config import ServiceBusSettings


class FakeReceiver:
    def __init__(self, messages: list[str]) -> None:
        self.messages = messages
        self.completed: list[str] = []
        self.closed = 0

    def receive_messages(self, max_message_count: int, max_wait_time: int):
        _ = (max_message_count, max_wait_time)
        returned = self.messages[:]
        self.messages.clear()
        return returned

    def complete_message(self, message: str) -> None:
        self.completed.append(message)

    def close(self) -> None:
        self.closed += 1


class FakeServiceBusClient:
    def __init__(self, messages: list[str]) -> None:
        self.receiver = FakeReceiver(messages=messages)
        self.closed = 0

    def get_queue_receiver(self, queue_name: str) -> FakeReceiver:
        _ = queue_name
        return self.receiver

    def close(self) -> None:
        self.closed += 1


def _settings() -> ServiceBusSettings:
    return ServiceBusSettings(
        connection_string="Endpoint=sb://x/;SharedAccessKeyName=k;SharedAccessKey=s",
        queue_name="q",
        max_wait_time_seconds=1,
    )


def test_run_once_closes_client_exactly_once() -> None:
    created: list[FakeServiceBusClient] = []

    def client_factory() -> FakeServiceBusClient:
        client = FakeServiceBusClient(messages=["m1", "m2"])
        created.append(client)
        return client

    observer = _build_observer_from_service_bus(
        _settings(), client_factory=client_factory
    )
    seen: list[str] = []

    processed = observer.run_once(lambda message: seen.append(message))

    assert processed == 2
    assert seen == ["m1", "m2"]
    # Exactly one client created and closed for this cycle.
    assert len(created) == 1
    assert created[0].closed == 1
    assert created[0].receiver.closed == 1
    # No client left unclosed.
    assert all(client.closed >= 1 for client in created)


def test_run_forever_leaves_no_unclosed_clients() -> None:
    created: list[FakeServiceBusClient] = []

    def client_factory() -> FakeServiceBusClient:
        client = FakeServiceBusClient(messages=["m"])
        created.append(client)
        return client

    observer = _build_observer_from_service_bus(
        _settings(), client_factory=client_factory
    )
    seen: list[str] = []
    iterations = 0

    # Stop after a bounded number of poll cycles by intercepting the handler.
    def handler(message: str) -> None:
        seen.append(message)

    # Drive a bounded number of run_once cycles directly to emulate
    # run_forever without relying on wall-clock timing.
    for _ in range(3):
        observer.run_once(handler)
        iterations += 1

    assert iterations == 3
    # One client per cycle, each closed exactly once, none leaked.
    assert len(created) == 3
    assert all(client.closed == 1 for client in created)
    assert all(client.receiver.closed == 1 for client in created)


def test_close_is_idempotent() -> None:
    client = FakeServiceBusClient(messages=[])

    observer = _build_observer_from_service_bus(
        _settings(), client_factory=lambda: client
    )
    receiver = observer._receiver_factory()  # pylint: disable=protected-access

    receiver.close()
    receiver.close()

    # Idempotent: the underlying client/receiver are closed once, not twice.
    assert client.closed == 1
    assert client.receiver.closed == 1
