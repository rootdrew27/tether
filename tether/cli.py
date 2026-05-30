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
from .model import Artifact, Tether
from .output import (
    ArtifactStatus,
    RefsReport,
    StatusReport,
    StatusSummary,
    TetherStatus,
    encode_pretty,
    relativize_errors,
)
from .project import find_project_root, init_project
from .render import (
    Row,
    counts,
    errors_section,
    item_lines,
    refs_xml,
    show_text,
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
from .storage import find_by_path, load, load_all, save

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
    """tether: content-fingerprinted relationship annotation layer."""


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
@click.argument("a_path")
@click.argument("b_path")
@click.option(
    "--description",
    required=True,
    help="Required free-form description of why the relationship exists.",
)
@handle_errors
def add(a_path: str, b_path: str, description: str) -> None:
    """Create a new tether between two existing files."""
    if not description.strip():
        raise TetherError("--description must be non-empty")
    root = _root()
    a_rel = _resolve_rel(root, a_path)
    b_rel = _resolve_rel(root, b_path)
    if a_rel == b_rel:
        raise TetherError("a and b must differ; self-tethers are not allowed")

    a_abs = root / a_rel
    b_abs = root / b_rel
    if not a_abs.is_file():
        raise TetherError(f"file does not exist: {a_rel}")
    if not b_abs.is_file():
        raise TetherError(f"file does not exist: {b_rel}")

    a_fp = hash_object_write(a_abs, root)
    b_fp = hash_object_write(b_abs, root)

    now = _utcnow_iso()
    t = Tether(
        id=str(uuid7()),
        schema_version=1,
        a=Artifact(path=a_rel, fingerprint=a_fp),
        b=Artifact(path=b_rel, fingerprint=b_fp),
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
    if ArtifactState.BROKEN in (check.a.state, check.b.state):
        raise TetherError(
            "refresh refuses on BROKEN tether — locator does not resolve. "
            "Use `tether update --a-path/--b-path` to follow the rename first."
        )
    new_t = replace(
        t,
        a=replace(t.a, fingerprint=hash_object_write(root / t.a.path, root)),
        b=replace(t.b, fingerprint=hash_object_write(root / t.b.path, root)),
        refreshed_at=_utcnow_iso(),
    )
    save(root, new_t)
    click.echo(f"Refreshed tether {tether_id}")


@main.command()
@click.argument("tether_id")
@click.option("--a-path", "new_a_path", default=None)
@click.option("--b-path", "new_b_path", default=None)
@click.option("--description", "new_description", default=None)
@handle_errors
def update(
    tether_id: str,
    new_a_path: str | None,
    new_b_path: str | None,
    new_description: str | None,
) -> None:
    """Modify a tether's path or description without touching fingerprints."""
    if all(v is None for v in (new_a_path, new_b_path, new_description)):
        raise TetherError(
            "no fields to update; pass --a-path, --b-path, or --description"
        )
    if new_description is not None and not new_description.strip():
        raise TetherError("--description must be non-empty")
    root = _root()
    t = load(root, tether_id)
    changes: dict[str, Any] = {}
    if new_a_path is not None:
        changes["a"] = replace(t.a, path=_resolve_rel(root, new_a_path))
    if new_b_path is not None:
        changes["b"] = replace(t.b, path=_resolve_rel(root, new_b_path))
    if new_description is not None:
        changes["description"] = new_description
    new_t = replace(t, **changes)
    if new_t.a.path == new_t.b.path:
        raise TetherError("a and b must differ after update")
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
        a_match = t.a.path == old_rel
        b_match = t.b.path == old_rel
        if not (a_match or b_match):
            continue
        new_t = replace(
            t,
            a=replace(t.a, path=new_rel) if a_match else t.a,
            b=replace(t.b, path=new_rel) if b_match else t.b,
        )
        if new_t.a.path == new_t.b.path:
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
        rescued = check.a.normalization_rescued or check.b.normalization_rescued
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
    return check.a.normalization_rescued or check.b.normalization_rescued


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
    lines = [
        f"# Tether `{t.id}`",
        "",
        f"- **State:** {check.aggregate.value}",
        f"- **a:** `{t.a.path}` — {check.a.state.value}"
        + (" (encoding-only drift rescued)" if check.a.normalization_rescued else ""),
        f"- **b:** `{t.b.path}` — {check.b.state.value}"
        + (" (encoding-only drift rescued)" if check.b.normalization_rescued else ""),
        f"- **Created:** {t.created_at}",
        f"- **Refreshed:** {t.refreshed_at}",
        f"- **Description:** {t.description}",
    ]
    if show_diff:
        for label, path, fingerprint, art in (
            ("a", t.a.path, t.a.fingerprint, check.a),
            ("b", t.b.path, t.b.fingerprint, check.b),
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
        description=t.description,
        created_at=t.created_at,
        refreshed_at=t.refreshed_at,
        a=_build_artifact_status(t.a, check.a, root, include_diff),
        b=_build_artifact_status(t.b, check.b, root, include_diff),
        state=check.aggregate,
    )


def _build_status_summary(rows: list[Row]) -> StatusSummary:
    c = counts(rows)
    return StatusSummary(
        total=len(rows),
        healthy=c["HEALTHY"],
        weakened=c["WEAKENED"],
        drifted=c["DRIFTED"],
        broken=c["BROKEN"],
    )


def _build_status_report(
    rows: list[Row],
    errors: list[tuple[Path, str]],
    root: Path,
) -> StatusReport:
    return StatusReport(
        summary=_build_status_summary(rows),
        tethers=[_build_tether_status(t, ck, root, False) for t, ck in rows],
        errors=relativize_errors(errors, root),
    )


@main.command()
@click.argument("path")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Emit JSON (default when no format flag is given).",
)
@click.option(
    "--xml",
    "as_xml",
    is_flag=True,
    default=False,
    help="Emit XML (the format injected into Claude Code on PreToolUse Read).",
)
@handle_errors
def refs(path: str, as_json: bool, as_xml: bool) -> None:
    """List tethers referencing PATH (severity-ordered)."""
    if as_json and as_xml:
        raise TetherError("--json and --xml are mutually exclusive")
    root = _root()
    rel = _resolve_rel(root, path)
    result = find_by_path(root, rel)
    rows: list[Row] = [(t, check_tether(t, root)) for t in result.tethers]

    if as_xml:
        click.echo(refs_xml(rel, rows, result.errors, root), nl=False)
        return
    click.echo(encode_pretty(_build_refs_report(rel, rows, result.errors, root)))


def _build_refs_report(
    rel: str,
    rows: list[Row],
    errors: list[tuple[Path, str]],
    root: Path,
) -> RefsReport:
    return RefsReport(
        queried_path=rel,
        summary=_build_status_summary(rows),
        tethers=[_build_tether_status(t, ck, root, False) for t, ck in rows],
        errors=relativize_errors(errors, root),
    )


@main.command()
@handle_errors
def show() -> None:
    """List every tether with its description."""
    root = _root()
    result = load_all(root)
    text = show_text(result.tethers, result.errors, root)
    if sys.stdout.isatty():
        click.echo_via_pager(text + "\n")
    else:
        click.echo(text)


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


@hook_claude_code.command("pre-tool-use")
def hook_claude_code_pre_tool_use() -> None:
    from .claude_code.hooks import pre_tool_use

    pre_tool_use()
