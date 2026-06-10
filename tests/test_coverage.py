from __future__ import annotations

import subprocess
from pathlib import Path

import msgspec
from click.testing import CliRunner

from tether.cli import main


def _git_add_all(project: Path) -> None:
    subprocess.run(["git", "add", "-A"], cwd=project, check=True)


def _seed(project: Path) -> None:
    (project / "docs").mkdir()
    (project / "src").mkdir()
    (project / "docs" / "a.md").write_text("# doc\n")
    (project / "src" / "a.py").write_text("x = 1\n")
    (project / "src" / "b.py").write_text("y = 2\n")
    _git_add_all(project)


def _add_tether(a: str, b: str, description: str = "a relates to b") -> None:
    result = CliRunner().invoke(main, ["add", a, b, "--description", description])
    assert result.exit_code == 0, result.output


def test_no_tracked_files(in_project: Path):
    result = CliRunner().invoke(main, ["coverage"])
    assert result.exit_code == 0
    assert "No tracked files outside `.tether/`." in result.output


def test_summary_counts(in_project: Path):
    _seed(in_project)
    _add_tether("docs/a.md", "src/a.py")
    result = CliRunner().invoke(main, ["coverage"])
    assert result.exit_code == 0
    assert "2 of 3 tracked files tethered (67%). 1 untethered." in result.output
    # Hint shown only when no list flag is passed
    assert "--list-untethered-files" in result.output


def test_tether_dir_excluded_from_denominator(in_project: Path):
    _seed(in_project)
    _add_tether("docs/a.md", "src/a.py")
    # Stage the tether records too; counts must not change.
    _git_add_all(in_project)
    result = CliRunner().invoke(main, ["coverage"])
    assert "2 of 3 tracked files tethered" in result.output


def test_file_in_multiple_tethers_counted_once(in_project: Path):
    _seed(in_project)
    _add_tether("docs/a.md", "src/a.py")
    _add_tether("docs/a.md", "src/b.py", "doc also covers b")
    result = CliRunner().invoke(main, ["coverage"])
    assert "3 of 3 tracked files tethered (100%). 0 untethered." in result.output


def test_untracked_tether_path_not_in_numerator(in_project: Path):
    _seed(in_project)
    (in_project / "src" / "untracked.py").write_text("z = 3\n")
    _add_tether("src/a.py", "src/untracked.py")
    result = CliRunner().invoke(main, ["coverage"])
    # untracked.py is tethered but not git-tracked: numerator counts only a.py.
    assert "1 of 3 tracked files tethered (33%). 2 untethered." in result.output


def test_list_flags_compose_with_sections(in_project: Path):
    _seed(in_project)
    _add_tether("docs/a.md", "src/a.py")
    result = CliRunner().invoke(
        main, ["coverage", "--list-untethered-files", "--list-tethered-files"]
    )
    assert result.exit_code == 0
    out = result.output
    assert "### Untethered files" in out
    assert "### Tethered files" in out
    assert "- `src/b.py`" in out
    assert "- `docs/a.md`" in out
    assert "- `src/a.py`" in out
    # No hint line when lists are requested
    assert "For file lists" not in out


def test_list_flag_empty_shows_none(in_project: Path):
    _seed(in_project)
    _add_tether("docs/a.md", "src/a.py")
    _add_tether("src/a.py", "src/b.py", "a feeds b")
    result = CliRunner().invoke(main, ["coverage", "--list-untethered-files"])
    assert "### Untethered files" in result.output
    assert "(none)" in result.output


def test_unreadable_record_skipped_and_reported(in_project: Path):
    _seed(in_project)
    _add_tether("docs/a.md", "src/a.py")
    (in_project / ".tether" / "tethers" / "garbage.json").write_text("not json")
    result = CliRunner().invoke(main, ["coverage"])
    assert result.exit_code == 0
    assert "2 of 3 tracked files tethered" in result.output
    assert "Unreadable tether files (skipped):" in result.output
    assert "garbage.json" in result.output


def test_json_shape(in_project: Path):
    _seed(in_project)
    _add_tether("docs/a.md", "src/a.py")
    result = CliRunner().invoke(main, ["coverage", "--json"])
    assert result.exit_code == 0
    payload = msgspec.json.decode(result.output.encode())
    assert payload["tracked"] == 3
    assert payload["tethered_count"] == 2
    assert payload["untethered_count"] == 1
    assert payload["percent"] == 66.7
    # File arrays populate only behind their flags
    assert payload["tethered_files"] == []
    assert payload["untethered_files"] == []
    assert payload["errors"] == []


def test_json_lists_behind_flags(in_project: Path):
    _seed(in_project)
    _add_tether("docs/a.md", "src/a.py")
    result = CliRunner().invoke(
        main,
        ["coverage", "--json", "--list-untethered-files", "--list-tethered-files"],
    )
    payload = msgspec.json.decode(result.output.encode())
    assert payload["untethered_files"] == ["src/b.py"]
    assert payload["tethered_files"] == ["docs/a.md", "src/a.py"]


def test_json_percent_null_when_no_tracked_files(in_project: Path):
    result = CliRunner().invoke(main, ["coverage", "--json"])
    payload = msgspec.json.decode(result.output.encode())
    assert payload["tracked"] == 0
    assert payload["percent"] is None


def test_non_ascii_path_listed_literally(in_project: Path):
    (in_project / "naïve.md").write_text("# hé\n")
    _git_add_all(in_project)
    result = CliRunner().invoke(main, ["coverage", "--list-untethered-files"])
    assert "- `naïve.md`" in result.output
