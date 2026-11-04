# azure-data-lake-fs

Python wrapper for Azure Data Lake Storage Gen2 with:

- ACL redaction on read/write surfaces
- Lazy permission-to-group mapping to reduce ACL record pressure
- On-the-fly user ACL conversion into groups to help stay below the 64-record ACL limit
- Indirect upload/download workflow via returned SAS URLs
- Direct uploads, existence checks and file-system bootstrap for server-side callers
- Optional Service Bus queue observer and publisher for change-driven handling

## Installation

```bash
pip install .
```

For development:

```bash
pip install -e .[dev]
```

## High-level API

```python
from azure_data_lake_fs import (
    AclPolicy,
    AclService,
    AzureDataLakeFsClient,
    AzureDataLakeFsConfig,
    InMemoryPermissionGroupDirectory,
    PermissionGroupMapper,
)

config = AzureDataLakeFsConfig(
    account_name="myaccount",
    file_system_name="myfs",
    account_key="***",
    acl_policy=AclPolicy(
        max_records=64,
        group_prefix="adlfs-perm-",
        administrative_unit_id="00000000-0000-0000-0000-000000000000",
    ),
)

acl_service = AclService(
    policy=config.acl_policy,
    mapper=PermissionGroupMapper(
        directory=InMemoryPermissionGroupDirectory(),
        group_prefix=config.acl_policy.group_prefix,
        administrative_unit_id=config.acl_policy.administrative_unit_id,
    ),
)

client = AzureDataLakeFsClient.from_azure(config=config, acl_service=acl_service)
```

`acl_service` is optional; without it `get_acl`/`set_acl` raise `ValueError`.

### Authentication and endpoints

- `account_key`: shared-key auth; SAS URLs are signed with the key.
- `credential`: any token credential (e.g. `DefaultAzureCredential`); SAS URLs are signed with a
  user-delegation key.
- `endpoint`: overrides `https://<account>.dfs.core.windows.net`, e.g. for Azurite.
- `AzureDataLakeFsConfig.from_connection_string(conn_str, file_system_name, **kwargs)` builds a
  config from a connection string carrying `AccountName` and `AccountKey`; `BlobEndpoint` becomes
  the endpoint, as in `DataLakeServiceClient.from_connection_string`.

## Storage operations

- `ensure_file_system()` creates the configured file system unless it exists.
- `exists(path)` reports whether a file exists.
- `upload(path, data, overwrite=False, metadata=None, content_type=None)` writes bytes, text or a
  readable stream.
- `url_for(path)` returns the unsigned file URL.

## ACL behavior

- `get_acl(path)` returns redacted entries (`principal` is never exposed as raw object ID).
- `get_acl(path)` returns ungrouped records for mapper-managed groups when user mappings are known.
- `set_acl(path, entries)` converts named `user` ACL records to lazily-created permission groups.
- Group creation can be scoped to an Entra administrative unit via `AclPolicy.administrative_unit_id`.
- Conversion deduplicates resulting group ACLs and validates final ACL count against `max_records`.

## Indirect data transfer

- `open_download_context(path)` returns a context object with SAS URL for caller-side download.
- `open_upload_context(path)` returns a context object with SAS URL for caller-side upload.
- Library does not stream file bytes directly in these methods.

## Change observation mode

Pass `ServiceBusSettings` as `service_bus_settings` to `from_azure` to enable the observer and the
publisher on the same queue.

- `run_change_observer(handler, once=True)` processes one receive cycle.
- `run_change_observer(handler)` starts polling until `stop_change_observer()` is called.
- `publish_change(event)` sends `event` to the queue as a JSON message.

## Architecture notes

- `AclService` owns ACL parse/serialize, redaction, and user-to-group conversion.
- `PermissionGroupMapper` lazily creates/reuses one group per permission tuple.
- `IndirectTransferService` provides SAS-context opening semantics.
- `ChangeObserver` encapsulates queue receive/ack loop for process-mode observation.
- `ChangePublisher` serializes change events and hands them to the queue sender.

## Infrastructure bootstrap

A deployable Bicep template is included at:

- `infra/azure-data-lake-servicebus.bicep`

It provisions:

- ADLS Gen2-capable storage account (`isHnsEnabled: true`)
- Service Bus namespace + queue
- Event Grid system topic and subscription that forwards storage events to the queue

The storage account template disables public network access by default.
