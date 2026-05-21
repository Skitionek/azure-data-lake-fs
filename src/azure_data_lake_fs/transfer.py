"""Indirect transfer contexts backed by SAS URLs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol
from urllib.parse import quote

from .config import AzureDataLakeFsConfig


class SasSigner(Protocol):
    def sign(self, path: str, permissions: str, expiry_minutes: int) -> str:
        """Return full SAS URL for the given file path and permissions."""
        ...


class _UserDelegationKeyProvider(Protocol):
    """Minimal interface for obtaining a user-delegation key."""

    def get_user_delegation_key(
        self,
        key_start_time: Any,
        key_expiry_time: Any,
    ) -> Any:
        """Return a user-delegation key valid between start and expiry."""


@dataclass(frozen=True)
class TransferContext:
    operation: Literal["download", "upload"]
    path: str
    sas_url: str


class AzureDataLakeSasSigner:
    """Generates SAS URLs for file paths in a file system.

    When the config supplies an ``account_key`` it is used directly.
    Otherwise a user-delegation key is obtained from ``service_client``
    (a ``DataLakeServiceClient`` instance) at signing time.
    """

    def __init__(
        self,
        config: AzureDataLakeFsConfig,
        service_client: _UserDelegationKeyProvider | None = None,
    ) -> None:
        self._config = config
        self._service_client = service_client

    def sign(self, path: str, permissions: str, expiry_minutes: int) -> str:
        from azure.storage.filedatalake import FileSasPermissions, generate_file_sas

        normalized_path = path.lstrip("/")
        if not normalized_path:
            raise ValueError("path must not be empty")
        directory_name, _, file_name = normalized_path.rpartition("/")
        expiry = datetime.now(UTC) + timedelta(minutes=expiry_minutes)

        if self._config.account_key is not None:
            token = generate_file_sas(
                account_name=self._config.account_name,
                file_system_name=self._config.file_system_name,
                directory_name=directory_name,
                file_name=file_name,
                credential=self._config.account_key,
                permission=FileSasPermissions.from_string(permissions),
                expiry=expiry,
            )
        else:
            if self._service_client is None:
                raise ValueError(
                    "service_client is required for token-credential SAS signing"
                )
            start = datetime.now(UTC) - timedelta(minutes=5)
            udk = self._service_client.get_user_delegation_key(
                key_start_time=start,
                key_expiry_time=expiry,
            )
            token = generate_file_sas(
                account_name=self._config.account_name,
                file_system_name=self._config.file_system_name,
                directory_name=directory_name,
                file_name=file_name,
                credential=udk,
                permission=FileSasPermissions.from_string(permissions),
                expiry=expiry,
            )

        encoded_path = quote(normalized_path)
        return (
            f"{self._config.account_url}/"
            f"{self._config.file_system_name}/{encoded_path}?{token}"
        )


class IndirectTransferService:
    """Returns upload/download contexts that carry SAS URLs."""

    def __init__(self, config: AzureDataLakeFsConfig, signer: SasSigner) -> None:
        self._config = config
        self._signer = signer

    def open_download_context(self, path: str) -> TransferContext:
        sas_url = self._signer.sign(
            path=path,
            permissions=self._config.sas_policy.download_permissions,
            expiry_minutes=self._config.sas_policy.expiry_minutes,
        )
        return TransferContext(operation="download", path=path, sas_url=sas_url)

    def open_upload_context(self, path: str) -> TransferContext:
        sas_url = self._signer.sign(
            path=path,
            permissions=self._config.sas_policy.upload_permissions,
            expiry_minutes=self._config.sas_policy.expiry_minutes,
        )
        return TransferContext(operation="upload", path=path, sas_url=sas_url)
