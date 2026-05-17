from __future__ import annotations

import uuid

import msgspec

from .errors import InvalidTetherError


class Artifact(msgspec.Struct, frozen=True, kw_only=True):
    path: str
    fingerprint: str


class Tether(msgspec.Struct, frozen=True, kw_only=True):
    id: str
    schema_version: int
    a: Artifact
    b: Artifact
    description: str
    created_at: str
    refreshed_at: str


def validate(t: Tether) -> None:
    try:
        u = uuid.UUID(t.id)
    except ValueError as e:
        raise InvalidTetherError(f"invalid UUID {t.id!r}: {e}") from e
    if u.version != 7:
        raise InvalidTetherError(f"UUID {t.id} is not version 7")

    if t.schema_version != 1:
        raise InvalidTetherError(
            f"unsupported schema_version {t.schema_version}; this build supports 1"
        )

    if not t.a.path or not t.b.path:
        raise InvalidTetherError("artifact paths must be non-empty")

    if t.a.path == t.b.path:
        raise InvalidTetherError("a.path == b.path: self-tethers are not allowed")

    if not t.a.fingerprint or not t.b.fingerprint:
        raise InvalidTetherError("artifact fingerprints must be non-empty")

    if not t.description.strip():
        raise InvalidTetherError("description must be non-empty")

    if t.created_at > t.refreshed_at:
        raise InvalidTetherError(
            f"created_at ({t.created_at}) is later than refreshed_at ({t.refreshed_at})"
        )
