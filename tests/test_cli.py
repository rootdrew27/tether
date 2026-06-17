from __future__ import annotations

import json
from pathlib import Path

import msgspec
from click.testing import CliRunner

from tether.cli import _surface, main
from tether.model import Tether
from tether.storage import load_all_tethers


def test_surface_routing() -> None:
    # explicit flags win over everything
    assert (
        _surface(as_json=True, plain=False, is_tty=True, json_default=False) == "json"
    )
    assert (
        _surface(as_json=False, plain=True, is_tty=True, json_default=True) == "plain"
    )
    # a TTY with no flags gets the pretty view, regardless of json_default
    assert (
        _surface(as_json=False, plain=False, is_tty=True, json_default=False)
        == "pretty"
    )
    assert (
        _surface(as_json=False, plain=False, is_tty=True, json_default=True) == "pretty"
    )
    # piped (agent path): refs falls back to JSON, status to plain markdown
    assert (
        _surface(as_json=False, plain=False, is_tty=False, json_default=True) == "json"
    )
    assert (
        _surface(as_json=False, plain=False, is_tty=False, json_default=False)
        == "plain"
    )


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


def test_init_errors_cleanly_when_tether_dir_is_a_file(tmp_path: Path, monkeypatch):
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".tether").write_text("not a directory\n")
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(main, ["init"])
    assert result.exit_code == 1
    assert "Unable to create" in result.output


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
    assert "self-tethers" in result.output


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


def test_status_drifted_after_one_sided_drift(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    _add_tether(runner)
    (in_project / "src" / "auth.py").write_text("def auth(token): pass\n")
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0
    assert "DRIFTED" in result.output
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
    loaded = load_all_tethers(in_project).tethers[0]
    assert loaded.b.path == "src/authentication.py"


def test_rm_rejects_traversal_id(in_project: Path):
    secret = in_project / "secret.json"
    secret.write_text("{}\n")
    result = CliRunner().invoke(main, ["rm", "../../secret"])
    assert result.exit_code == 1
    assert "UUID" in result.output
    assert secret.exists()


def test_mv_abort_leaves_no_records_changed(in_project: Path):
    # t1 = (x.md, y.md) rewrites cleanly; t2 = (z.md, y.md) would become a
    # self-tether. The abort must leave every record untouched, including t1.
    for name in ("x.md", "y.md", "z.md"):
        (in_project / name).write_text(f"{name}\n")
    runner = CliRunner()
    for a, b in (("x.md", "y.md"), ("z.md", "y.md")):
        r = runner.invoke(main, ["add", a, b, "--description", "d"])
        assert r.exit_code == 0, r.output

    result = runner.invoke(main, ["mv", "y.md", "z.md"])
    assert result.exit_code == 1
    assert "self-tether" in result.output
    assert "no records changed" in result.output
    paths = sorted((t.a.path, t.b.path) for t in load_all_tethers(in_project).tethers)
    assert paths == [("x.md", "y.md"), ("z.md", "y.md")]


def test_update_description(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    tid = _add_tether(runner)
    result = runner.invoke(main, ["update", tid, "--description", "new description"])
    assert result.exit_code == 0
    loaded = load_all_tethers(in_project).tethers[0]
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


# --- region (section-locator) tethers --------------------------------------

_PY_MODULE = """def alpha(x):
    return x + 1


def beta(y):
    return y * 2
"""


def _seed_region_files(project: Path) -> None:
    (project / "docs").mkdir()
    (project / "src").mkdir()
    (project / "docs" / "calc.md").write_text("# calc\n")
    (project / "src" / "calc.py").write_text(_PY_MODULE)


def _add_region(runner: CliRunner) -> str:
    result = runner.invoke(
        main,
        [
            "add",
            "src/calc.py::alpha",
            "docs/calc.md",
            "--description",
            "alpha is documented in calc.md",
        ],
    )
    assert result.exit_code == 0, result.output
    return result.output.split()[-1]


def test_add_region_writes_v2_record(in_project: Path):
    _seed_region_files(in_project)
    _add_region(CliRunner())
    t = load_all_tethers(in_project).tethers[0]
    assert t.schema_version == 2
    assert t.a.locator is not None
    assert t.a.locator.kind == "symbol"
    assert t.a.locator.lang == "python"
    assert t.a.locator.selector == "alpha"
    assert t.a.fingerprint.file_blob_oid  # type: ignore[union-attr]
    assert t.a.fingerprint.region_hash  # type: ignore[union-attr]
    assert t.b.locator is None  # whole-file peer untouched


def test_add_region_unsupported_extension_rejected(in_project: Path):
    _seed_region_files(in_project)
    (in_project / "notes.txt").write_text("plain notes\n")
    result = CliRunner().invoke(
        main,
        ["add", "notes.txt::Heading", "src/calc.py", "--description", "d"],
    )
    assert result.exit_code == 1
    assert "no section-locator parser" in result.output


def test_add_region_unresolved_selector_rejected(in_project: Path):
    _seed_region_files(in_project)
    result = CliRunner().invoke(
        main,
        ["add", "src/calc.py::missing", "docs/calc.md", "--description", "d"],
    )
    assert result.exit_code == 1
    assert "no definition named 'missing'" in result.output


def test_region_status_lifecycle_drift_then_refresh(in_project: Path):
    _seed_region_files(in_project)
    runner = CliRunner()
    tid = _add_region(runner)

    # Editing beta must not drift a tether on alpha.
    src = in_project / "src" / "calc.py"
    src.write_text(_PY_MODULE.replace("return y * 2", "return y * 99"))
    assert "all HEALTHY" in runner.invoke(main, ["status"]).output

    # Editing alpha drifts it.
    src.write_text(_PY_MODULE.replace("return x + 1", "return x + 100"))
    assert "DRIFTED" in runner.invoke(main, ["status"]).output

    # Refresh re-fingerprints the region and clears the drift.
    assert runner.invoke(main, ["refresh", tid]).exit_code == 0
    assert "all HEALTHY" in runner.invoke(main, ["status"]).output


def test_region_status_broken_on_symbol_rename(in_project: Path):
    _seed_region_files(in_project)
    runner = CliRunner()
    _add_region(runner)
    (in_project / "src" / "calc.py").write_text(
        _PY_MODULE.replace("def alpha", "def renamed_alpha")
    )
    result = runner.invoke(main, ["status"])
    assert "BROKEN" in result.output


def test_update_selector_then_refresh_follows_region_rename(in_project: Path):
    _seed_region_files(in_project)
    runner = CliRunner()
    tid = _add_region(runner)
    (in_project / "src" / "calc.py").write_text(
        _PY_MODULE.replace("def alpha", "def renamed_alpha")
    )
    # Follow the region rename structurally, then refresh to re-align.
    assert (
        runner.invoke(main, ["update", tid, "--a-selector", "renamed_alpha"]).exit_code
        == 0
    )
    t = load_all_tethers(in_project).tethers[0]
    assert t.a.locator is not None and t.a.locator.selector == "renamed_alpha"
    assert runner.invoke(main, ["refresh", tid]).exit_code == 0
    assert "all HEALTHY" in runner.invoke(main, ["status"]).output


def test_update_selector_on_whole_file_artifact_rejected(in_project: Path):
    _seed_files(in_project)
    runner = CliRunner()
    tid = _add_tether(runner)
    result = runner.invoke(main, ["update", tid, "--a-selector", "auth"])
    assert result.exit_code == 1
    assert "no locator" in result.output


def test_region_status_json_carries_locator(in_project: Path):
    _seed_region_files(in_project)
    runner = CliRunner()
    tid = _add_region(runner)
    payload = json.loads(runner.invoke(main, ["status", tid, "--json"]).output)
    assert payload["a"]["locator"]["selector"] == "alpha"
    assert payload["b"]["locator"] is None


_MD_DOC = """# calc

## Add

Adds two numbers.

## Multiply

Multiplies two numbers.
"""


def test_add_markdown_region_and_lifecycle(in_project: Path):
    _seed_region_files(in_project)
    runner = CliRunner()
    md = in_project / "docs" / "calc.md"
    md.write_text(_MD_DOC)

    # Both ends are regions: a markdown heading path and a python symbol.
    result = runner.invoke(
        main,
        [
            "add",
            "docs/calc.md::calc/Add",
            "src/calc.py::alpha",
            "--description",
            "the Add section documents alpha",
        ],
    )
    assert result.exit_code == 0, result.output
    tid = result.output.split()[-1]

    t = load_all_tethers(in_project).tethers[0]
    assert t.schema_version == 2
    assert t.a.locator is not None
    assert t.a.locator.kind == "heading"
    assert t.a.locator.lang == "markdown"
    assert t.a.locator.selector == "calc/Add"

    # Editing the Multiply section must not drift a tether on the Add section.
    md.write_text(_MD_DOC.replace("Multiplies two numbers.", "Multiplies two ints."))
    assert "all HEALTHY" in runner.invoke(main, ["status"]).output

    # Editing the Add section drifts it; refresh re-aligns.
    md.write_text(_MD_DOC.replace("Adds two numbers.", "Adds two integers."))
    assert "DRIFTED" in runner.invoke(main, ["status"]).output
    assert runner.invoke(main, ["refresh", tid]).exit_code == 0
    assert "all HEALTHY" in runner.invoke(main, ["status"]).output
