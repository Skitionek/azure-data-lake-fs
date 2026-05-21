import pytest

from azure_data_lake_fs.acl import (
    AclEntry,
    AclService,
    InMemoryPermissionGroupDirectory,
    PermissionGroupMapper,
)
from azure_data_lake_fs.config import AclPolicy


def build_acl_service(max_records: int = 64) -> AclService:
    mapper = PermissionGroupMapper(
        directory=InMemoryPermissionGroupDirectory(),
        group_prefix="perm-",
    )
    return AclService(policy=AclPolicy(max_records=max_records), mapper=mapper)


def test_acl_get_is_redacted() -> None:
    service = build_acl_service()
    entries = [
        AclEntry(principal_type="user", principal_id="abc", permissions="r--"),
        AclEntry(principal_type="group", principal_id="def", permissions="rw-"),
        AclEntry(principal_type="other", permissions="---"),
    ]

    redacted = service.redact(entries)

    assert redacted[0].principal == "REDACTED"
    assert redacted[1].principal == "REDACTED"
    assert redacted[2].principal == "SYSTEM"


def test_user_entries_are_converted_to_lazy_permission_groups() -> None:
    service = build_acl_service()
    entries = [
        AclEntry(principal_type="user", principal_id="u1", permissions="r--"),
        AclEntry(principal_type="user", principal_id="u2", permissions="r--"),
        AclEntry(principal_type="user", principal_id="u3", permissions="rw-"),
    ]

    converted = service.convert_users_to_groups(entries)

    assert len(converted) == 2
    permissions = sorted(entry.permissions for entry in converted)
    assert permissions == ["r--", "rw-"]
    for entry in converted:
        assert entry.principal_type == "group"
        assert entry.principal_id is not None


def test_conversion_respects_acl_record_limit() -> None:
    service = build_acl_service(max_records=1)
    entries = [
        AclEntry(principal_type="user", principal_id="u1", permissions="r--"),
        AclEntry(principal_type="user", principal_id="u2", permissions="rw-"),
    ]

    with pytest.raises(ValueError) as error:
        service.convert_users_to_groups(entries)
    assert "exceeds" in str(error.value)


def test_ungroup_entries_restores_known_user_entries() -> None:
    service = build_acl_service()
    source_entries = [
        AclEntry(principal_type="user", principal_id="u1", permissions="r--"),
        AclEntry(principal_type="user", principal_id="u2", permissions="r--"),
    ]
    grouped_entries = service.convert_users_to_groups(source_entries)

    ungrouped_entries = service.ungroup_entries(grouped_entries)

    assert len(ungrouped_entries) == 2
    principals = sorted(
        entry.principal_id
        for entry in ungrouped_entries
        if entry.principal_id is not None
    )
    assert principals == ["u1", "u2"]
    assert all(entry.principal_type == "user" for entry in ungrouped_entries)


def test_group_creation_uses_administrative_unit() -> None:
    class RecordingDirectory(InMemoryPermissionGroupDirectory):
        def __init__(self) -> None:
            super().__init__()
            self.calls: list[tuple[str, str | None]] = []

        def ensure_group(
            self,
            display_name: str,
            administrative_unit_id: str | None = None,
        ) -> str:
            self.calls.append((display_name, administrative_unit_id))
            return super().ensure_group(
                display_name=display_name,
                administrative_unit_id=administrative_unit_id,
            )

    directory = RecordingDirectory()
    mapper = PermissionGroupMapper(
        directory=directory,
        group_prefix="perm-",
        administrative_unit_id="au-123",
    )
    service = AclService(policy=AclPolicy(), mapper=mapper)

    service.convert_users_to_groups(
        [AclEntry(principal_type="user", principal_id="u1", permissions="r--")]
    )

    assert directory.calls == [("perm-r__", "au-123")]
