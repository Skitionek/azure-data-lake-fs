# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring,missing-function-docstring
# pylint: disable=too-few-public-methods,unnecessary-lambda

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import pytest
from azure.core.credentials import AzureNamedKeyCredential
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError

from azure_data_lake_fs.acl import (
    AclEntry,
    AclRedactedEntry,
    AclService,
    InMemoryPermissionGroupDirectory,
    PermissionGroupMapper,
)
from azure_data_lake_fs.client import AzureDataLakeFsClient
from azure_data_lake_fs.config import (
    AclPolicy,
    AzureDataLakeFsConfig,
    ServiceBusSettings,
)
from azure_data_lake_fs.observer import ChangeObserver
from azure_data_lake_fs.publisher import ChangePublisher
from azure_data_lake_fs.transfer import IndirectTransferService


@dataclass
class FakePathClient:
    acl: str
    set_acl: str | None = None
    url: str = "https://acct.dfs.core.windows.net/fs/test"
    present: bool = False
    uploads: list[tuple[Any, dict[str, Any]]] = field(default_factory=list)

    def get_access_control(self) -> dict[str, str]:
        return {"acl": self.acl}

    def set_access_control(self, acl: str):
        self.set_acl = acl
        self.acl = acl
        return {"ok": True}

    def exists(self) -> bool:
        return self.present

    def upload_data(self, data: Any, **kwargs: Any) -> None:
        self.uploads.append((data, kwargs))


class FakeFileSystemClient:
    def __init__(
        self,
        path_client: FakePathClient,
        properties_error: Exception | None = None,
        create_error: Exception | None = None,
    ) -> None:
        self.path_client = path_client
        self.requested_paths: list[str] = []
        self.properties_error = properties_error
        self.create_error = create_error
        self.created = False

    def get_file_client(self, path: str) -> FakePathClient:
        self.requested_paths.append(path)
        return self.path_client

    def get_file_system_properties(self) -> dict[str, str]:
        if self.properties_error is not None:
            raise self.properties_error
        return {}

    def create_file_system(self) -> None:
        if self.create_error is not None:
            raise self.create_error
        self.created = True


class FakeSigner:
    def sign(self, path: str, permissions: str, expiry_minutes: int) -> str:
        return f"https://example.test/{path}?perm={permissions}&exp={expiry_minutes}"


def build_client(
    path_client: FakePathClient,
    observer: ChangeObserver | None = None,
    max_records: int = 64,
    file_system_client: FakeFileSystemClient | None = None,
    publisher: ChangePublisher | None = None,
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
        file_system_client=file_system_client
        or FakeFileSystemClient(path_client=path_client),
        acl_service=acl_service,
        transfer_service=transfer_service,
        observer=observer,
        publisher=publisher,
    )


def set_acl_for_two_users(
    max_records: int = 64,
) -> tuple[FakePathClient, list[AclRedactedEntry]]:
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


def test_acl_operations_require_acl_service() -> None:
    client = AzureDataLakeFsClient(
        file_system_client=FakeFileSystemClient(path_client=FakePathClient(acl="")),
        acl_service=None,
        transfer_service=IndirectTransferService(
            config=AzureDataLakeFsConfig(
                account_name="acct", file_system_name="fs", account_key="key"
            ),
            signer=FakeSigner(),
        ),
    )

    with pytest.raises(ValueError, match="ACL service is not configured"):
        client.get_acl("/test")
    with pytest.raises(ValueError, match="ACL service is not configured"):
        client.set_acl("/test", [])


def test_ensure_file_system_keeps_existing_file_system() -> None:
    file_system_client = FakeFileSystemClient(path_client=FakePathClient(acl=""))
    client = build_client(
        file_system_client.path_client, file_system_client=file_system_client
    )

    client.ensure_file_system()

    assert file_system_client.created is False


def test_ensure_file_system_creates_missing_file_system() -> None:
    file_system_client = FakeFileSystemClient(
        path_client=FakePathClient(acl=""),
        properties_error=ResourceNotFoundError("missing"),
    )
    client = build_client(
        file_system_client.path_client, file_system_client=file_system_client
    )

    client.ensure_file_system()

    assert file_system_client.created is True


def test_ensure_file_system_tolerates_concurrent_creation() -> None:
    file_system_client = FakeFileSystemClient(
        path_client=FakePathClient(acl=""),
        properties_error=ResourceNotFoundError("missing"),
        create_error=ResourceExistsError("exists"),
    )
    client = build_client(
        file_system_client.path_client, file_system_client=file_system_client
    )

    client.ensure_file_system()  # must not raise


def test_exists_reports_path_presence() -> None:
    path_client = FakePathClient(acl="", present=True)
    file_system_client = FakeFileSystemClient(path_client=path_client)
    client = build_client(path_client, file_system_client=file_system_client)

    assert client.exists("folder/data.csv") is True
    assert file_system_client.requested_paths == ["folder/data.csv"]


def test_upload_passes_content_and_options_to_sdk() -> None:
    path_client = FakePathClient(acl="")
    file_system_client = FakeFileSystemClient(path_client=path_client)
    client = build_client(path_client, file_system_client=file_system_client)

    client.upload(
        "folder/data.csv",
        b"a,b",
        overwrite=True,
        metadata={"source": "test"},
        content_type="text/csv",
    )

    data, options = path_client.uploads[0]
    assert file_system_client.requested_paths == ["folder/data.csv"]
    assert data == b"a,b"
    assert options["overwrite"] is True
    assert options["metadata"] == {"source": "test"}
    assert options["content_settings"].content_type == "text/csv"


def test_upload_defaults_to_no_overwrite_without_optional_settings() -> None:
    path_client = FakePathClient(acl="")
    client = build_client(path_client)

    client.upload("data.bin", b"x")

    assert path_client.uploads == [(b"x", {"overwrite": False})]


def test_url_for_returns_unsigned_file_url() -> None:
    client = build_client(FakePathClient(acl="", url="https://example.test/fs/a"))

    assert client.url_for("a") == "https://example.test/fs/a"


def test_publish_change_sends_json_event() -> None:
    sent: list[str] = []
    client = build_client(
        FakePathClient(acl=""), publisher=ChangePublisher(send=sent.append)
    )

    client.publish_change({"event_type": "upload", "file_path": "a.txt"})

    assert sent == ['{"event_type": "upload", "file_path": "a.txt"}']


def test_publish_change_requires_publisher() -> None:
    client = build_client(FakePathClient(acl=""))

    with pytest.raises(ValueError, match="Change publisher is not configured"):
        client.publish_change({"event_type": "upload"})


@patch("azure.storage.filedatalake.DataLakeServiceClient")
def test_from_azure_uses_named_key_credential_and_endpoint(service_client) -> None:
    config = AzureDataLakeFsConfig(
        account_name="devstoreaccount1",
        file_system_name="fs",
        account_key="a2V5",
        endpoint="http://azurite:10000/devstoreaccount1/",
    )

    client = AzureDataLakeFsClient.from_azure(config=config)

    kwargs = service_client.call_args.kwargs
    assert kwargs["account_url"] == "http://azurite:10000/devstoreaccount1"
    assert isinstance(kwargs["credential"], AzureNamedKeyCredential)
    assert kwargs["credential"].named_key == ("devstoreaccount1", "a2V5")
    service_client.return_value.get_file_system_client.assert_called_once_with(
        file_system="fs"
    )
    with pytest.raises(ValueError, match="Change publisher is not configured"):
        client.publish_change({})


@patch("azure.storage.filedatalake.DataLakeServiceClient")
def test_from_azure_passes_token_credential_through(service_client) -> None:
    class Credential:
        def get_token(self, *scopes: str, **kwargs: Any) -> Any:
            _ = (scopes, kwargs)
            return object()

    credential = Credential()
    config = AzureDataLakeFsConfig(
        account_name="acct", file_system_name="fs", credential=credential
    )

    AzureDataLakeFsClient.from_azure(config=config)

    assert service_client.call_args.kwargs["credential"] is credential


@patch("azure.servicebus.ServiceBusClient")
@patch("azure.storage.filedatalake.DataLakeServiceClient")
def test_from_azure_publishes_through_service_bus(_, service_bus_client) -> None:
    config = AzureDataLakeFsConfig(
        account_name="acct", file_system_name="fs", account_key="a2V5"
    )
    client = AzureDataLakeFsClient.from_azure(
        config=config,
        service_bus_settings=ServiceBusSettings(
            connection_string="sb-conn-str", queue_name="events"
        ),
    )

    client.publish_change({"event_type": "upload"})

    service_bus_client.from_connection_string.assert_called_once_with(
        conn_str="sb-conn-str"
    )
    bus = service_bus_client.from_connection_string.return_value.__enter__.return_value
    bus.get_queue_sender.assert_called_once_with(queue_name="events")
    sender = bus.get_queue_sender.return_value.__enter__.return_value
    (message,) = sender.send_messages.call_args.args
    assert b"".join(message.body) == b'{"event_type": "upload"}'
