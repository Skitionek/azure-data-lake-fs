"""ACL transformation, redaction, and permission-group mapping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, cast

from .config import AclPolicy

PrincipalType = Literal["user", "group", "mask", "other"]


@dataclass(frozen=True)
class AclEntry:
    principal_type: PrincipalType
    permissions: str
    principal_id: str | None = None
    default: bool = False

    def __post_init__(self) -> None:
        if self.principal_type not in {"user", "group", "mask", "other"}:
            raise ValueError(f"Unsupported principal_type: {self.principal_type}")
        if len(self.permissions) != 3:
            raise ValueError("ACL permissions must be a 3-char rwx tuple")
        for char in self.permissions:
            if char not in {"r", "w", "x", "-"}:
                raise ValueError("ACL permissions may only contain r,w,x,-")

    def to_acl_record(self) -> str:
        prefix = "default:" if self.default else ""
        if self.principal_type in {"user", "group"}:
            principal = self.principal_id or ""
            return f"{prefix}{self.principal_type}:{principal}:{self.permissions}"
        return f"{prefix}{self.principal_type}::{self.permissions}"

    @staticmethod
    def from_acl_record(record: str) -> "AclEntry":
        default = False
        if record.startswith("default:"):
            default = True
            record = record[len("default:") :]
        parts = record.split(":")
        if len(parts) != 3:
            raise ValueError(f"Invalid ACL record: {record}")
        principal_type, principal_id, permissions = parts
        normalized_principal_id = principal_id or None
        if principal_type in {"mask", "other"}:
            normalized_principal_id = None
        return AclEntry(
            principal_type=cast(PrincipalType, principal_type),
            principal_id=normalized_principal_id,
            permissions=permissions,
            default=default,
        )


@dataclass(frozen=True)
class AclRedactedEntry:
    principal_type: PrincipalType
    permissions: str
    default: bool
    principal: str


class PermissionGroupDirectory(Protocol):
    def ensure_group(
        self,
        display_name: str,
        administrative_unit_id: str | None = None,
    ) -> str:
        """Return group object id for display name, creating if missing."""


class InMemoryPermissionGroupDirectory:
    """In-memory lazy group creation store for testing and local mode."""

    def __init__(self) -> None:
        self._display_name_to_id: dict[str, str] = {}
        self._next_id: int = 1

    def ensure_group(
        self,
        display_name: str,
        administrative_unit_id: str | None = None,
    ) -> str:
        """Return an in-memory group id; administrative_unit_id is ignored."""
        existing = self._display_name_to_id.get(display_name)
        if existing is not None:
            return existing
        group_id = f"group-{self._next_id}"
        self._next_id += 1
        self._display_name_to_id[display_name] = group_id
        return group_id


class PermissionGroupMapper:
    """Maps permission triples to lazily-created groups."""

    def __init__(
        self,
        directory: PermissionGroupDirectory,
        group_prefix: str,
        administrative_unit_id: str | None = None,
    ) -> None:
        self._directory = directory
        self._group_prefix = group_prefix
        self._administrative_unit_id = administrative_unit_id
        self._cache: dict[str, str] = {}
        self._group_to_users: dict[tuple[str, bool], set[str]] = {}

    def resolve_group_id(self, permissions: str) -> str:
        group_id = self._cache.get(permissions)
        if group_id is not None:
            return group_id
        safe_permissions = permissions.replace("-", "_")
        display_name = f"{self._group_prefix}{safe_permissions}"
        group_id = self._directory.ensure_group(
            display_name=display_name,
            administrative_unit_id=self._administrative_unit_id,
        )
        self._cache[permissions] = group_id
        return group_id

    def map_user_to_group(
        self,
        user_id: str,
        permissions: str,
        *,
        default: bool,
    ) -> str:
        group_id = self.resolve_group_id(permissions)
        key = (group_id, default)
        users = self._group_to_users.setdefault(key, set())
        users.add(user_id)
        return group_id

    def expand_group_entry(self, entry: AclEntry) -> list[AclEntry]:
        if entry.principal_type != "group" or not entry.principal_id:
            return [entry]
        users = self._group_to_users.get((entry.principal_id, entry.default))
        if not users:
            return [entry]
        return [
            AclEntry(
                principal_type="user",
                principal_id=user_id,
                permissions=entry.permissions,
                default=entry.default,
            )
            for user_id in sorted(users)
        ]


class AclService:
    """Transforms ACLs for safe external behavior and 64-record constraints."""

    def __init__(self, policy: AclPolicy, mapper: PermissionGroupMapper) -> None:
        self._policy = policy
        self._mapper = mapper

    @staticmethod
    def parse_acl(acl: str) -> list[AclEntry]:
        if not acl:
            return []
        return [AclEntry.from_acl_record(record) for record in acl.split(",") if record]

    @staticmethod
    def serialize_acl(entries: list[AclEntry]) -> str:
        return ",".join(entry.to_acl_record() for entry in entries)

    def redact(self, entries: list[AclEntry]) -> list[AclRedactedEntry]:
        redacted: list[AclRedactedEntry] = []
        for entry in entries:
            principal = "REDACTED" if entry.principal_id else "SYSTEM"
            redacted.append(
                AclRedactedEntry(
                    principal_type=entry.principal_type,
                    permissions=entry.permissions,
                    default=entry.default,
                    principal=principal,
                )
            )
        return redacted

    def convert_users_to_groups(self, entries: list[AclEntry]) -> list[AclEntry]:
        converted: list[AclEntry] = []
        for entry in entries:
            if entry.principal_type == "user" and entry.principal_id:
                group_id = self._mapper.map_user_to_group(
                    user_id=entry.principal_id,
                    permissions=entry.permissions,
                    default=entry.default,
                )
                converted.append(
                    AclEntry(
                        principal_type="group",
                        principal_id=group_id,
                        permissions=entry.permissions,
                        default=entry.default,
                    )
                )
                continue
            converted.append(entry)
        return self._deduplicate_and_validate(converted)

    def ungroup_entries(self, entries: list[AclEntry]) -> list[AclEntry]:
        expanded: list[AclEntry] = []
        for entry in entries:
            expanded.extend(self._mapper.expand_group_entry(entry))
        return self._deduplicate_and_validate(expanded)

    def _deduplicate_and_validate(self, entries: list[AclEntry]) -> list[AclEntry]:
        deduplicated: dict[tuple[str, str, str, bool], AclEntry] = {}
        for entry in entries:
            deduplicated[
                (
                    entry.principal_type,
                    entry.principal_id or "",
                    entry.permissions,
                    entry.default,
                )
            ] = entry
        normalized = list(deduplicated.values())
        if len(normalized) > self._policy.max_records:
            raise ValueError(
                f"ACL record count ({len(normalized)}) exceeds {self._policy.max_records}"
            )
        return normalized
