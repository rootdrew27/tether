from __future__ import annotations

import json
import sys
from pathlib import Path

import msgspec
import pytest
from click.testing import CliRunner

from tether.claude_code.install import install
from tether.claude_code.settings import (
    ALLOW_PATTERNS,
    DENY_PATTERNS,
    build_session_start_hook,
    build_stop_hook,
    detect_tether_command,
    merge_local_settings,
    merge_project_settings,
)
from tether.cli import main


def _seed_files(project: Path) -> None:
    (project / "docs").mkdir()
    (project / "src").mkdir()
    (project / "docs" / "auth.md").write_text("# auth doc\n")
    (project / "src" / "auth.py").write_text("def auth(): pass\n")


def _hook_commands(entry: dict) -> list[str]:
    return [h.get("command", "") for h in entry.get("hooks", []) if isinstance(h, dict)]


def _has_owned_hook(entries: list[dict], suffix: str) -> bool:
    return any(cmd.endswith(suffix) for e in entries for cmd in _hook_commands(e))


def test_install_writes_fragment_and_claude_md(project: Path):
    install(project)
    assert (project / ".tether" / "tether.md").is_file()
    assert (project / "CLAUDE.md").read_text().strip() == "@.tether/tether.md"


def test_install_perms_in_settings_hooks_in_local(project: Path):
    install(project)
    s = json.loads((project / ".claude" / "settings.json").read_text())
    sl = json.loads((project / ".claude" / "settings.local.json").read_text())

    for p in DENY_PATTERNS:
        assert p in s["permissions"]["deny"]
    for p in ALLOW_PATTERNS:
        assert p in s["permissions"]["allow"]
    assert "hooks" not in s or not s.get("hooks")

    assert _has_owned_hook(
        sl["hooks"]["SessionStart"], "hook claude-code session-start"
    )
    assert _has_owned_hook(sl["hooks"]["Stop"], "hook claude-code stop")
    assert "permissions" not in sl or not sl.get("permissions")


def test_install_adds_settings_local_to_gitignore(project: Path):
    install(project)
    gi = (project / ".gitignore").read_text().splitlines()
    assert ".claude/settings.local.json" in {line.strip() for line in gi}


def test_install_gitignore_idempotent(project: Path):
    (project / ".gitignore").write_text(".claude/settings.local.json\nfoo\n")
    install(project)
    content = (project / ".gitignore").read_text()
    assert content.count(".claude/settings.local.json") == 1


def test_install_idempotent(project: Path):
    install(project)
    first_settings = (project / ".claude" / "settings.json").read_text()
    first_local = (project / ".claude" / "settings.local.json").read_text()
    install(project)
    assert (project / ".claude" / "settings.json").read_text() == first_settings
    assert (project / ".claude" / "settings.local.json").read_text() == first_local


def test_install_preserves_user_owned_settings_keys(project: Path):
    settings_path = project / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(
            {
                "model": "claude-opus-4",
                "permissions": {
                    "allow": ["Bash(ls:*)"],
                    "deny": ["Bash(rm -rf /:*)"],
                },
            }
        )
    )
    install(project)
    s = json.loads(settings_path.read_text())
    assert s["model"] == "claude-opus-4"
    assert "Bash(ls:*)" in s["permissions"]["allow"]
    assert "Bash(rm -rf /:*)" in s["permissions"]["deny"]


def test_install_replaces_stale_tether_hooks(project: Path):
    install(project)
    local_path = project / ".claude" / "settings.local.json"
    s = json.loads(local_path.read_text())
    s["hooks"]["SessionStart"].append(
        {
            "matcher": "*",
            "hooks": [
                {
                    "type": "command",
                    "command": "/old/path/tether hook claude-code session-start",
                }
            ],
        }
    )
    local_path.write_text(json.dumps(s))

    install(project)
    s2 = json.loads(local_path.read_text())
    tether_entries = [
        e
        for e in s2["hooks"]["SessionStart"]
        if any(
            "hook claude-code" in h.get("command", "")
            for h in e["hooks"]
            if isinstance(h, dict)
        )
    ]
    assert len(tether_entries) == 1
    assert "/old/path/tether" not in tether_entries[0]["hooks"][0]["command"]


def test_install_preserves_unrelated_hooks_in_local(project: Path):
    local_path = project / ".claude" / "settings.local.json"
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "*",
                            "hooks": [
                                {"type": "command", "command": "echo hello"},
                            ],
                        }
                    ]
                }
            }
        )
    )
    install(project)
    sl = json.loads(local_path.read_text())
    commands = [
        h["command"]
        for e in sl["hooks"]["SessionStart"]
        for h in e["hooks"]
        if isinstance(h, dict)
    ]
    assert "echo hello" in commands
    assert any("hook claude-code session-start" in c for c in commands)


def test_merge_project_settings_empty():
    result = merge_project_settings({})
    assert result.settings["permissions"]["deny"] == DENY_PATTERNS
    assert result.settings["permissions"]["allow"] == ALLOW_PATTERNS
    assert "hooks" not in result.settings
    assert result.changes


def test_merge_local_settings_embeds_command():
    result = merge_local_settings({}, "/abs/path/tether")
    sessionstart = result.settings["hooks"]["SessionStart"][0]
    stop = result.settings["hooks"]["Stop"][0]
    assert (
        sessionstart["hooks"][0]["command"]
        == "/abs/path/tether hook claude-code session-start"
    )
    assert stop["hooks"][0]["command"] == "/abs/path/tether hook claude-code stop"
    assert "permissions" not in result.settings


def test_build_hook_shape():
    h = build_session_start_hook("/x/tether")
    assert h["matcher"] == "*"
    assert h["hooks"][0]["timeout"] == 10
    assert h["hooks"][0]["type"] == "command"

    s = build_stop_hook("/x/tether")
    assert s["hooks"][0]["command"].endswith(" hook claude-code stop")


def test_detect_tether_command_anchors_inside_project(
    project: Path, monkeypatch: pytest.MonkeyPatch
):
    fake_bin = project / "bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python"
    fake_python.write_text("")
    fake_tether = fake_bin / "tether"
    fake_tether.write_text("")
    monkeypatch.setattr(sys, "executable", str(fake_python))

    cmd = detect_tether_command(project)
    assert cmd == "${CLAUDE_PROJECT_DIR}/bin/tether"


def test_detect_tether_command_absolute_for_external(
    project: Path,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
):
    external = tmp_path_factory.mktemp("external")
    fake_python = external / "python"
    fake_python.write_text("")
    fake_tether = external / "tether"
    fake_tether.write_text("")
    monkeypatch.setattr(sys, "executable", str(fake_python))

    cmd = detect_tether_command(project)
    assert cmd == str(fake_tether.resolve())


def _hook_input(cwd: Path) -> str:
    return json.dumps({"cwd": str(cwd), "session_id": "test"})


def test_session_start_silent_when_no_tethers(in_project: Path):
    result = CliRunner().invoke(
        main,
        ["hook", "claude-code", "session-start"],
        input=_hook_input(in_project),
    )
    assert result.exit_code == 0
    assert result.output.strip() == ""


def test_session_start_all_healthy_one_liner(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    runner.invoke(
        main,
        ["add", "docs/auth.md", "src/auth.py", "--description", "describes auth"],
    )
    result = runner.invoke(
        main,
        ["hook", "claude-code", "session-start"],
        input=_hook_input(in_project),
    )
    assert result.exit_code == 0
    assert "all HEALTHY" in result.output


def test_session_start_emits_markdown_on_drift(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    runner.invoke(
        main,
        ["add", "docs/auth.md", "src/auth.py", "--description", "describes auth"],
    )
    (in_project / "src" / "auth.py").write_text("def auth(token): pass\n")
    result = runner.invoke(
        main,
        ["hook", "claude-code", "session-start"],
        input=_hook_input(in_project),
    )
    assert result.exit_code == 0
    assert "## Tether status" in result.output
    assert "WEAKENED" in result.output


def test_stop_silent_when_all_healthy(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    runner.invoke(
        main,
        ["add", "docs/auth.md", "src/auth.py", "--description", "describes auth"],
    )
    result = runner.invoke(
        main,
        ["hook", "claude-code", "stop"],
        input=_hook_input(in_project),
    )
    assert result.exit_code == 0
    assert result.output.strip() == ""


def test_stop_emits_block_json_on_non_healthy(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    runner.invoke(
        main,
        ["add", "docs/auth.md", "src/auth.py", "--description", "describes auth"],
    )
    (in_project / "src" / "auth.py").write_text("def auth(token): pass\n")
    result = runner.invoke(
        main,
        ["hook", "claude-code", "stop"],
        input=_hook_input(in_project),
    )
    assert result.exit_code == 0
    payload = msgspec.json.decode(result.output.encode())
    assert payload["decision"] == "block"
    assert "WEAKENED" in payload["reason"]


def test_hook_empty_stdin_exits_2(in_project: Path):
    result = CliRunner().invoke(
        main,
        ["hook", "claude-code", "session-start"],
        input="",
    )
    assert result.exit_code == 2


def test_hook_missing_cwd_exits_2(in_project: Path):
    result = CliRunner().invoke(
        main,
        ["hook", "claude-code", "session-start"],
        input=json.dumps({}),
    )
    assert result.exit_code == 2
