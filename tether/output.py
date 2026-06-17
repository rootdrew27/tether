from __future__ import annotations

from pathlib import Path

import msgspec

from .coverage import Coverage
from .model import Artifact, Locator, Tether
from .render import Row, by_severity, counts
from .status import (
    AggregateState,
    ArtifactCheck,
    ArtifactState,
    RenameCandidate,
    TetherCheck,
    artifact_diff,
)


class ArtifactStatus(msgspec.Struct, frozen=True, kw_only=True):
    path: str
    fingerprint: str
    state: ArtifactState
    locator: Locator | None = None
    diff: str | None = None
    normalization_rescued: bool = False
    rename_candidates: tuple[RenameCandidate, ...] = ()


class TetherStatus(msgspec.Struct, frozen=True, kw_only=True):
    id: str
    schema_version: int
    description: str
    created_at: str
    refreshed_at: str
    a: ArtifactStatus
    b: ArtifactStatus
    state: AggregateState


# Maps the snake_case Python field names to their UPPERCASE JSON keys, derived
# from the state enum so it stays in lock-step with AggregateState.
_SUMMARY_RENAME: dict[str, str] = {s.name.lower(): s.value for s in AggregateState}


class StatusSummary(
    msgspec.Struct,
    frozen=True,
    kw_only=True,
    rename=_SUMMARY_RENAME,
):
    total: int
    healthy: int
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


class CoverageReport(msgspec.Struct, frozen=True, kw_only=True):
    tracked: int
    tethered_count: int
    untethered_count: int
    percent: float | None
    tethered_files: list[str]
    untethered_files: list[str]
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


def build_artifact_status(
    a: Artifact,
    art_check: ArtifactCheck,
    root: Path,
    include_diff: bool,
) -> ArtifactStatus:
    diff = None
    if include_diff and (
        art_check.state == ArtifactState.DRIFTED
        or (
            art_check.state == ArtifactState.HEALTHY and art_check.normalization_rescued
        )
    ):
        diff = artifact_diff(a, root)
    # The JSON `fingerprint` carries the drift-relevant hash: a whole-file blob
    # OID, or a region's region_hash. The whole-file blob OID of a region
    # artifact is available via its locator-bearing record on disk.
    fp = a.fingerprint
    fingerprint = fp if isinstance(fp, str) else fp.region_hash
    return ArtifactStatus(
        path=a.path,
        fingerprint=fingerprint,
        state=art_check.state,
        locator=a.locator,
        diff=diff,
        normalization_rescued=art_check.normalization_rescued,
        rename_candidates=art_check.rename_candidates,
    )


def build_tether_status(
    t: Tether,
    check: TetherCheck,
    root: Path,
    include_diff: bool,
) -> TetherStatus:
    return TetherStatus(
        id=t.id,
        schema_version=t.schema_version,
        description=t.description,
        created_at=t.created_at,
        refreshed_at=t.refreshed_at,
        a=build_artifact_status(t.a, check.a, root, include_diff),
        b=build_artifact_status(t.b, check.b, root, include_diff),
        state=check.aggregate,
    )


def build_status_summary(rows: list[Row]) -> StatusSummary:
    c = counts(rows)
    return StatusSummary(
        total=len(rows),
        healthy=c["HEALTHY"],
        drifted=c["DRIFTED"],
        broken=c["BROKEN"],
    )


def build_status_report(
    rows: list[Row],
    errors: list[tuple[Path, str]],
    root: Path,
) -> StatusReport:
    return StatusReport(
        summary=build_status_summary(rows),
        tethers=[build_tether_status(t, ck, root, False) for t, ck in rows],
        errors=relativize_errors(errors, root),
    )


def build_coverage_report(
    cov: Coverage,
    root: Path,
    *,
    list_tethered: bool,
    list_untethered: bool,
) -> CoverageReport:
    percent = round(100 * len(cov.tethered) / cov.tracked, 1) if cov.tracked else None
    return CoverageReport(
        tracked=cov.tracked,
        tethered_count=len(cov.tethered),
        untethered_count=len(cov.untethered),
        percent=percent,
        tethered_files=cov.tethered if list_tethered else [],
        untethered_files=cov.untethered if list_untethered else [],
        errors=relativize_errors(cov.errors, root),
    )


def build_refs_report(
    rel: str,
    rows: list[Row],
    errors: list[tuple[Path, str]],
    root: Path,
) -> RefsReport:
    return RefsReport(
        queried_path=rel,
        summary=build_status_summary(rows),
        tethers=[
            build_tether_status(t, ck, root, False) for t, ck in by_severity(rows)
        ],
        errors=relativize_errors(errors, root),
    )
