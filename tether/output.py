from __future__ import annotations

from pathlib import Path

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


class RefsReport(msgspec.Struct, frozen=True, kw_only=True):
    queried_path: str
    summary: StatusSummary
    tethers: list[TetherStatus]
    errors: list[LoadError]


def encode_pretty(obj: object) -> str:
    return msgspec.json.format(msgspec.json.encode(obj), indent=2).decode("utf-8")


def relativize_errors(
    errors: list[tuple[Path, str]], project_root: Path
) -> list[LoadError]:
    out: list[LoadError] = []
    for p, msg in errors:
        if p.is_absolute():
            try:
                rel = str(p.relative_to(project_root))
            except ValueError:
                rel = str(p)
        else:
            rel = str(p)
        out.append(LoadError(path=rel, error=msg))
    return out
