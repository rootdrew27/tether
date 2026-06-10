from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..errors import TetherError
from ..project import init_project
from .fragment import FRAGMENT
from .skill import ONBOARD_SKILL
from .settings import (
    detect_tether_command,
    merge_local_settings,
    merge_project_settings,
)

CLAUDE_DIR = ".claude"
TETHER_DIR = ".tether"
FRAGMENT_NAME = "tether.md"
SKILLS_DIR = "skills"
ONBOARD_SKILL_DIR = "tether-onboard"
SKILL_NAME = "SKILL.md"
SETTINGS_NAME = "settings.json"
SETTINGS_LOCAL_NAME = "settings.local.json"
CLAUDE_MD = "CLAUDE.md"
IMPORT_LINE = "@.tether/tether.md"
GITIGNORE_NAME = ".gitignore"
SETTINGS_LOCAL_GITIGNORE_ENTRY = ".claude/settings.local.json"


def install(start: Path) -> list[str]:
    report: list[str] = []
    root = init_project(start)
    report.append(f"Initialized tether project at {root / TETHER_DIR}")

    claude_dir = root / CLAUDE_DIR
    claude_dir.mkdir(parents=True, exist_ok=True)

    fragment_path = root / TETHER_DIR / FRAGMENT_NAME
    fragment_path.write_text(FRAGMENT)
    report.append(f"Wrote {fragment_path.relative_to(root)}")

    skill_path = claude_dir / SKILLS_DIR / ONBOARD_SKILL_DIR / SKILL_NAME
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(ONBOARD_SKILL)
    report.append(f"Wrote {skill_path.relative_to(root)}")

    claude_md = root / CLAUDE_MD
    if claude_md.exists():
        content = claude_md.read_text()
        if IMPORT_LINE not in content:
            sep = "" if content.endswith("\n") or not content else "\n"
            claude_md.write_text(content + sep + IMPORT_LINE + "\n")
            report.append(f"Appended `{IMPORT_LINE}` to {CLAUDE_MD}")
        else:
            report.append(f"{CLAUDE_MD} already imports `{IMPORT_LINE}`")
    else:
        claude_md.write_text(IMPORT_LINE + "\n")
        report.append(f"Created {CLAUDE_MD} with `{IMPORT_LINE}`")

    settings_path = claude_dir / SETTINGS_NAME
    project_current = _read_json_object(settings_path)
    project_result = merge_project_settings(project_current)
    settings_path.write_text(json.dumps(project_result.settings, indent=2) + "\n")
    report.append(f"Updated {settings_path.relative_to(root)}:")
    for c in project_result.changes:
        report.append(f"  - {c}")

    tether_cmd = detect_tether_command(root)
    local_path = claude_dir / SETTINGS_LOCAL_NAME
    local_current = _read_json_object(local_path)
    local_result = merge_local_settings(local_current, tether_cmd)
    local_path.write_text(json.dumps(local_result.settings, indent=2) + "\n")
    report.append(f"Updated {local_path.relative_to(root)}:")
    for c in local_result.changes:
        report.append(f"  - {c}")
    report.append(f"  - hook command resolved to `{tether_cmd}`")

    gitignore_msg = _ensure_gitignored(root, SETTINGS_LOCAL_GITIGNORE_ENTRY)
    if gitignore_msg:
        report.append(gitignore_msg)

    return report


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text() or "{}")
    except json.JSONDecodeError as e:
        raise TetherError(f"{path}: invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise TetherError(f"{path}: top level must be a JSON object")
    return data


def _ensure_gitignored(project_root: Path, entry: str) -> str | None:
    gi_path = project_root / GITIGNORE_NAME
    if gi_path.exists():
        content = gi_path.read_text()
        existing = {line.strip() for line in content.splitlines()}
        if entry in existing:
            return None
        sep = "" if content.endswith("\n") or not content else "\n"
        gi_path.write_text(content + sep + entry + "\n")
        return f"Appended `{entry}` to {GITIGNORE_NAME}"
    gi_path.write_text(entry + "\n")
    return f"Created {GITIGNORE_NAME} with `{entry}`"
