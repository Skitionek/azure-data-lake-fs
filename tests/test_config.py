import pytest

from azure_data_lake_fs.config import (
    AclPolicy,
    AzureDataLakeFsConfig,
    ServiceBusSettings,
)


def test_invalid_acl_policy_raises() -> None:
    with pytest.raises(ValueError):
        AclPolicy(max_records=0)


def test_invalid_service_bus_config_raises() -> None:
    with pytest.raises(ValueError):
        ServiceBusSettings(connection_string="", queue_name="q")


def test_account_url_is_derived_from_account_name() -> None:
    config = AzureDataLakeFsConfig(
        account_name="myacct",
        file_system_name="fs",
        account_key="key",
    )
    assert config.account_url == "https://myacct.dfs.core.windows.net"


def test_empty_administrative_unit_id_raises() -> None:
    with pytest.raises(ValueError):
        AclPolicy(administrative_unit_id="")


def test_credential_accepted_instead_of_account_key() -> None:
    class FakeCredential:
        def get_token(self, *scopes, **kwargs):
            _ = (scopes, kwargs)
            return object()

    config = AzureDataLakeFsConfig(
        account_name="myacct",
        file_system_name="fs",
        credential=FakeCredential(),
    )
    assert config.account_key is None
    assert isinstance(config.credential, FakeCredential)
    assert config.account_url == "https://myacct.dfs.core.windows.net"


def test_neither_account_key_nor_credential_raises() -> None:
    with pytest.raises(ValueError, match="Either account_key or credential"):
        AzureDataLakeFsConfig(
            account_name="myacct",
            file_system_name="fs",
        )


def test_empty_account_key_raises() -> None:
    with pytest.raises(ValueError, match="account_key must not be empty"):
        AzureDataLakeFsConfig(
            account_name="myacct",
            file_system_name="fs",
            account_key="",
        )
