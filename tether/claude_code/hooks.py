from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, TypeVar

import msgspec

from ..errors import TetherError
from ..project import find_project_root
from ..render import (
    Row,
    counts,
    errors_section,
    item_lines,
    refs_xml,
    summary_line,
)
from ..status import AggregateState, check_all, check_tether
from ..storage import LoadTethersResult, find_by_path, load_all_tethers


class HookInput(msgspec.Struct, kw_only=True):
    cwd: str


class PreToolUseInput(msgspec.Struct, kw_only=True):
    cwd: str
    tool_name: str
    tool_input: dict[str, Any]


class StopBlock(msgspec.Struct, kw_only=True):
    decision: str
    reason: str


class PreToolUseHookSpecificOutput(msgspec.Struct, kw_only=True):
    hookEventName: str
    additionalContext: str


class PreToolUseOutput(msgspec.Struct, kw_only=True):
    hookSpecificOutput: PreToolUseHookSpecificOutput


T = TypeVar("T")


def _read_input(struct_type: type[T]) -> T:
    raw = sys.stdin.buffer.read()
    if not raw.strip():
        print("tether hook: stdin is empty (expected hook JSON)", file=sys.stderr)
        sys.exit(2)
    try:
        return msgspec.json.decode(raw, type=struct_type)
    except (msgspec.ValidationError, msgspec.DecodeError) as e:
        print(f"tether hook: invalid stdin JSON: {e}", file=sys.stderr)
        sys.exit(2)


def _resolve_cwd(cwd_str: str) -> Path:
    cwd = Path(cwd_str)
    if not cwd.exists():
        print(f"tether hook: cwd does not exist: {cwd_str}", file=sys.stderr)
        sys.exit(2)
    return cwd


def _evaluate(root: Path) -> tuple[LoadTethersResult, list[Row]]:
    result = load_all_tethers(root)
    checks = check_all(result.tethers, root)
    rows: list[Row] = [(t, ck) for t, ck in zip(result.tethers, checks)]
    return result, rows


def session_start() -> None:
    cwd = _resolve_cwd(_read_input(HookInput).cwd)
    try:
        root = find_project_root(cwd)
    except TetherError:
        sys.exit(0)

    result, rows = _evaluate(root)
    if not rows and not result.errors:
        sys.exit(0)

    c = counts(rows)
    total = len(rows)
    if total > 0 and c["HEALTHY"] == total and not result.errors:
        plural = "s" if total != 1 else ""
        print(f"tether: {total} tether{plural}, all HEALTHY.")
        return

    lines = ["## Tether status", "", summary_line(rows)]
    non_healthy = [r for r in rows if r[1].aggregate != AggregateState.HEALTHY]
    if non_healthy:
        lines.extend(["", "Needs attention:"])
        lines.extend(item_lines(non_healthy))
        lines.extend(["", "For diffs: `tether status <uuid>`"])
    lines.extend(errors_section(result.errors, root))
    print("\n".join(lines))


def stop() -> None:
    cwd = _resolve_cwd(_read_input(HookInput).cwd)
    try:
        root = find_project_root(cwd)
    except TetherError:
        sys.exit(0)

    result, rows = _evaluate(root)
    non_healthy = [r for r in rows if r[1].aggregate != AggregateState.HEALTHY]
    if not non_healthy and not result.errors:
        sys.exit(0)

    lines = ["## Stop blocked: tethers need attention", ""]
    if non_healthy:
        lines.extend(item_lines(non_healthy))
    lines.extend(errors_section(result.errors, root))
    lines.extend(
        [
            "",
            "For each entry above:",
            '- DRIFTED: align the file(s) to the description, OR run `tether update <uuid> --description "..."` to align the description to the files. Then `tether refresh <uuid>` to re-fingerprint.',
            "- BROKEN: run `tether status <uuid>` for the rename candidate, then `tether update --a-path/--b-path <new>` to follow it. If the file is truly gone, `tether rm <uuid>`.",
            "",
            "Do not refresh until alignment is real — refresh erases the drift signal.",
        ]
    )

    block = StopBlock(decision="block", reason="\n".join(lines))
    sys.stdout.write(msgspec.json.encode(block).decode("utf-8"))
    sys.stdout.write("\n")


def pre_tool_use() -> None:
    # Load errors from corrupt records are dropped here so PreRead does not
    # nag on every tool call; SessionStart and Stop surface them project-wide.
    data = _read_input(PreToolUseInput)
    if data.tool_name != "Read":
        return
    file_path = data.tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        return

    try:
        root = find_project_root(Path(data.cwd))
    except TetherError:
        return

    try:
        rel = Path(file_path).resolve().relative_to(root).as_posix()
    except (OSError, ValueError):
        return

    result = find_by_path(root, rel)
    if not result.tethers:
        return

    rows: list[Row] = [(t, check_tether(t, root)) for t in result.tethers]
    xml = refs_xml(rel, rows, [], root)
    output = PreToolUseOutput(
        hookSpecificOutput=PreToolUseHookSpecificOutput(
            hookEventName="PreToolUse",
            additionalContext=xml,
        )
    )
    sys.stdout.write(msgspec.json.encode(output).decode("utf-8"))
    sys.stdout.write("\n")
