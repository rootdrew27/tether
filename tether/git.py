import subprocess
from pathlib import Path

from .errors import GitError


def hash_object_write(file_path: Path, root: Path) -> str:
    result = subprocess.run(
        ["git", "hash-object", "-w", "--", str(file_path)],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitError(f"git hash-object -w failed: {result.stderr.strip()}")
    return result.stdout.strip()


def hash_object(file_path: Path, root: Path) -> str:
    result = subprocess.run(
        ["git", "hash-object", "--", str(file_path)],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitError(f"git hash-object failed: {result.stderr.strip()}")
    return result.stdout.strip()


def cat_blob(oid: str, root: Path) -> bytes:
    result = subprocess.run(
        ["git", "cat-file", "blob", oid],
        cwd=root,
        capture_output=True,
    )
    if result.returncode != 0:
        raise GitError(
            f"git cat-file blob {oid} failed: {result.stderr.decode(errors='replace').strip()}"
        )
    return result.stdout


def blob_exists(oid: str, root: Path) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{oid}^{{blob}}"],
        cwd=root,
        capture_output=True,
    )
    return result.returncode == 0


def find_paths_for_blob(oid: str, root: Path) -> list[str]:
    result = subprocess.run(
        [
            "git",
            "log",
            "--all",
            "--find-object",
            oid,
            "--pretty=tformat:",
            "--name-only",
        ],
        cwd=root,
        capture_output=True,
        text=True,
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
