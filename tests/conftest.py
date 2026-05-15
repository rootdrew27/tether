from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tether.project import init_project


@pytest.fixture
def project(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "tether-tests"], cwd=tmp_path, check=True
    )
    init_project(tmp_path)
    return tmp_path


@pytest.fixture
def in_project(project: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(project)
    return project
