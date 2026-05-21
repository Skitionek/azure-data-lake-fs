"""Indirect transfer contexts backed by SAS URLs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol
from urllib.parse import quote

from .config import AzureDataLakeFsConfig


class SasSigner(Protocol):
    def sign(self, path: str, permissions: str, expiry_minutes: int) -> str:
        """Return full SAS URL for the given file path and permissions."""


@dataclass(frozen=True)
class TransferContext:
    operation: Literal["download", "upload"]
    path: str
    sas_url: str


class AzureDataLakeSasSigner:
    """Generates SAS URLs for file paths in a file system."""

    def __init__(self, config: AzureDataLakeFsConfig) -> None:
        self._config = config

    def sign(self, path: str, permissions: str, expiry_minutes: int) -> str:
        from azure.storage.filedatalake import FileSasPermissions, generate_file_sas

        normalized_path = path.lstrip("/")
        expiry = datetime.now(UTC) + timedelta(minutes=expiry_minutes)
        token = generate_file_sas(
            account_name=self._config.account_name,
            file_system_name=self._config.file_system_name,
            file_path=normalized_path,
            account_key=self._config.account_key,
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
