"""Configuration models for the Azure Data Lake wrapper."""

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TokenCredential(Protocol):
    """Minimal protocol matching ``azure.core.credentials.TokenCredential``."""

    def get_token(self, *scopes: str, **kwargs: Any) -> Any:
        """Return an ``AccessToken`` for the requested scopes."""


@dataclass(frozen=True)
class SasPolicy:
    """Policy for creating temporary SAS URLs."""

    expiry_minutes: int = 30
    download_permissions: str = "r"
    upload_permissions: str = "cw"

    def __post_init__(self) -> None:
        if self.expiry_minutes <= 0:
            raise ValueError("SAS expiry_minutes must be positive")
        if not self.download_permissions:
            raise ValueError("SAS download_permissions must not be empty")
        if not self.upload_permissions:
            raise ValueError("SAS upload_permissions must not be empty")


@dataclass(frozen=True)
class AclPolicy:
    """Policy for ACL transformation and safety limits."""

    max_records: int = 64
    group_prefix: str = "adlfs-perm-"
    redact_raw_records: bool = True
    administrative_unit_id: str | None = None

    def __post_init__(self) -> None:
        if self.max_records <= 0:
            raise ValueError("ACL max_records must be positive")
        if not self.group_prefix:
            raise ValueError("ACL group_prefix must not be empty")
        if self.administrative_unit_id is not None and not self.administrative_unit_id:
            raise ValueError("ACL administrative_unit_id must not be empty")


@dataclass(frozen=True)
class ServiceBusSettings:
    """Settings for Service Bus-backed change observation."""

    connection_string: str
    queue_name: str
    max_wait_time_seconds: int = 5

    def __post_init__(self) -> None:
        if not self.connection_string:
            raise ValueError("Service Bus connection_string must not be empty")
        if not self.queue_name:
            raise ValueError("Service Bus queue_name must not be empty")
        if self.max_wait_time_seconds <= 0:
            raise ValueError("Service Bus max_wait_time_seconds must be positive")


@dataclass(frozen=True)
class AzureDataLakeFsConfig:
    """Top-level config for Azure Data Lake wrapper.

    Provide either ``account_key`` (storage account key string) or a token
    ``credential`` such as ``DefaultAzureCredential``.  When ``account_key``
    is supplied it is used directly for SAS token generation.  When only
    ``credential`` is supplied the client fetches a user-delegation key at
    runtime to sign SAS URLs.
    """

    account_name: str
    file_system_name: str
    account_key: str | None = None
    credential: TokenCredential | None = None
    acl_policy: AclPolicy = AclPolicy()
    sas_policy: SasPolicy = SasPolicy()

    def __post_init__(self) -> None:
        if not self.account_name:
            raise ValueError("account_name must not be empty")
        if not self.file_system_name:
            raise ValueError("file_system_name must not be empty")
        if self.account_key is None and self.credential is None:
            raise ValueError(
                "Either account_key or credential must be provided"
            )
        if self.account_key is not None and not self.account_key:
            raise ValueError("account_key must not be empty")

    @property
    def account_url(self) -> str:
        return f"https://{self.account_name}.dfs.core.windows.net"
