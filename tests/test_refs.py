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


def test_refs_empty_result_xml(in_project: Path):
    _seed_files(in_project)
    result = CliRunner().invoke(main, ["refs", "src/auth.py", "--xml"])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "<tether-context>\n</tether-context>"


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


def test_refs_multi_match_severity_order_xml(in_project: Path):
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

    result = runner.invoke(main, ["refs", "src/auth.py", "--xml"])
    assert result.exit_code == 0, result.output
    out = result.output
    # Severity order: BROKEN first, then DRIFTED, then HEALTHY
    broken_pos = out.find('aggregate="BROKEN"')
    drifted_pos = out.find('aggregate="DRIFTED"')
    healthy_pos = out.find('aggregate="HEALTHY"')
    assert 0 <= broken_pos < drifted_pos < healthy_pos


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


def test_refs_mutually_exclusive_flags(in_project: Path):
    result = CliRunner().invoke(main, ["refs", "src/auth.py", "--json", "--xml"])
    assert result.exit_code == 1
    assert "mutually exclusive" in result.output


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


def test_refs_xml_escapes_description(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    _add(
        runner,
        "docs/auth.md",
        "src/auth.py",
        'uses <token> & "quoted" things',
    )
    result = runner.invoke(main, ["refs", "src/auth.py", "--xml"])
    assert result.exit_code == 0, result.output
    # Description content must be escaped
    assert "&lt;token&gt;" in result.output
    assert "&amp;" in result.output
    # The raw form must not leak through
    assert "<token>" not in result.output.replace("<tether-context>", "").replace(
        "</tether-context>", ""
    )


def test_refs_xml_includes_self_and_peer_paths(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    _add(runner, "docs/auth.md", "src/auth.py", "describes auth")
    result = runner.invoke(main, ["refs", "src/auth.py", "--xml"])
    assert result.exit_code == 0, result.output
    assert '<self path="src/auth.py"' in result.output
    assert '<peer path="docs/auth.md"' in result.output
