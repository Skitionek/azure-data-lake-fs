"""Configuration models for the Azure Data Lake wrapper."""

from dataclasses import dataclass


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

    def __post_init__(self) -> None:
        if self.max_records <= 0:
            raise ValueError("ACL max_records must be positive")
        if not self.group_prefix:
            raise ValueError("ACL group_prefix must not be empty")


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
    """Top-level config for Azure Data Lake wrapper."""

    account_name: str
    file_system_name: str
    account_key: str
    acl_policy: AclPolicy = AclPolicy()
    sas_policy: SasPolicy = SasPolicy()

    def __post_init__(self) -> None:
        if not self.account_name:
            raise ValueError("account_name must not be empty")
        if not self.file_system_name:
            raise ValueError("file_system_name must not be empty")
        if not self.account_key:
            raise ValueError("account_key must not be empty")

    @property
    def account_url(self) -> str:
        return f"https://{self.account_name}.dfs.core.windows.net"
