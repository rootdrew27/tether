from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .errors import GitError, TetherError


def run_git(
    args: list[str],
    *,
    cwd: Path,
    text: bool = True,
) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=text,
    )


def run_git_checked(
    args: list[str],
    *,
    cwd: Path,
    error_prefix: str,
    text: bool = True,
    error_cls: type[TetherError] = GitError,
) -> subprocess.CompletedProcess[Any]:
    result = run_git(args, cwd=cwd, text=text)
    if result.returncode != 0:
        stderr = (
            result.stderr.strip()
            if text
            else result.stderr.decode(errors="replace").strip()
        )
        raise error_cls(f"{error_prefix}: {stderr}")
    return result


def hash_object_write(file_path: Path, root: Path) -> str:
    result = run_git_checked(
        ["hash-object", "-w", "--", str(file_path)],
        cwd=root,
        error_prefix="git hash-object -w failed",
    )
    return result.stdout.strip()


def hash_object(file_path: Path, root: Path) -> str:
    result = run_git_checked(
        ["hash-object", "--", str(file_path)],
        cwd=root,
        error_prefix="git hash-object failed",
    )
    return result.stdout.strip()


def cat_blob(oid: str, root: Path) -> bytes:
    result = run_git_checked(
        ["cat-file", "blob", oid],
        cwd=root,
        text=False,
        error_prefix=f"git cat-file blob {oid} failed",
    )
    return result.stdout


def blob_exists(oid: str, root: Path) -> bool:
    result = run_git(["cat-file", "-e", f"{oid}^{{blob}}"], cwd=root, text=False)
    return result.returncode == 0


def find_paths_for_blob(oid: str, root: Path) -> list[str]:
    result = run_git(
        ["log", "--all", "--find-object", oid, "--pretty=tformat:", "--name-only"],
        cwd=root,
    )
    if result.returncode != 0:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for line in result.stdout.splitlines():
        p = line.strip()
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out
