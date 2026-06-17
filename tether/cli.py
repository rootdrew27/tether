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
from .git import hash_object_write, hash_object_write_bytes
from .locators import extract_region
from .model import Artifact, Locator, RegionFingerprint, Tether
from .coverage import compute_coverage
from .output import (
    build_coverage_report,
    build_refs_report,
    build_status_report,
    build_tether_status,
    encode_pretty,
)
from .pretty import (
    make_console,
    pretty_refs,
    pretty_show,
    pretty_status_all,
    pretty_status_one,
)
from .project import find_project_root, init_project
from .render import Row, all_tethers_md, coverage_md, one_tether_md, refs_md, show_text
from .status import AggregateState, ArtifactState, check_all, check_tether
from uuid_utils import uuid7

from .storage import delete_tether, load_all_tethers
from .storage import find_by_path, load_tether, save_tether

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


# File extension → locator language, and language → locator kind. This build
# resolves Python symbols; markdown sections are the next language to land.
# Inference happens only at `add` time; the chosen lang is stored in the record,
# so a later rename never silently re-infers from a new extension.
_LANG_BY_EXT: dict[str, str] = {
    ".py": "python",
    ".md": "markdown",
    ".markdown": "markdown",
}
_KIND_BY_LANG: dict[str, str] = {"python": "symbol", "markdown": "heading"}


def _split_selector(arg: str) -> tuple[str, str | None]:
    """Split a `path::selector` argument. No `::` → whole file (selector None)."""
    path, sep, selector = arg.partition("::")
    if not sep:
        return arg, None
    if not selector.strip():
        raise TetherError(f"empty selector after '::' in {arg!r}")
    return path, selector


def _make_locator(rel: str, selector: str) -> Locator:
    ext = Path(rel).suffix
    lang = _LANG_BY_EXT.get(ext)
    if lang is None:
        supported = ", ".join(sorted(_LANG_BY_EXT))
        raise TetherError(
            f"no section-locator parser for {ext or '(no extension)'} files "
            f"(supported: {supported})"
        )
    return Locator(kind=_KIND_BY_LANG[lang], lang=lang, selector=selector)


def _fingerprint_artifact(
    root: Path, rel: str, locator: Locator | None
) -> str | RegionFingerprint:
    """Record the fingerprint for an artifact, writing bytes into git's store.

    Whole-file → the file's blob OID. Region → a pair: the file's blob OID (for
    file-rename detection) plus the region's own blob OID (the drift signal).
    Raises a LocatorError (a TetherError) if the region cannot be extracted.
    """
    abs_path = root / rel
    file_oid = hash_object_write(abs_path, root)
    if locator is None:
        return file_oid
    region = extract_region(abs_path.read_bytes(), locator)
    region_hash = hash_object_write_bytes(region, root)
    return RegionFingerprint(file_blob_oid=file_oid, region_hash=region_hash)


def _surface(*, as_json: bool, plain: bool, is_tty: bool, json_default: bool) -> str:
    """Pick the output surface for a dual human/agent command.

    Explicit flags win; otherwise a TTY gets the Rich `pretty` view and a pipe
    gets the plain text an agent or script expects — `json` for refs (its
    agent contract), `plain` markdown for status. Keeping this pure makes the
    routing trivially testable without simulating a terminal.
    """
    if as_json:
        return "json"
    if plain:
        return "plain"
    if is_tty:
        return "pretty"
    return "json" if json_default else "plain"


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
    """Create a new tether between two existing files or regions.

    Each argument is a path, optionally with a `::selector` suffix naming a
    region (e.g. `src/calc.py::Calculator.multiply`).
    """
    if not description.strip():
        raise TetherError("--description must be non-empty")
    root = _root()
    a_raw, a_sel = _split_selector(a_path)
    b_raw, b_sel = _split_selector(b_path)
    a_rel = _resolve_rel(root, a_raw)
    b_rel = _resolve_rel(root, b_raw)
    a_loc = _make_locator(a_rel, a_sel) if a_sel is not None else None
    b_loc = _make_locator(b_rel, b_sel) if b_sel is not None else None
    if a_rel == b_rel and a_loc == b_loc:
        raise TetherError(
            "a and b address the same content; self-tethers are not allowed"
        )

    if not (root / a_rel).is_file():
        raise TetherError(f"file does not exist: {a_rel}")
    if not (root / b_rel).is_file():
        raise TetherError(f"file does not exist: {b_rel}")

    a_fp = _fingerprint_artifact(root, a_rel, a_loc)
    b_fp = _fingerprint_artifact(root, b_rel, b_loc)

    now = _utcnow_iso()
    t = Tether(
        id=str(uuid7()),
        schema_version=2 if (a_loc or b_loc) else 1,
        a=Artifact(path=a_rel, fingerprint=a_fp, locator=a_loc),
        b=Artifact(path=b_rel, fingerprint=b_fp, locator=b_loc),
        description=description,
        created_at=now,
        refreshed_at=now,
    )
    save_tether(root, t)
    click.echo(f"Created tether {t.id}")


@main.command()
@click.argument("tether_id")
@handle_errors
def rm(tether_id: str) -> None:
    """Delete a tether record."""
    delete_tether(_root(), tether_id)
    click.echo(f"Removed tether {tether_id}")


@main.command()
@click.argument("tether_id")
@handle_errors
def refresh(tether_id: str) -> None:
    """Re-fingerprint both artifacts, asserting they are aligned."""
    root = _root()
    t = load_tether(root, tether_id)
    check = check_tether(t, root)
    if ArtifactState.BROKEN in (check.a.state, check.b.state):
        raise TetherError(
            "refresh refuses on BROKEN tether — locator does not resolve. "
            "Use `tether update --a-path/--b-path` (or --a-selector/--b-selector) "
            "to follow the move first."
        )
    new_t = replace(
        t,
        a=replace(t.a, fingerprint=_fingerprint_artifact(root, t.a.path, t.a.locator)),
        b=replace(t.b, fingerprint=_fingerprint_artifact(root, t.b.path, t.b.locator)),
        refreshed_at=_utcnow_iso(),
    )
    save_tether(root, new_t)
    click.echo(f"Refreshed tether {tether_id}")


def _retarget(
    art: Artifact,
    new_path: str | None,
    new_selector: str | None,
    root: Path,
    label: str,
) -> Artifact:
    """Apply a structural path/selector change to one artifact (no re-fingerprint)."""
    if new_path is not None:
        art = replace(art, path=_resolve_rel(root, new_path))
    if new_selector is not None:
        if art.locator is None:
            raise TetherError(
                f"--{label}-selector: artifact {label} has no locator to retarget"
            )
        art = replace(art, locator=replace(art.locator, selector=new_selector))
    return art


@main.command()
@click.argument("tether_id")
@click.option("--a-path", "new_a_path", default=None)
@click.option("--b-path", "new_b_path", default=None)
@click.option("--a-selector", "new_a_selector", default=None)
@click.option("--b-selector", "new_b_selector", default=None)
@click.option("--description", "new_description", default=None)
@handle_errors
def update(
    tether_id: str,
    new_a_path: str | None,
    new_b_path: str | None,
    new_a_selector: str | None,
    new_b_selector: str | None,
    new_description: str | None,
) -> None:
    """Modify a tether's path, locator, or description without touching fingerprints."""
    fields = (
        new_a_path,
        new_b_path,
        new_a_selector,
        new_b_selector,
        new_description,
    )
    if all(v is None for v in fields):
        raise TetherError(
            "no fields to update; pass --a-path/--b-path, "
            "--a-selector/--b-selector, or --description"
        )
    if new_description is not None and not new_description.strip():
        raise TetherError("--description must be non-empty")
    for label, sel in (("a", new_a_selector), ("b", new_b_selector)):
        if sel is not None and not sel.strip():
            raise TetherError(f"--{label}-selector must be non-empty")
    root = _root()
    t = load_tether(root, tether_id)
    changes: dict[str, Any] = {
        "a": _retarget(t.a, new_a_path, new_a_selector, root, "a"),
        "b": _retarget(t.b, new_b_path, new_b_selector, root, "b"),
    }
    if new_description is not None:
        changes["description"] = new_description
    new_t = replace(t, **changes)
    if new_t.a.path == new_t.b.path and new_t.a.locator == new_t.b.locator:
        raise TetherError("a and b must address different content after update")
    save_tether(root, new_t)
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
    result = load_all_tethers(root)
    rewritten: list[Tether] = []
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
        rewritten.append(new_t)
    for new_t in rewritten:
        save_tether(root, new_t)
    if not rewritten:
        click.echo(f"No tethers reference {old_rel}")
    else:
        click.echo(f"Rewrote {len(rewritten)} tether(s)")
        for new_t in rewritten:
            click.echo(f"  {new_t.id}")
    if result.errors:
        click.echo(f"(skipped {len(result.errors)} unreadable record(s))", err=True)


@main.command()
@click.argument("tether_id", required=False)
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON.")
@click.option(
    "--plain",
    is_flag=True,
    default=False,
    help="Force plain markdown (no color or layout); the default when piped.",
)
@click.option(
    "--no-color",
    "no_color",
    is_flag=True,
    default=False,
    help="Disable color in the pretty (TTY) view.",
)
@click.option(
    "--diff/--no-diff",
    default=None,
    help=(
        "Include unified diffs for DRIFTED (and normalization-rescued) artifacts. "
        "Default: on for single-tether view when state is non-HEALTHY or rescued."
    ),
)
@handle_errors
def status(
    tether_id: str | None,
    as_json: bool,
    plain: bool,
    no_color: bool,
    diff: bool | None,
) -> None:
    """Report the status of tethers."""
    root = _root()
    surface = _surface(
        as_json=as_json, plain=plain, is_tty=sys.stdout.isatty(), json_default=False
    )

    if tether_id is not None:
        t = load_tether(root, tether_id)
        check = check_all([t], root)[0]
        rescued = check.a.normalization_rescued or check.b.normalization_rescued
        show_diff = (
            diff
            if diff is not None
            else (check.aggregate != AggregateState.HEALTHY or rescued)
        )
        if surface == "json":
            click.echo(encode_pretty(build_tether_status(t, check, root, show_diff)))
        elif surface == "pretty":
            pretty_status_one(
                make_console(no_color=no_color), t, check, root, show_diff
            )
        else:
            click.echo(one_tether_md(t, check, root, show_diff))
        return

    result = load_all_tethers(root)
    checks = check_all(result.tethers, root)
    rows: list[Row] = [(t, ck) for t, ck in zip(result.tethers, checks)]

    if surface == "json":
        click.echo(encode_pretty(build_status_report(rows, result.errors, root)))
    elif surface == "pretty":
        pretty_status_all(make_console(no_color=no_color), rows, result.errors, root)
    else:
        click.echo(all_tethers_md(rows, result.errors, root))


@main.command()
@click.argument("path")
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON.")
@click.option(
    "--plain",
    is_flag=True,
    default=False,
    help="Force plain markdown (no color or layout).",
)
@click.option(
    "--no-color",
    "no_color",
    is_flag=True,
    default=False,
    help="Disable color in the pretty (TTY) view.",
)
@handle_errors
def refs(path: str, as_json: bool, plain: bool, no_color: bool) -> None:
    """List tethers referencing PATH, severity-ordered, with drift state.

    State-aware: the pretty (TTY) view tints each panel border by aggregate
    state (with a color key); the JSON (piped, the agent path) carries
    per-artifact and aggregate state.
    """
    root = _root()
    # A `::selector` suffix is accepted but only the file path is matched;
    # region-scoped refs are future work.
    raw, _ = _split_selector(path)
    rel = _resolve_rel(root, raw)
    result = find_by_path(root, rel)
    checks = check_all(result.tethers, root)
    rows: list[Row] = [(t, ck) for t, ck in zip(result.tethers, checks)]
    surface = _surface(
        as_json=as_json, plain=plain, is_tty=sys.stdout.isatty(), json_default=True
    )

    if surface == "json":
        click.echo(encode_pretty(build_refs_report(rel, rows, result.errors, root)))
    elif surface == "pretty":
        pretty_refs(make_console(no_color=no_color), rel, rows, result.errors, root)
    else:
        click.echo(refs_md(rel, rows, result.errors, root))


@main.command()
@click.option(
    "--plain",
    is_flag=True,
    default=False,
    help="Force plain markdown (no color or layout).",
)
@click.option(
    "--no-color",
    "no_color",
    is_flag=True,
    default=False,
    help="Disable color in the pretty (TTY) view.",
)
@handle_errors
def show(plain: bool, no_color: bool) -> None:
    """List every tether with its description. Structural only — no drift state.

    Reads records from disk without computing drift or touching git, so the
    pretty (TTY) view is deliberately neutral (no state color). For drift use
    `tether status`.
    """
    root = _root()
    result = load_all_tethers(root)

    if plain or not sys.stdout.isatty():
        click.echo(show_text(result.tethers, result.errors, root))
        return

    # Print straight to the terminal — no pager. Rich's pager routes through
    # pydoc, which never passes `less -R`, so a non-`-R` pager renders the ANSI
    # as literal `ESC[...]` junk. Direct printing keeps the color correct; the
    # terminal's own scrollback covers long catalogs.
    pretty_show(make_console(no_color=no_color), result.tethers, result.errors, root)


@main.command()
@click.option(
    "--list-untethered-files",
    "list_untethered",
    is_flag=True,
    default=False,
    help="List the tracked files no tether references.",
)
@click.option(
    "--list-tethered-files",
    "list_tethered",
    is_flag=True,
    default=False,
    help="List the tracked files referenced by at least one tether.",
)
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON.")
@handle_errors
def coverage(list_untethered: bool, list_tethered: bool, as_json: bool) -> None:
    """Report what fraction of git-tracked files participate in a tether."""
    root = _root()
    cov = compute_coverage(root)
    if as_json:
        report = build_coverage_report(
            cov, root, list_tethered=list_tethered, list_untethered=list_untethered
        )
        click.echo(encode_pretty(report))
    else:
        click.echo(
            coverage_md(
                cov, root, list_tethered=list_tethered, list_untethered=list_untethered
            )
        )


@main.group(hidden=True)
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
