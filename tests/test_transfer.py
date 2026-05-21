from azure_data_lake_fs.config import AzureDataLakeFsConfig
from azure_data_lake_fs.transfer import AzureDataLakeSasSigner, IndirectTransferService


class FakeSigner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []

    def sign(self, path: str, permissions: str, expiry_minutes: int) -> str:
        self.calls.append((path, permissions, expiry_minutes))
        return f"https://example.test/{path}?perm={permissions}&exp={expiry_minutes}"


def test_download_context_returns_sas_url() -> None:
    config = AzureDataLakeFsConfig(
        account_name="acct",
        file_system_name="fs",
        account_key="key",
    )
    signer = FakeSigner()
    service = IndirectTransferService(config=config, signer=signer)

    context = service.open_download_context("folder/data.csv")

    assert context.operation == "download"
    assert context.path == "folder/data.csv"
    assert context.sas_url.startswith("https://example.test/folder/data.csv")
    assert signer.calls[0][1] == config.sas_policy.download_permissions


def test_upload_context_returns_sas_url() -> None:
    config = AzureDataLakeFsConfig(
        account_name="acct",
        file_system_name="fs",
        account_key="key",
    )
    signer = FakeSigner()
    service = IndirectTransferService(config=config, signer=signer)

    context = service.open_upload_context("folder/data.csv")

    assert context.operation == "upload"
    assert context.path == "folder/data.csv"
    assert context.sas_url.startswith("https://example.test/folder/data.csv")
    assert signer.calls[0][1] == config.sas_policy.upload_permissions


def test_signer_rejects_empty_path() -> None:
    config = AzureDataLakeFsConfig(
        account_name="acct",
        file_system_name="fs",
        account_key="key",
    )
    signer = AzureDataLakeSasSigner(config=config)

    try:
        signer.sign("", "r", 5)
    except ValueError as error:
        assert str(error) == "path must not be empty"
    else:
        raise AssertionError("Expected ValueError for empty path")


def test_signer_rejects_directory_path() -> None:
    config = AzureDataLakeFsConfig(
        account_name="acct",
        file_system_name="fs",
        account_key="key",
    )
    signer = AzureDataLakeSasSigner(config=config)

    try:
        signer.sign("folder/", "r", 5)
    except ValueError as error:
        assert str(error) == "path must reference a file"
    else:
        raise AssertionError("Expected ValueError for directory path")
