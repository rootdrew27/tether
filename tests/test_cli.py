from __future__ import annotations

import json
from pathlib import Path

import msgspec
from click.testing import CliRunner

from tether.cli import main
from tether.model import Tether
from tether.storage import load_all


def _seed_files(project: Path) -> None:
    (project / "docs").mkdir()
    (project / "src").mkdir()
    (project / "docs" / "auth.md").write_text("# auth doc\n")
    (project / "src" / "auth.py").write_text("def auth(): pass\n")


def _add_tether(runner: CliRunner, description: str = "describes auth") -> str:
    result = runner.invoke(
        main,
        [
            "add",
            "docs/auth.md",
            "src/auth.py",
            "--description",
            description,
        ],
    )
    assert result.exit_code == 0, result.output
    return result.output.split()[-1]


def test_init_creates_tether_dir(tmp_path: Path, monkeypatch):
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(main, ["init"])
    assert result.exit_code == 0
    assert (tmp_path / ".tether" / "tethers").is_dir()


def test_init_refuses_outside_git(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(main, ["init"])
    assert result.exit_code == 1
    assert "git work tree" in result.output


def test_add_creates_record(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    tid = _add_tether(runner)
    records = list((in_project / ".tether" / "tethers").glob("*.json"))
    assert len(records) == 1
    assert records[0].name == f"{tid}.json"


def test_add_refuses_self_tether(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["add", "docs/auth.md", "docs/auth.md", "--description", "x"],
    )
    assert result.exit_code == 1
    assert "differ" in result.output


def test_add_requires_description(in_project: Path):
    _seed_files(in_project)
    result = CliRunner().invoke(
        main,
        ["add", "docs/auth.md", "src/auth.py"],
    )
    assert result.exit_code != 0
    assert "--description" in result.output


def test_add_refuses_empty_description(in_project: Path):
    _seed_files(in_project)
    result = CliRunner().invoke(
        main,
        ["add", "docs/auth.md", "src/auth.py", "--description", "   "],
    )
    assert result.exit_code == 1
    assert "non-empty" in result.output


def test_status_all_healthy(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    _add_tether(runner)
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0
    assert "all HEALTHY" in result.output


def test_status_weakened_after_drift(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    _add_tether(runner)
    (in_project / "src" / "auth.py").write_text("def auth(token): pass\n")
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0
    assert "WEAKENED" in result.output
    assert "(DRIFTED)" in result.output


def test_status_broken_after_rename(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    _add_tether(runner)
    (in_project / "src" / "auth.py").rename(in_project / "src" / "authentication.py")
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0
    assert "BROKEN" in result.output


def test_refresh_refuses_on_broken(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    tid = _add_tether(runner)
    (in_project / "src" / "auth.py").rename(in_project / "src" / "authentication.py")
    result = runner.invoke(main, ["refresh", tid])
    assert result.exit_code == 1
    assert "refuses on BROKEN" in result.output


def test_refresh_updates_fingerprint(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    tid = _add_tether(runner)
    [record] = list((in_project / ".tether" / "tethers").glob("*.json"))
    before = msgspec.json.decode(record.read_bytes(), type=Tether)

    (in_project / "src" / "auth.py").write_text("def auth(token): pass\n")
    result = runner.invoke(main, ["refresh", tid])
    assert result.exit_code == 0

    after = msgspec.json.decode(record.read_bytes(), type=Tether)
    assert after.b.fingerprint != before.b.fingerprint
    assert after.refreshed_at >= before.refreshed_at
    assert after.created_at == before.created_at


def test_mv_rewrites_paths(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    _add_tether(runner)
    (in_project / "src" / "auth.py").rename(in_project / "src" / "authentication.py")
    result = runner.invoke(main, ["mv", "src/auth.py", "src/authentication.py"])
    assert result.exit_code == 0
    assert "Rewrote 1" in result.output
    loaded = load_all(in_project).tethers[0]
    assert loaded.b.path == "src/authentication.py"


def test_update_description(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    tid = _add_tether(runner)
    result = runner.invoke(main, ["update", tid, "--description", "new description"])
    assert result.exit_code == 0
    loaded = load_all(in_project).tethers[0]
    assert loaded.description == "new description"


def test_update_rejects_empty_description(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    tid = _add_tether(runner)
    result = runner.invoke(main, ["update", tid, "--description", "   "])
    assert result.exit_code == 1
    assert "non-empty" in result.output


def test_update_requires_at_least_one_field(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    tid = _add_tether(runner)
    result = runner.invoke(main, ["update", tid])
    assert result.exit_code == 1
    assert "no fields to update" in result.output


def test_rm_deletes_record(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    tid = _add_tether(runner)
    result = runner.invoke(main, ["rm", tid])
    assert result.exit_code == 0
    assert list((in_project / ".tether" / "tethers").glob("*.json")) == []


def test_status_json_shape(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    _add_tether(runner)
    result = runner.invoke(main, ["status", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["summary"]["total"] == 1
    assert payload["summary"]["HEALTHY"] == 1
    assert payload["tethers"][0]["state"] == "HEALTHY"


def test_status_single_tether_json_shape(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    tid = _add_tether(runner)
    result = runner.invoke(main, ["status", tid, "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["id"] == tid
    assert payload["state"] == "HEALTHY"
