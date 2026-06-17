from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from tether.cli import main


def _seed_files(project: Path) -> None:
    (project / "docs").mkdir()
    (project / "src").mkdir()
    (project / "tests").mkdir()
    (project / "docs" / "auth.md").write_text("# auth doc\n")
    (project / "docs" / "billing.md").write_text("# billing doc\n")
    (project / "src" / "auth.py").write_text("def auth(): pass\n")
    (project / "src" / "billing.py").write_text("def bill(): pass\n")
    (project / "tests" / "test_auth.py").write_text("def test_auth(): pass\n")


def _add(runner: CliRunner, a: str, b: str, description: str) -> str:
    result = runner.invoke(
        main,
        ["add", a, b, "--description", description],
    )
    assert result.exit_code == 0, result.output
    return result.output.split()[-1]


def test_refs_empty_result_json(in_project: Path):
    _seed_files(in_project)
    result = CliRunner().invoke(main, ["refs", "src/auth.py"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["queried_path"] == "src/auth.py"
    assert payload["summary"]["total"] == 0
    assert payload["tethers"] == []
    assert payload["errors"] == []


def test_refs_empty_result_plain(in_project: Path):
    _seed_files(in_project)
    result = CliRunner().invoke(main, ["refs", "src/auth.py", "--plain"])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "No tethers reference `src/auth.py`."


def test_refs_single_match_a_side(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    tid = _add(runner, "docs/auth.md", "src/auth.py", "describes auth")
    result = runner.invoke(main, ["refs", "docs/auth.md"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["summary"]["total"] == 1
    assert payload["tethers"][0]["id"] == tid
    assert payload["tethers"][0]["a"]["path"] == "docs/auth.md"
    assert payload["tethers"][0]["b"]["path"] == "src/auth.py"


def test_refs_single_match_b_side(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    tid = _add(runner, "docs/auth.md", "src/auth.py", "describes auth")
    result = runner.invoke(main, ["refs", "src/auth.py"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["summary"]["total"] == 1
    assert payload["tethers"][0]["id"] == tid


def test_refs_multi_match_severity_order_json(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    # tether 1: src/auth.py <-> docs/auth.md (will be HEALTHY)
    _add(runner, "src/auth.py", "docs/auth.md", "auth doc")
    # tether 2: src/auth.py <-> tests/test_auth.py (will be DRIFTED — peer drifts)
    _add(runner, "src/auth.py", "tests/test_auth.py", "auth tests")
    # tether 3: src/auth.py <-> docs/billing.md (will be BROKEN — peer removed)
    _add(runner, "src/auth.py", "docs/billing.md", "cross-ref")

    # Cause peer-side drift for tether 2
    (in_project / "tests" / "test_auth.py").write_text("def test_auth(token): pass\n")
    # Cause peer-side BROKEN for tether 3
    (in_project / "docs" / "billing.md").unlink()

    result = runner.invoke(main, ["refs", "src/auth.py"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    states = [t["state"] for t in payload["tethers"]]
    assert states == ["BROKEN", "DRIFTED", "HEALTHY"]


def test_refs_outside_project_raises(in_project: Path):
    _seed_files(in_project)
    result = CliRunner().invoke(main, ["refs", "/etc/hosts"])
    assert result.exit_code == 1
    assert "outside the project root" in result.output


def test_refs_path_missing_on_disk_still_resolves(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    tid = _add(runner, "docs/auth.md", "src/auth.py", "describes auth")
    # Remove the file but keep the tether record
    (in_project / "src" / "auth.py").unlink()
    result = runner.invoke(main, ["refs", "src/auth.py"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["summary"]["total"] == 1
    assert payload["tethers"][0]["id"] == tid
    # The queried file is gone → its side is BROKEN
    assert payload["tethers"][0]["b"]["state"] == "BROKEN"


def test_refs_corrupt_record_listed_in_errors(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    _add(runner, "docs/auth.md", "src/auth.py", "describes auth")
    # Plant a corrupt record alongside
    (in_project / ".tether" / "tethers" / "garbage.json").write_text("not json")
    result = runner.invoke(main, ["refs", "docs/auth.md"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["summary"]["total"] == 1
    assert any("garbage.json" in e["path"] for e in payload["errors"])


def test_refs_plain_includes_paths_and_description(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    _add(runner, "docs/auth.md", "src/auth.py", "describes auth")
    result = runner.invoke(main, ["refs", "src/auth.py", "--plain"])
    assert result.exit_code == 0, result.output
    assert "1 tether referencing `src/auth.py`" in result.output
    assert "`docs/auth.md`" in result.output
    assert "`src/auth.py`" in result.output
    assert "describes auth" in result.output


def test_refs_plain_severity_order(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    _add(runner, "src/auth.py", "docs/auth.md", "auth doc")
    _add(runner, "src/auth.py", "tests/test_auth.py", "auth tests")
    _add(runner, "src/auth.py", "docs/billing.md", "cross-ref")
    (in_project / "tests" / "test_auth.py").write_text("def test_auth(token): pass\n")
    (in_project / "docs" / "billing.md").unlink()

    result = runner.invoke(main, ["refs", "src/auth.py", "--plain"])
    assert result.exit_code == 0, result.output
    # Each tether bullet starts with "- `<id>`: <aggregate>"; extract the aggregate.
    aggregates = [
        line.split(": ", 1)[1].split(" ", 1)[0]
        for line in result.output.splitlines()
        if line.startswith("- `")
    ]
    assert aggregates == ["BROKEN", "DRIFTED", "HEALTHY"]
