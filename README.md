# azure-data-lake-fs

Python wrapper for Azure Data Lake Storage Gen2 with:

- ACL redaction on read/write surfaces
- Lazy permission-to-group mapping to reduce ACL record pressure
- On-the-fly user ACL conversion into groups to help stay below the 64-record ACL limit
- Indirect upload/download workflow via returned SAS URLs
- Optional Service Bus queue observer process for change-driven handling

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
    acl_policy=AclPolicy(max_records=64, group_prefix="adlfs-perm-"),
)

acl_service = AclService(
    policy=config.acl_policy,
    mapper=PermissionGroupMapper(
        directory=InMemoryPermissionGroupDirectory(),
        group_prefix=config.acl_policy.group_prefix,
    ),
)

client = AzureDataLakeFsClient.from_azure(config=config, acl_service=acl_service)
```

## ACL behavior

- `get_acl(path)` returns redacted entries (`principal` is never exposed as raw object ID).
- `set_acl(path, entries)` converts named `user` ACL records to lazily-created permission groups.
- Conversion deduplicates resulting group ACLs and validates final ACL count against `max_records`.

## Indirect data transfer

- `open_download_context(path)` returns a context object with SAS URL for caller-side download.
- `open_upload_context(path)` returns a context object with SAS URL for caller-side upload.
- Library does not stream file bytes directly in these methods.

## Change observation mode

Configure `ServiceBusSettings` and construct the client with observer enabled.

- `run_change_observer(handler, once=True)` processes one receive cycle.
- `run_change_observer(handler)` starts polling until `stop_change_observer()` is called.

## Architecture notes

- `AclService` owns ACL parse/serialize, redaction, and user-to-group conversion.
- `PermissionGroupMapper` lazily creates/reuses one group per permission tuple.
- `IndirectTransferService` provides SAS-context opening semantics.
- `ChangeObserver` encapsulates queue receive/ack loop for process-mode observation.
