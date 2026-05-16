from __future__ import annotations

import functools
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ParamSpec, TypeVar

import click
from msgspec.structs import replace

from . import __version__
from .errors import TetherError
from .git import hash_object_write
from .model import (
    UNIDIRECTIONAL_ONLY,
    VALID_TYPES,
    Artifact,
    Tether,
    default_bidirectional,
)
from .output import (
    ArtifactStatus,
    LoadError,
    StatusReport,
    StatusSummary,
    TetherStatus,
    encode_pretty,
)
from .project import find_project_root, init_project
from .render import (
    Row,
    counts,
    errors_section,
    item_lines,
    summary_line,
)
from .status import (
    AggregateState,
    ArtifactCheck,
    ArtifactState,
    TetherCheck,
    artifact_diff,
    check_tether,
)
from uuid_utils import uuid7

from .storage import delete as storage_delete
from .storage import load, load_all, save

P = ParamSpec("P")
R = TypeVar("R")


def _utcnow_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _root() -> Path:
    return find_project_root(Path.cwd())


def _resolve_rel(project_root: Path, p: str) -> str:
    cwd = Path.cwd()
    candidate = Path(p) if Path(p).is_absolute() else cwd / p
    resolved = candidate.resolve()
    try:
        rel = resolved.relative_to(project_root)
    except ValueError as e:
        raise TetherError(
            f"path {p!r} is outside the project root {project_root}"
        ) from e
    return rel.as_posix()


def handle_errors(fn: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return fn(*args, **kwargs)
        except TetherError as e:
            click.echo(f"error: {e}", err=True)
            sys.exit(1)

    return wrapper


@click.group()
@click.version_option(__version__)
def main() -> None:
    """tether: typed-relationship annotation layer over content."""


@main.group(invoke_without_command=True)
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize tether state."""
    if ctx.invoked_subcommand is not None:
        return
    _do_init()


@handle_errors
def _do_init() -> None:
    root = init_project(Path.cwd())
    click.echo(f"Initialized tether project at {root / '.tether'}")


@init.command("claude-code")
@handle_errors
def init_claude_code() -> None:
    """Integrate tether with Claude Code."""
    from .claude_code.install import install

    for line in install(Path.cwd()):
        click.echo(line)


@main.command()
@click.argument("src_path")
@click.argument("dst_path")
@click.option(
    "--type",
    "tether_type",
    type=click.Choice(sorted(VALID_TYPES)),
    required=True,
    help="Relationship type.",
)
@click.option(
    "--bidirectional/--unidirectional",
    default=None,
    help="Direction. Defaults by type (related=bidirectional, others=unidirectional).",
)
@click.option("--description", default=None, help="Optional free-form description.")
@handle_errors
def add(
    src_path: str,
    dst_path: str,
    tether_type: str,
    bidirectional: bool | None,
    description: str | None,
) -> None:
    """Create a new tether between two existing files."""
    root = _root()
    src_rel = _resolve_rel(root, src_path)
    dst_rel = _resolve_rel(root, dst_path)
    if src_rel == dst_rel:
        raise TetherError("src and dst must differ; self-tethers are not allowed")

    src_abs = root / src_rel
    dst_abs = root / dst_rel
    if not src_abs.is_file():
        raise TetherError(f"source file does not exist: {src_rel}")
    if not dst_abs.is_file():
        raise TetherError(f"destination file does not exist: {dst_rel}")

    if bidirectional is None:
        bidirectional = default_bidirectional(tether_type)
    if tether_type in UNIDIRECTIONAL_ONLY and bidirectional:
        raise TetherError(f"type {tether_type!r} cannot be bidirectional")

    src_fp = hash_object_write(src_abs, root)
    dst_fp = hash_object_write(dst_abs, root)

    now = _utcnow_iso()
    t = Tether(
        id=str(uuid7()),
        schema_version=1,
        src=Artifact(path=src_rel, fingerprint=src_fp),
        dst=Artifact(path=dst_rel, fingerprint=dst_fp),
        type=tether_type,  # type: ignore[arg-type]
        bidirectional=bidirectional,
        description=description,
        created_at=now,
        refreshed_at=now,
    )
    save(root, t)
    click.echo(f"Created tether {t.id}")


@main.command()
@click.argument("tether_id")
@handle_errors
def rm(tether_id: str) -> None:
    """Delete a tether record."""
    storage_delete(_root(), tether_id)
    click.echo(f"Removed tether {tether_id}")


@main.command()
@click.argument("tether_id")
@handle_errors
def refresh(tether_id: str) -> None:
    """Re-fingerprint both artifacts, asserting they are aligned."""
    root = _root()
    t = load(root, tether_id)
    check = check_tether(t, root)
    if ArtifactState.BROKEN in (check.src.state, check.dst.state):
        raise TetherError(
            "refresh refuses on BROKEN tether — locator does not resolve. "
            "Use `tether update --src-path/--dst-path` to follow the rename first."
        )
    new_t = replace(
        t,
        src=replace(t.src, fingerprint=hash_object_write(root / t.src.path, root)),
        dst=replace(t.dst, fingerprint=hash_object_write(root / t.dst.path, root)),
        refreshed_at=_utcnow_iso(),
    )
    save(root, new_t)
    click.echo(f"Refreshed tether {tether_id}")


@main.command()
@click.argument("tether_id")
@click.option("--src-path", "new_src_path", default=None)
@click.option("--dst-path", "new_dst_path", default=None)
@click.option("--description", "new_description", default=None)
@click.option("--bidirectional/--unidirectional", "new_bidir", default=None)
@handle_errors
def update(
    tether_id: str,
    new_src_path: str | None,
    new_dst_path: str | None,
    new_description: str | None,
    new_bidir: bool | None,
) -> None:
    """Modify a tether's path, description, or direction without touching fingerprints."""
    if all(v is None for v in (new_src_path, new_dst_path, new_description, new_bidir)):
        raise TetherError(
            "no fields to update; pass --src-path, --dst-path, --description, "
            "or --bidirectional/--unidirectional"
        )
    root = _root()
    t = load(root, tether_id)
    changes: dict[str, Any] = {}
    if new_src_path is not None:
        changes["src"] = replace(t.src, path=_resolve_rel(root, new_src_path))
    if new_dst_path is not None:
        changes["dst"] = replace(t.dst, path=_resolve_rel(root, new_dst_path))
    if new_description is not None:
        changes["description"] = new_description
    if new_bidir is not None:
        changes["bidirectional"] = new_bidir
    new_t = replace(t, **changes)
    if new_t.src.path == new_t.dst.path:
        raise TetherError("src and dst must differ after update")
    if new_t.type in UNIDIRECTIONAL_ONLY and new_t.bidirectional:
        raise TetherError(f"type {new_t.type!r} cannot be bidirectional")
    save(root, new_t)
    click.echo(f"Updated tether {tether_id}")


@main.command()
@click.argument("old_path")
@click.argument("new_path")
@handle_errors
def mv(old_path: str, new_path: str) -> None:
    """Rewrite all tether artifacts pointing at OLD_PATH to NEW_PATH."""
    root = _root()
    old_rel = _resolve_rel(root, old_path)
    new_rel = _resolve_rel(root, new_path)
    result = load_all(root)
    modified: list[str] = []
    for t in result.tethers:
        src_match = t.src.path == old_rel
        dst_match = t.dst.path == old_rel
        if not (src_match or dst_match):
            continue
        new_t = replace(
            t,
            src=replace(t.src, path=new_rel) if src_match else t.src,
            dst=replace(t.dst, path=new_rel) if dst_match else t.dst,
        )
        if new_t.src.path == new_t.dst.path:
            raise TetherError(
                f"mv would create self-tether on {t.id}; aborting (no records changed)"
            )
        save(root, new_t)
        modified.append(t.id)
    if not modified:
        click.echo(f"No tethers reference {old_rel}")
    else:
        click.echo(f"Rewrote {len(modified)} tether(s)")
        for tid in modified:
            click.echo(f"  {tid}")
    if result.errors:
        click.echo(f"(skipped {len(result.errors)} unreadable record(s))", err=True)


@main.command()
@click.argument("tether_id", required=False)
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON.")
@click.option(
    "--diff/--no-diff",
    default=None,
    help=(
        "Include unified diffs for DRIFTED (and normalization-rescued) artifacts. "
        "Default: on for single-tether view when state is non-HEALTHY or rescued."
    ),
)
@handle_errors
def status(tether_id: str | None, as_json: bool, diff: bool | None) -> None:
    """Report the status of tethers."""
    root = _root()

    if tether_id is not None:
        t = load(root, tether_id)
        check = check_tether(t, root)
        rescued = check.src.normalization_rescued or check.dst.normalization_rescued
        show_diff = (
            diff
            if diff is not None
            else (check.aggregate != AggregateState.HEALTHY or rescued)
        )
        ts = _build_tether_status(t, check, root, show_diff)
        if as_json:
            click.echo(encode_pretty(ts))
        else:
            click.echo(_one_tether_md(t, check, root, show_diff))
        return

    result = load_all(root)
    rows: list[Row] = [(t, check_tether(t, root)) for t in result.tethers]

    if as_json:
        click.echo(encode_pretty(_build_status_report(rows, result.errors, root)))
    else:
        click.echo(_all_tethers_md(rows, result.errors, root))


def _is_rescued(check: TetherCheck) -> bool:
    return check.src.normalization_rescued or check.dst.normalization_rescued


def _all_tethers_md(
    rows: list[Row],
    errors: list[tuple[Path, str]],
    root: Path,
) -> str:
    total = len(rows)
    if total == 0 and not errors:
        return "No tethers."

    c = counts(rows)
    if (
        c["HEALTHY"] == total
        and not errors
        and not any(_is_rescued(ck) for _, ck in rows)
    ):
        plural = "s" if total != 1 else ""
        return f"{total} tether{plural}, all HEALTHY."

    lines: list[str] = [summary_line(rows)]
    non_healthy = [r for r in rows if r[1].aggregate != AggregateState.HEALTHY]
    if non_healthy:
        lines.extend(["", "Needs attention:"])
        lines.extend(item_lines(non_healthy))

    rescued = [
        r
        for r in rows
        if r[1].aggregate == AggregateState.HEALTHY and _is_rescued(r[1])
    ]
    if rescued:
        lines.extend(
            ["", "Encoding-only drift (rescued by normalizer; no action required):"]
        )
        lines.extend(item_lines(rescued, with_description=False))

    lines.extend(errors_section(errors, root))
    return "\n".join(lines)


def _drift_block(
    label: str, path: str, fingerprint: str, root: Path, *, rescued: bool
) -> list[str]:
    header = (
        f"## Encoding-only drift on {label}: `{path}`"
        if rescued
        else f"## Drift on {label}: `{path}`"
    )
    body = [
        "",
        header,
    ]
    if rescued:
        body.append(
            "Bytes differ but normalize to the same value (line endings / trailing whitespace / "
            "BOM / leading-tab expansion). State is rescued to HEALTHY; `tether refresh <uuid>` "
            "would re-align the raw fingerprint."
        )
    body.extend(
        [
            "",
            "```diff",
            artifact_diff(path, fingerprint, root).rstrip("\n"),
            "```",
        ]
    )
    return body


def _broken_block(label: str, path: str, candidates: tuple[str, ...]) -> list[str]:
    lines = [
        "",
        f"## Broken {label}: `{path}` (file not present at recorded path)",
    ]
    if candidates:
        lines.append("")
        lines.append("Rename candidates (matched by fingerprint):")
        for p in candidates:
            lines.append(f"- `{p}`")
        lines.append("")
        lines.append(
            f"To follow a rename: `tether update --{label}-path <new>`, "
            "then `tether refresh <uuid>` once aligned."
        )
    return lines


def _one_tether_md(
    t: Tether,
    check: TetherCheck,
    root: Path,
    show_diff: bool,
) -> str:
    direction = "bidirectional" if t.bidirectional else "unidirectional"
    lines = [
        f"# Tether `{t.id}`",
        "",
        f"- **State:** {check.aggregate.value}",
        f"- **Type:** `{t.type}` ({direction})",
        f"- **src:** `{t.src.path}` — {check.src.state.value}"
        + (" (encoding-only drift rescued)" if check.src.normalization_rescued else ""),
        f"- **dst:** `{t.dst.path}` — {check.dst.state.value}"
        + (" (encoding-only drift rescued)" if check.dst.normalization_rescued else ""),
        f"- **Created:** {t.created_at}",
        f"- **Refreshed:** {t.refreshed_at}",
        f"- **Description:** {t.description or '(none)'}",
    ]
    if show_diff:
        for label, path, fingerprint, art in (
            ("src", t.src.path, t.src.fingerprint, check.src),
            ("dst", t.dst.path, t.dst.fingerprint, check.dst),
        ):
            if art.state == ArtifactState.DRIFTED:
                lines.extend(
                    _drift_block(label, path, fingerprint, root, rescued=False)
                )
            elif art.state == ArtifactState.HEALTHY and art.normalization_rescued:
                lines.extend(_drift_block(label, path, fingerprint, root, rescued=True))
            elif art.state == ArtifactState.BROKEN:
                lines.extend(_broken_block(label, path, art.rename_candidates))
    return "\n".join(lines)


def _build_artifact_status(
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
        diff = artifact_diff(a.path, a.fingerprint, root)
    return ArtifactStatus(
        path=a.path,
        fingerprint=a.fingerprint,
        state=art_check.state,
        diff=diff,
        normalization_rescued=art_check.normalization_rescued,
        rename_candidates=art_check.rename_candidates,
    )


def _build_tether_status(
    t: Tether,
    check: TetherCheck,
    root: Path,
    include_diff: bool,
) -> TetherStatus:
    return TetherStatus(
        id=t.id,
        schema_version=t.schema_version,
        type=t.type,
        bidirectional=t.bidirectional,
        description=t.description,
        created_at=t.created_at,
        refreshed_at=t.refreshed_at,
        src=_build_artifact_status(t.src, check.src, root, include_diff),
        dst=_build_artifact_status(t.dst, check.dst, root, include_diff),
        state=check.aggregate,
    )


def _build_status_report(
    rows: list[Row],
    errors: list[tuple[Path, str]],
    root: Path,
) -> StatusReport:
    c = counts(rows)
    summary = StatusSummary(
        total=len(rows),
        healthy=c["HEALTHY"],
        weakened=c["WEAKENED"],
        drifted=c["DRIFTED"],
        broken=c["BROKEN"],
    )
    error_objs: list[LoadError] = []
    for p, m in errors:
        if Path(p).is_absolute():
            try:
                rel = str(Path(p).relative_to(root))
            except ValueError:
                rel = str(p)
        else:
            rel = str(p)
        error_objs.append(LoadError(path=rel, error=m))
    return StatusReport(
        summary=summary,
        tethers=[_build_tether_status(t, ck, root, False) for t, ck in rows],
        errors=error_objs,
    )


@main.group()
def hook() -> None:
    """Hook subcommands invoked by external tools (Claude Code, etc.)."""


@hook.group("claude-code")
def hook_claude_code() -> None:
    """Claude Code hook subcommands."""


@hook_claude_code.command("session-start")
def hook_claude_code_session_start() -> None:
    from .claude_code.hooks import session_start

    session_start()


@hook_claude_code.command("stop")
def hook_claude_code_stop() -> None:
    from .claude_code.hooks import stop

    stop()
