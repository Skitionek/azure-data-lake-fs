"""Public Azure Data Lake wrapper client."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from .acl import AclEntry, AclRedactedEntry, AclService
from .config import AzureDataLakeFsConfig, ServiceBusSettings
from .observer import ChangeObserver, QueueReceiver
from .transfer import AzureDataLakeSasSigner, IndirectTransferService


class PathClient(Protocol):
    def get_access_control(self) -> Any:
        """Get ACL payload."""
        ...

    def set_access_control(self, acl: str) -> Any:
        """Set ACL payload."""
        ...


class FileSystemClient(Protocol):
    def get_file_client(self, path: str) -> PathClient:
        """Get path/file client."""
        ...


def _extract_acl_string(payload: Any) -> str:
    if payload is None:
        return ""
    if isinstance(payload, dict):
        return str(payload.get("acl", ""))
    acl_value = getattr(payload, "acl", "")
    return str(acl_value or "")


class AzureDataLakeFsClient:
    """High-level wrapper for ACL-safe and indirect-transfer file operations."""

    def __init__(
        self,
        file_system_client: FileSystemClient,
        acl_service: AclService,
        transfer_service: IndirectTransferService,
        observer: ChangeObserver | None = None,
    ) -> None:
        self._file_system_client = file_system_client
        self._acl_service = acl_service
        self._transfer_service = transfer_service
        self._observer = observer

    @classmethod
    def from_azure(
        cls,
        config: AzureDataLakeFsConfig,
        acl_service: AclService,
        service_bus_settings: ServiceBusSettings | None = None,
    ) -> "AzureDataLakeFsClient":
        from azure.storage.filedatalake import DataLakeServiceClient

        credential = (
            config.account_key if config.account_key is not None else config.credential
        )
        data_lake_service_client = DataLakeServiceClient(
            account_url=config.account_url,
            credential=credential,
        )
        file_system_client = data_lake_service_client.get_file_system_client(
            file_system=config.file_system_name
        )
        signer = AzureDataLakeSasSigner(
            config=config,
            service_client=(
                data_lake_service_client if config.account_key is None else None
            ),
        )
        transfer_service = IndirectTransferService(
            config=config,
            signer=signer,
        )
        observer = (
            _build_observer_from_service_bus(service_bus_settings)
            if service_bus_settings is not None
            else None
        )
        return cls(
            file_system_client=file_system_client,
            acl_service=acl_service,
            transfer_service=transfer_service,
            observer=observer,
        )

    def get_acl(self, path: str) -> list[AclRedactedEntry]:
        path_client = self._file_system_client.get_file_client(path)
        acl_string = _extract_acl_string(path_client.get_access_control())
        entries = self._acl_service.parse_acl(acl_string)
        return self._acl_service.redact(self._acl_service.ungroup_entries(entries))

    def set_acl(self, path: str, entries: list[AclEntry]) -> list[AclRedactedEntry]:
        normalized = self._acl_service.convert_users_to_groups(entries)
        acl_string = self._acl_service.serialize_acl(normalized)
        path_client = self._file_system_client.get_file_client(path)
        path_client.set_access_control(acl=acl_string)
        return self._acl_service.redact(self._acl_service.ungroup_entries(normalized))

    def open_download_context(self, path: str):
        return self._transfer_service.open_download_context(path)

    def open_upload_context(self, path: str):
        return self._transfer_service.open_upload_context(path)

    def run_change_observer(
        self,
        handler: Callable[[Any], None],
        *,
        once: bool = False,
        poll_interval_seconds: float = 1.0,
    ) -> int | None:
        if self._observer is None:
            raise ValueError("Change observer is not configured")
        if once:
            return self._observer.run_once(handler)
        self._observer.run_forever(
            handler=handler, poll_interval_seconds=poll_interval_seconds
        )
        return None

    def stop_change_observer(self) -> None:
        if self._observer is not None:
            self._observer.stop()


def _build_observer_from_service_bus(
    settings: ServiceBusSettings,
) -> ChangeObserver:
    from azure.servicebus import ServiceBusClient

    class AzureQueueReceiver:
        def __init__(self, receiver: Any) -> None:
            self._receiver = receiver

        def receive_messages(
            self, max_message_count: int, max_wait_time: int
        ) -> list[Any]:
            return list(
                self._receiver.receive_messages(
                    max_message_count=max_message_count,
                    max_wait_time=max_wait_time,
                )
            )

        def complete_message(self, message: Any) -> None:
            self._receiver.complete_message(message)

        def close(self) -> None:
            self._receiver.close()

    def receiver_factory() -> QueueReceiver:
        service_bus_client = ServiceBusClient.from_connection_string(
            conn_str=settings.connection_string
        )
        receiver = service_bus_client.get_queue_receiver(queue_name=settings.queue_name)
        return AzureQueueReceiver(receiver)

    return ChangeObserver(
        receiver_factory=receiver_factory,
        max_wait_time_seconds=settings.max_wait_time_seconds,
    )
