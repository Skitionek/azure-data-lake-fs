import pytest

from azure_data_lake_fs.config import AclPolicy, AzureDataLakeFsConfig, ServiceBusSettings


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
