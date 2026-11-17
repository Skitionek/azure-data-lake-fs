"""Public Azure Data Lake wrapper client."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol, cast

from .acl import AclEntry, AclRedactedEntry, AclService
from .config import AzureDataLakeFsConfig, ServiceBusSettings
from .observer import ChangeObserver, QueueReceiver
from .publisher import ChangePublisher
from .transfer import AzureDataLakeSasSigner, IndirectTransferService


class PathClient(Protocol):
    url: str

    def get_access_control(self) -> Any:
        """Get ACL payload."""
        ...

    def set_access_control(self, acl: str) -> Any:
        """Set ACL payload."""
        ...

    def exists(self) -> bool:
        """Return whether the path exists."""
        ...

    def upload_data(self, data: Any, **kwargs: Any) -> Any:
        """Upload file content."""
        ...


class FileSystemClient(Protocol):
    def get_file_client(self, path: str) -> PathClient:
        """Get path/file client."""
        ...

    def get_file_system_properties(self) -> Any:
        """Get file system properties; raises when it does not exist."""
        ...

    def create_file_system(self) -> Any:
        """Create the file system."""
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

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        file_system_client: FileSystemClient,
        acl_service: AclService | None,
        transfer_service: IndirectTransferService,
        observer: ChangeObserver | None = None,
        publisher: ChangePublisher | None = None,
    ) -> None:
        self._file_system_client = file_system_client
        self._acl_service = acl_service
        self._transfer_service = transfer_service
        self._observer = observer
        self._publisher = publisher

    @classmethod
    def from_azure(
        cls,
        config: AzureDataLakeFsConfig,
        acl_service: AclService | None = None,
        service_bus_settings: ServiceBusSettings | None = None,
    ) -> "AzureDataLakeFsClient":
        from azure.core.credentials import AzureNamedKeyCredential
        from azure.storage.filedatalake import DataLakeServiceClient

        # A named key credential carries the account name, so shared-key auth
        # also works against custom endpoints (e.g. Azurite) the SDK cannot
        # derive an account name from.
        credential = (
            AzureNamedKeyCredential(config.account_name, config.account_key)
            if config.account_key is not None
            else config.credential
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
        observer = None
        publisher = None
        if service_bus_settings is not None:
            observer = _build_observer_from_service_bus(service_bus_settings)
            publisher = _build_publisher_from_service_bus(service_bus_settings)
        return cls(
            file_system_client=cast(FileSystemClient, file_system_client),
            acl_service=acl_service,
            transfer_service=transfer_service,
            observer=observer,
            publisher=publisher,
        )

    def ensure_file_system(self) -> None:
        """Create the configured file system unless it already exists."""
        from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError

        try:
            self._file_system_client.get_file_system_properties()
        except ResourceNotFoundError:
            try:
                self._file_system_client.create_file_system()
            except ResourceExistsError:
                pass  # Created concurrently by another process.

    def exists(self, path: str) -> bool:
        return self._file_system_client.get_file_client(path).exists()

    def upload(  # pylint: disable=too-many-arguments
        self,
        path: str,
        data: Any,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
        content_type: str | None = None,
    ) -> None:
        """Upload ``data`` (bytes, str or a readable stream) to ``path``."""
        options: dict[str, Any] = {"overwrite": overwrite}
        if metadata:
            options["metadata"] = dict(metadata)
        if content_type:
            from azure.storage.filedatalake import ContentSettings

            options["content_settings"] = ContentSettings(content_type=content_type)
        self._file_system_client.get_file_client(path).upload_data(data, **options)

    def url_for(self, path: str) -> str:
        """Return the unsigned URL of ``path``."""
        return self._file_system_client.get_file_client(path).url

    def get_acl(self, path: str) -> list[AclRedactedEntry]:
        acl_service = self._require_acl_service()
        path_client = self._file_system_client.get_file_client(path)
        acl_string = _extract_acl_string(path_client.get_access_control())
        entries = acl_service.parse_acl(acl_string)
        return acl_service.redact(acl_service.ungroup_entries(entries))

    def set_acl(self, path: str, entries: list[AclEntry]) -> list[AclRedactedEntry]:
        acl_service = self._require_acl_service()
        normalized = acl_service.convert_users_to_groups(entries)
        acl_string = acl_service.serialize_acl(normalized)
        path_client = self._file_system_client.get_file_client(path)
        path_client.set_access_control(acl=acl_string)
        return acl_service.redact(acl_service.ungroup_entries(normalized))

    def _require_acl_service(self) -> AclService:
        if self._acl_service is None:
            raise ValueError("ACL service is not configured")
        return self._acl_service

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

    def publish_change(self, event: Mapping[str, Any]) -> None:
        if self._publisher is None:
            raise ValueError("Change publisher is not configured")
        self._publisher.publish(event)


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


def _build_publisher_from_service_bus(
    settings: ServiceBusSettings,
) -> ChangePublisher:
    from azure.servicebus import ServiceBusClient, ServiceBusMessage

    def send(body: str) -> None:
        with (
            ServiceBusClient.from_connection_string(
                conn_str=settings.connection_string
            ) as service_bus_client,
            service_bus_client.get_queue_sender(
                queue_name=settings.queue_name
            ) as sender,
        ):
            sender.send_messages(ServiceBusMessage(body))

    return ChangePublisher(send=send)
