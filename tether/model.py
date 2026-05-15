from __future__ import annotations

import uuid
from typing import Literal

import msgspec

from .errors import InvalidTetherError

TetherType = Literal["related", "describes", "tests", "references"]
VALID_TYPES: frozenset[str] = frozenset(["related", "describes", "tests", "references"])
UNIDIRECTIONAL_ONLY: frozenset[str] = frozenset(["describes", "tests"])
DEFAULT_BIDIRECTIONAL: dict[str, bool] = {
    "related": True,
    "describes": False,
    "tests": False,
    "references": False,
}


class Artifact(msgspec.Struct, frozen=True, kw_only=True):
    path: str
    fingerprint: str


class Tether(msgspec.Struct, frozen=True, kw_only=True):
    id: str
    schema_version: int
    src: Artifact
    dst: Artifact
    type: TetherType
    bidirectional: bool
    description: str | None
    created_at: str
    refreshed_at: str


def default_bidirectional(t: str) -> bool:
    return DEFAULT_BIDIRECTIONAL[t]


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

    if t.type not in VALID_TYPES:
        raise InvalidTetherError(
            f"invalid type {t.type!r}; must be one of {sorted(VALID_TYPES)}"
        )

    if t.type in UNIDIRECTIONAL_ONLY and t.bidirectional:
        raise InvalidTetherError(f"type {t.type!r} cannot be bidirectional")

    if not t.src.path or not t.dst.path:
        raise InvalidTetherError("artifact paths must be non-empty")

    if t.src.path == t.dst.path:
        raise InvalidTetherError("src.path == dst.path: self-tethers are not allowed")

    if not t.src.fingerprint or not t.dst.fingerprint:
        raise InvalidTetherError("artifact fingerprints must be non-empty")

    if t.created_at > t.refreshed_at:
        raise InvalidTetherError(
            f"created_at ({t.created_at}) is later than refreshed_at ({t.refreshed_at})"
        )
