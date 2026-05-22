# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring,missing-function-docstring
# pylint: disable=too-few-public-methods,unnecessary-lambda

from dataclasses import dataclass

from azure_data_lake_fs.acl import (
    AclEntry,
    AclService,
    InMemoryPermissionGroupDirectory,
    PermissionGroupMapper,
)
from azure_data_lake_fs.client import AzureDataLakeFsClient
from azure_data_lake_fs.config import AclPolicy, AzureDataLakeFsConfig
from azure_data_lake_fs.observer import ChangeObserver
from azure_data_lake_fs.transfer import IndirectTransferService


@dataclass
class FakePathClient:
    acl: str
    set_acl: str | None = None

    def get_access_control(self) -> dict[str, str]:
        return {"acl": self.acl}

    def set_access_control(self, acl: str):
        self.set_acl = acl
        self.acl = acl
        return {"ok": True}


class FakeFileSystemClient:
    def __init__(self, path_client: FakePathClient) -> None:
        self.path_client = path_client

    def get_file_client(self, path: str) -> FakePathClient:
        _ = path
        return self.path_client


class FakeSigner:
    def sign(self, path: str, permissions: str, expiry_minutes: int) -> str:
        return f"https://example.test/{path}?perm={permissions}&exp={expiry_minutes}"


def build_client(
    path_client: FakePathClient,
    observer: ChangeObserver | None = None,
    max_records: int = 64,
):
    acl_service = AclService(
        policy=AclPolicy(max_records=max_records),
        mapper=PermissionGroupMapper(
            directory=InMemoryPermissionGroupDirectory(),
            group_prefix="perm-",
            administrative_unit_id="au-123",
        ),
    )
    transfer_service = IndirectTransferService(
        config=AzureDataLakeFsConfig(
            account_name="acct",
            file_system_name="fs",
            account_key="key",
        ),
        signer=FakeSigner(),
    )
    return AzureDataLakeFsClient(
        file_system_client=FakeFileSystemClient(path_client=path_client),
        acl_service=acl_service,
        transfer_service=transfer_service,
        observer=observer,
    )


def set_acl_for_two_users(
    max_records: int = 64,
) -> tuple[FakePathClient, list[AclEntry]]:
    path_client = FakePathClient(acl="")
    client = build_client(path_client, max_records=max_records)
    response = client.set_acl(
        "/test",
        [
            AclEntry(principal_type="user", principal_id="u1", permissions="r--"),
            AclEntry(principal_type="user", principal_id="u2", permissions="r--"),
        ],
    )
    return path_client, response


def test_get_acl_returns_redacted_entries() -> None:
    client = build_client(FakePathClient(acl="user:alice:r--,other::---"))

    result = client.get_acl("/test")

    assert result[0].principal == "REDACTED"
    assert result[1].principal == "SYSTEM"


def test_set_acl_converts_users_to_groups_before_write() -> None:
    path_client, response = set_acl_for_two_users(max_records=1)

    assert path_client.set_acl is not None
    assert path_client.set_acl.count("group:") == 1
    assert len(response) == 2
    assert all(entry.principal == "REDACTED" for entry in response)


def test_set_acl_preserves_users_when_within_limit() -> None:
    path_client, response = set_acl_for_two_users()

    assert path_client.set_acl is not None
    assert path_client.set_acl.count("user:") == 2
    assert path_client.set_acl.count("group:") == 0
    assert all(entry.principal_type == "user" for entry in response)


def test_get_acl_returns_ungrouped_after_compacted_write() -> None:
    path_client = FakePathClient(acl="")
    client = build_client(path_client, max_records=1)
    client.set_acl(
        "/test",
        [
            AclEntry(principal_type="user", principal_id="u1", permissions="r--"),
            AclEntry(principal_type="user", principal_id="u2", permissions="r--"),
        ],
    )

    result = client.get_acl("/test")

    assert len(result) == 2
    assert all(entry.principal_type == "user" for entry in result)


def test_run_change_observer_once() -> None:
    messages = ["a", "b"]

    class Receiver:
        def receive_messages(self, max_message_count: int, max_wait_time: int):
            _ = (max_message_count, max_wait_time)
            returned = messages[:]
            messages.clear()
            return returned

        def complete_message(self, message):
            _ = message

        def close(self):
            pass

    observer = ChangeObserver(
        receiver_factory=lambda: Receiver(), max_wait_time_seconds=1
    )
    client = build_client(FakePathClient(acl=""), observer=observer)
    seen: list[str] = []

    processed = client.run_change_observer(
        lambda message: seen.append(message), once=True
    )

    assert processed == 2
    assert seen == ["a", "b"]
