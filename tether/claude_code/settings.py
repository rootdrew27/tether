from __future__ import annotations

import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import msgspec

from ..errors import TetherError

# The editing tools tether denies on its state directory. Both the canonical
# deny patterns and the ownership predicate derive from this tuple.
_DENY_TOOLS: tuple[str, ...] = ("Edit", "Write", "MultiEdit", "NotebookEdit")

DENY_PATTERNS: list[str] = [f"{tool}(.tether/**)" for tool in _DENY_TOOLS]

ALLOW_SUBCOMMANDS: list[str] = [
    "status",
    "refresh",
    "update",
    "add",
    "mv",
    "refs",
    "show",
]

ALLOW_INVOCATIONS: list[str] = [
    "tether",
    "uv run tether",
    "poetry run tether",
    "conda run -n * tether",
    ".venv/bin/tether",
    "${CLAUDE_PROJECT_DIR}/.venv/bin/tether",
]

ALLOW_PATTERNS: list[str] = [
    f"Bash({inv} {sub}:*)" for inv in ALLOW_INVOCATIONS for sub in ALLOW_SUBCOMMANDS
]

_ALLOW_PATTERN_SET: frozenset[str] = frozenset(ALLOW_PATTERNS)


def detect_tether_command(project_root: Path) -> str:
    """Return the command prefix to invoke tether from a Claude Code hook.

    Looks for the tether binary adjacent to the current Python interpreter
    first, falling back to a PATH lookup. If the resolved binary lives inside
    the project root, returns a ``${CLAUDE_PROJECT_DIR}``-anchored path;
    otherwise the absolute path.
    """
    candidate = Path(sys.executable).parent / "tether"
    if not candidate.exists():
        which_result = shutil.which("tether")
        if which_result is None:
            raise TetherError(
                "Could not locate the `tether` binary. "
                "Install tether (e.g. `uv sync` or `pipx install tether`) "
                "before running `tether init claude-code`."
            )
        candidate = Path(which_result)

    candidate = candidate.resolve()
    project_root = project_root.resolve()

    try:
        rel = candidate.relative_to(project_root)
        return f"${{CLAUDE_PROJECT_DIR}}/{rel.as_posix()}"
    except ValueError:
        return str(candidate)


# (settings key, `tether hook claude-code` subcommand, tool matcher) for each
# tether-owned hook.
HOOK_EVENTS: tuple[tuple[str, str, str], ...] = (
    ("SessionStart", "session-start", "*"),
    ("Stop", "stop", "*"),
    ("PreToolUse", "pre-tool-use", "Read"),
)


def build_hook_entry(tether_cmd: str, subcommand: str, matcher: str) -> dict[str, Any]:
    return {
        "matcher": matcher,
        "hooks": [
            {
                "type": "command",
                "command": f"{tether_cmd} hook claude-code {subcommand}",
                "timeout": 10,
            }
        ],
    }


def _is_tether_owned_deny(s: str) -> bool:
    # Owned iff the rule is one of tether's editing tools targeting a .tether/
    # path — catches the canonical patterns plus stale narrower forms (e.g.
    # Edit(.tether/tethers/**)) without touching user rules for other tools
    # (e.g. Read(.tether/secrets/**), Bash(rm .tether/**)).
    return any(s.startswith(f"{tool}(.tether/") for tool in _DENY_TOOLS)


def _is_tether_owned_allow(s: str) -> bool:
    return s in _ALLOW_PATTERN_SET


def _is_tether_owned_hook(entry: dict[str, Any]) -> bool:
    for h in entry.get("hooks", []):
        cmd = h.get("command", "") if isinstance(h, dict) else ""
        if isinstance(cmd, str) and "hook claude-code" in cmd:
            return True
    return False


class MergeResult(msgspec.Struct, frozen=True, kw_only=True):
    settings: dict[str, Any]
    changes: list[str]


T = TypeVar("T")


def _replace_owned(
    items: list[T],
    is_owned: Callable[[T], bool],
    owned: list[T],
) -> tuple[list[T], int]:
    kept = [x for x in items if not is_owned(x)]
    return kept + owned, len(items) - len(kept)


def _change_msg(noun: str, count: int | None, removed: int) -> str:
    verb = "replaced" if removed else "added"
    base = f"{verb} {noun}" if count is None else f"{verb} {count} {noun}"
    return base + (f" (removed {removed} stale)" if removed else "")


def merge_project_settings(current: dict[str, Any]) -> MergeResult:
    """Merge tether-owned permissions into committed `.claude/settings.json`.

    Hooks are intentionally excluded — they carry machine-specific paths and
    belong in `.claude/settings.local.json` instead.
    """
    out = dict(current)
    changes: list[str] = []

    perms = dict(out.get("permissions", {}))
    for perm_key, patterns, predicate in (
        ("deny", DENY_PATTERNS, _is_tether_owned_deny),
        ("allow", ALLOW_PATTERNS, _is_tether_owned_allow),
    ):
        merged, removed = _replace_owned(
            list(perms.get(perm_key, [])), predicate, list(patterns)
        )
        perms[perm_key] = merged
        changes.append(_change_msg(f"{perm_key} rule(s)", len(patterns), removed))
    out["permissions"] = perms

    return MergeResult(settings=out, changes=changes)


def merge_local_settings(current: dict[str, Any], tether_cmd: str) -> MergeResult:
    """Merge tether-owned hooks into gitignored `.claude/settings.local.json`.

    The hook command embeds the detected tether binary path so it works
    regardless of whether `tether` is on the shell's PATH at hook-fire time.
    """
    out = dict(current)
    changes: list[str] = []

    hooks = dict(out.get("hooks", {}))
    for key, subcommand, matcher in HOOK_EVENTS:
        hook_entry = build_hook_entry(tether_cmd, subcommand, matcher)
        merged, removed = _replace_owned(
            list(hooks.get(key, [])), _is_tether_owned_hook, [hook_entry]
        )
        hooks[key] = merged
        changes.append(_change_msg(f"{key} hook", None, removed))
    out["hooks"] = hooks

    return MergeResult(settings=out, changes=changes)
