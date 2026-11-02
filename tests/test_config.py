import pytest

from azure_data_lake_fs.config import (
    AclPolicy,
    AzureDataLakeFsConfig,
    SasPolicy,
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


AZURITE_CONNECTION_STRING = (
    "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;"
    "AccountKey=a2V5PQ==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
)


def test_endpoint_overrides_account_url() -> None:
    config = AzureDataLakeFsConfig(
        account_name="myacct",
        file_system_name="fs",
        account_key="key",
        endpoint="http://127.0.0.1:10000/devstoreaccount1/",
    )
    assert config.account_url == "http://127.0.0.1:10000/devstoreaccount1"


def test_empty_endpoint_raises() -> None:
    with pytest.raises(ValueError, match="endpoint must not be empty"):
        AzureDataLakeFsConfig(
            account_name="myacct",
            file_system_name="fs",
            account_key="key",
            endpoint="/",
        )


def test_from_connection_string_uses_blob_endpoint() -> None:
    config = AzureDataLakeFsConfig.from_connection_string(
        AZURITE_CONNECTION_STRING, "fs"
    )
    assert config.account_name == "devstoreaccount1"
    assert config.account_key == "a2V5PQ=="  # "=" padding survives parsing
    assert config.file_system_name == "fs"
    assert config.account_url == "http://127.0.0.1:10000/devstoreaccount1"


def test_from_connection_string_derives_dfs_endpoint_from_suffix() -> None:
    config = AzureDataLakeFsConfig.from_connection_string(
        "DefaultEndpointsProtocol=https;AccountName=foo;AccountKey=YmFy;"
        "EndpointSuffix=core.chinacloudapi.cn",
        "fs",
    )
    assert config.account_url == "https://foo.dfs.core.chinacloudapi.cn"


def test_from_connection_string_defaults_to_public_cloud() -> None:
    config = AzureDataLakeFsConfig.from_connection_string(
        "accountname=foo;accountkey=YmFy", "fs"
    )
    assert config.endpoint is None
    assert config.account_url == "https://foo.dfs.core.windows.net"


def test_from_connection_string_passes_policies_through() -> None:
    sas_policy = SasPolicy(expiry_minutes=60)
    config = AzureDataLakeFsConfig.from_connection_string(
        AZURITE_CONNECTION_STRING, "fs", sas_policy=sas_policy
    )
    assert config.sas_policy is sas_policy


@pytest.mark.parametrize(
    "connection_string",
    [
        "AccountName=foo;SharedAccessSignature=sv=2024",
        "AccountKey=YmFy;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1",
    ],
)
def test_from_connection_string_requires_account_name_and_key(
    connection_string: str,
) -> None:
    with pytest.raises(ValueError, match="AccountName and AccountKey"):
        AzureDataLakeFsConfig.from_connection_string(connection_string, "fs")


@pytest.mark.parametrize("connection_string", ["", "not-a-connection-string"])
def test_from_connection_string_rejects_malformed_input(connection_string: str) -> None:
    with pytest.raises(ValueError, match="malformed"):
        AzureDataLakeFsConfig.from_connection_string(connection_string, "fs")
