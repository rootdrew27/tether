from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .errors import GitError, TetherError

# Similarity floor for surfacing a rename candidate. `-M30%` means git pairs a
# deletion with an addition when ≥30% of the content is unchanged — lower than
# git's 50% default so heavier edits still surface under notify-only.
RENAME_SIMILARITY = "-M30%"


def run_git(
    args: list[str],
    *,
    cwd: Path,
    text: bool = True,
    env: dict[str, str] | None = None,
    input_data: bytes | str | None = None,
) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=text,
        env=env,
        input=input_data,
    )


def run_git_or_raise(
    args: list[str],
    *,
    cwd: Path,
    error_prefix: str,
    text: bool = True,
    error_cls: type[TetherError] = GitError,
    input_data: bytes | str | None = None,
) -> subprocess.CompletedProcess[Any]:
    result = run_git(args, cwd=cwd, text=text, input_data=input_data)
    if result.returncode != 0:
        stderr = (
            result.stderr.strip()
            if text
            else result.stderr.decode(errors="replace").strip()
        )
        raise error_cls(f"{error_prefix}: {stderr}")
    return result


def ls_files(root: Path) -> list[str]:
    """Return the project-relative POSIX paths of all git-tracked files."""
    result = run_git_or_raise(
        ["-c", "core.quotePath=false", "ls-files", "-z"],
        cwd=root,
        error_prefix="git ls-files failed",
    )
    return [p for p in result.stdout.split("\0") if p]


def hash_object_write(file_path: Path, root: Path) -> str:
    result = run_git_or_raise(
        ["hash-object", "-w", "--", str(file_path)],
        cwd=root,
        error_prefix="git hash-object -w failed",
    )
    return result.stdout.strip()


def hash_object(file_path: Path, root: Path) -> str:
    result = run_git_or_raise(
        ["hash-object", "--", str(file_path)],
        cwd=root,
        error_prefix="git hash-object failed",
    )
    return result.stdout.strip()


def hash_object_write_bytes(data: bytes, root: Path) -> str:
    """Write arbitrary bytes to git's object store as a blob; return the OID.

    Used to fingerprint a *region* (a located sub-file span) whose bytes have no
    file of their own. The blob is unreachable from any commit, so it is subject
    to git's gc grace period like any other loose blob — ref-pinning (see
    Future-Work) is the planned hardening.
    """
    result = run_git_or_raise(
        ["hash-object", "-w", "--stdin"],
        cwd=root,
        text=False,
        input_data=data,
        error_prefix="git hash-object -w --stdin failed",
    )
    return result.stdout.decode().strip()


def hash_object_bytes(data: bytes, root: Path) -> str:
    """Compute the git blob OID of `data` without writing it (drift compare)."""
    result = run_git_or_raise(
        ["hash-object", "--stdin"],
        cwd=root,
        text=False,
        input_data=data,
        error_prefix="git hash-object --stdin failed",
    )
    return result.stdout.decode().strip()


def cat_blob(oid: str, root: Path) -> bytes:
    result = run_git_or_raise(
        ["cat-file", "blob", oid],
        cwd=root,
        text=False,
        error_prefix=f"git cat-file blob {oid} failed",
    )
    return result.stdout


def blob_exists(oid: str, root: Path) -> bool:
    result = run_git(["cat-file", "-e", f"{oid}^{{blob}}"], cwd=root, text=False)
    return result.returncode == 0


def find_renames(
    broken: list[tuple[str, str]],
    root: Path,
) -> dict[tuple[str, str], tuple[str, int]]:
    """Find best-match rename candidates for BROKEN artifacts via git's rename detector.

    Each input is an ``(old_path, fingerprint)`` pair for an artifact whose file is
    missing at its recorded path. tether owns both halves git's ``diffcore-rename`` needs
    — the old path and the old content (the fingerprint blob) — so it synthesizes a
    "before" tree and diffs it against the live working tree through a throwaway index.
    The user's real index, working tree, and refs are never touched (only loose blobs for
    untracked files land in the object store, which git reclaims on gc).

    Returns a mapping from each input pair to ``(new_path, similarity_score)`` for every
    pair git can pair to a current file; pairs with no match are absent. Never raises —
    any git failure degrades to a partial or empty mapping so callers stay crash-free.
    """
    if not broken:
        return {}

    # Dedup by (path, fingerprint); drop fingerprints whose blob is gone (a GC'd blob
    # cannot be scored, so it yields no candidate).
    deduped = list(dict.fromkeys(broken))
    survivors = [(p, fp) for (p, fp) in deduped if blob_exists(fp, root)]
    if not survivors:
        return {}

    out: dict[tuple[str, str], tuple[str, int]] = {}
    try:
        with tempfile.TemporaryDirectory(prefix="tether-rename-") as td:
            tdp = Path(td)

            # T_new — the current working tree, shared across every collision layer.
            ti_new = tdp / "index_new"
            if not _seed_new_index(ti_new, root):
                return out
            env_new = {**os.environ, "GIT_INDEX_FILE": str(ti_new)}

            # A tree path is unique, so the same old_path recorded at two different
            # fingerprints cannot coexist in one T_old; layer them and diff each.
            for li, layer in enumerate(_layer(survivors)):
                tree_old = _write_tree(tdp / f"index_old_{li}", layer, root)
                if tree_old is None:
                    continue
                for old_p, new_p, score in _diff_renames(tree_old, env_new, root):
                    fp = layer.get(old_p)
                    if fp is not None:
                        out[(old_p, fp)] = (new_p, score)
        return out
    except OSError:
        return out


def _layer(survivors: list[tuple[str, str]]) -> list[dict[str, str]]:
    """Partition (path, fingerprint) pairs so each path appears once per layer."""
    layers: list[dict[str, str]] = []
    for path, fp in survivors:
        for layer in layers:
            if path not in layer:
                layer[path] = fp
                break
        else:
            layers.append({path: fp})
    return layers


def _seed_new_index(ti_new: Path, root: Path) -> bool:
    """Build a throwaway index reflecting the current working tree. False on failure.

    Copies the real index when present (reusing git's stat-cache, and carrying
    committed-but-clean files so committed renames are covered), then folds in
    working-tree changes with ``git add -A``. A fresh/no-commit repo has no index file
    yet; there the copy is skipped and ``git add -A`` initializes an empty one.
    """
    rp = run_git(["rev-parse", "--git-path", "index"], cwd=root)
    if rp.returncode == 0:
        real_path = Path(rp.stdout.strip())
        if not real_path.is_absolute():
            real_path = root / real_path
        if real_path.is_file():
            shutil.copyfile(real_path, ti_new)
    env = {**os.environ, "GIT_INDEX_FILE": str(ti_new)}
    return run_git(["add", "-A"], cwd=root, env=env).returncode == 0


def _write_tree(ti_old: Path, layer: dict[str, str], root: Path) -> str | None:
    """Write a tree containing only ``{path: fingerprint_blob}``. None on failure."""
    # A name-only index path must stay 0-byte-free for git; clear any stale lock too.
    lock = ti_old.with_name(ti_old.name + ".lock")
    if lock.exists():
        lock.unlink()
    env = {**os.environ, "GIT_INDEX_FILE": str(ti_old)}
    for path, fp in layer.items():
        r = run_git(
            ["update-index", "--add", "--cacheinfo", f"100644,{fp},{path}"],
            cwd=root,
            env=env,
        )
        if r.returncode != 0:
            return None
    wt = run_git(["write-tree"], cwd=root, env=env)
    return wt.stdout.strip() if wt.returncode == 0 else None


def _diff_renames(
    tree_old: str, env_new: dict[str, str], root: Path
) -> list[tuple[str, str, int]]:
    """Pair the synthetic deletions in ``tree_old`` against the seeded working tree.

    Returns ``(old_path, new_path, score)`` for each rename row. ``diff.renameLimit=0``
    neutralizes user gitconfig; ``core.quotePath=false`` keeps non-ASCII paths literal.
    """
    r = run_git(
        [
            "-c",
            "diff.renameLimit=0",
            "-c",
            "core.quotePath=false",
            "diff-index",
            RENAME_SIMILARITY,
            "--find-renames",
            "-z",
            "--name-status",
            tree_old,
        ],
        cwd=root,
        env=env_new,
    )
    if r.returncode not in (0, 1):
        return []
    return _parse_name_status_z(r.stdout)


def _parse_name_status_z(out: str) -> list[tuple[str, str, int]]:
    """Parse a ``-z --name-status`` stream (variable arity per row).

    Rename/copy rows carry two paths (``R<score>\\0<old>\\0<new>``); A/D/M/T/U rows carry
    one. Dispatch on the status token's first char and consume fields accordingly. Only
    rename (``R``) rows are returned; copy (``C``) rows are parsed for stream alignment.
    """
    toks = out.split("\0")
    while toks and toks[-1] == "":
        toks.pop()
    results: list[tuple[str, str, int]] = []
    i, n = 0, len(toks)
    while i < n:
        status = toks[i]
        i += 1
        if not status:
            continue
        if status[0] in ("R", "C"):
            if i + 1 >= n:
                break
            old_p, new_p = toks[i], toks[i + 1]
            i += 2
            if status[0] == "R":
                try:
                    score = int(status[1:])
                except ValueError:
                    score = 0
                results.append((old_p, new_p, score))
        else:
            if i >= n:
                break
            i += 1
    return results
