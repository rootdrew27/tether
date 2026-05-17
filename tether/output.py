from __future__ import annotations

import msgspec

from .status import AggregateState, ArtifactState


class ArtifactStatus(msgspec.Struct, frozen=True, kw_only=True):
    path: str
    fingerprint: str
    state: ArtifactState
    diff: str | None = None
    normalization_rescued: bool = False
    rename_candidates: tuple[str, ...] = ()


class TetherStatus(msgspec.Struct, frozen=True, kw_only=True):
    id: str
    schema_version: int
    description: str
    created_at: str
    refreshed_at: str
    a: ArtifactStatus
    b: ArtifactStatus
    state: AggregateState


class StatusSummary(
    msgspec.Struct,
    frozen=True,
    kw_only=True,
    rename={
        "healthy": "HEALTHY",
        "weakened": "WEAKENED",
        "drifted": "DRIFTED",
        "broken": "BROKEN",
    },
):
    total: int
    healthy: int
    weakened: int
    drifted: int
    broken: int


class LoadError(msgspec.Struct, frozen=True, kw_only=True):
    path: str
    error: str


class StatusReport(msgspec.Struct, frozen=True, kw_only=True):
    summary: StatusSummary
    tethers: list[TetherStatus]
    errors: list[LoadError]


def encode_pretty(obj: object) -> str:
    return msgspec.json.format(msgspec.json.encode(obj), indent=2).decode("utf-8")
