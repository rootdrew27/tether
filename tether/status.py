from __future__ import annotations

import tempfile
from enum import Enum
from pathlib import Path

import msgspec

from .errors import GitError
from .git import (
    blob_exists,
    cat_blob,
    find_paths_for_blob,
    hash_object,
    hash_object_write,
    run_git,
)
from .model import Tether
from .normalize import normalize


class ArtifactState(str, Enum):
    HEALTHY = "HEALTHY"
    DRIFTED = "DRIFTED"
    BROKEN = "BROKEN"


class AggregateState(str, Enum):
    HEALTHY = "HEALTHY"
    WEAKENED = "WEAKENED"
    DRIFTED = "DRIFTED"
    BROKEN = "BROKEN"


SEVERITY: dict[AggregateState, int] = {
    AggregateState.BROKEN: 0,
    AggregateState.DRIFTED: 1,
    AggregateState.WEAKENED: 2,
    AggregateState.HEALTHY: 3,
}


class ArtifactCheck(msgspec.Struct, frozen=True, kw_only=True):
    state: ArtifactState
    normalization_rescued: bool = False
    rename_candidates: tuple[str, ...] = ()


class TetherCheck(msgspec.Struct, frozen=True, kw_only=True):
    a: ArtifactCheck
    b: ArtifactCheck
    aggregate: AggregateState


def aggregate(a: ArtifactState, b: ArtifactState) -> AggregateState:
    if ArtifactState.BROKEN in (a, b):
        return AggregateState.BROKEN
    if a == ArtifactState.DRIFTED and b == ArtifactState.DRIFTED:
        return AggregateState.DRIFTED
    if ArtifactState.DRIFTED in (a, b):
        return AggregateState.WEAKENED
    return AggregateState.HEALTHY


def check_artifact(
    artifact_path: str,
    fingerprint: str,
    project_root: Path,
    tabstop: int = 8,
) -> ArtifactCheck:
    full = project_root / artifact_path
    if not full.is_file():
        candidates = tuple(
            p
            for p in find_paths_for_blob(fingerprint, project_root)
            if p != artifact_path
        )
        return ArtifactCheck(state=ArtifactState.BROKEN, rename_candidates=candidates)

    current_oid = hash_object(full, project_root)
    if current_oid == fingerprint:
        return ArtifactCheck(state=ArtifactState.HEALTHY)

    try:
        fingerprinted = cat_blob(fingerprint, project_root)
    except GitError:
        return ArtifactCheck(state=ArtifactState.DRIFTED)

    current = full.read_bytes()
    nc = normalize(current, tabstop=tabstop)
    nf = normalize(fingerprinted, tabstop=tabstop)
    if nc is not None and nf is not None and nc == nf:
        return ArtifactCheck(state=ArtifactState.HEALTHY, normalization_rescued=True)
    return ArtifactCheck(state=ArtifactState.DRIFTED)


def check_tether(t: Tether, project_root: Path, tabstop: int = 8) -> TetherCheck:
    a = check_artifact(t.a.path, t.a.fingerprint, project_root, tabstop=tabstop)
    b = check_artifact(t.b.path, t.b.fingerprint, project_root, tabstop=tabstop)
    return TetherCheck(a=a, b=b, aggregate=aggregate(a.state, b.state))


def artifact_diff(artifact_path: str, fingerprint: str, project_root: Path) -> str:
    full = project_root / artifact_path
    if not full.is_file():
        return f"[file not present: {artifact_path}]"
    if not blob_exists(fingerprint, project_root):
        return f"[fingerprinted bytes for {fingerprint} unavailable (likely git-gc'd)]"
    current_oid = hash_object_write(full, project_root)
    if current_oid == fingerprint:
        return "[no textual diff — encoding-level changes only]"

    with tempfile.TemporaryDirectory() as td:
        old_path = Path(td) / Path(artifact_path).name
        try:
            old_path.write_bytes(cat_blob(fingerprint, project_root))
        except GitError as e:
            return f"[failed to fetch fingerprinted bytes: {e}]"
        result = run_git(
            [
                "diff",
                "--no-color",
                "--no-index",
                "--src-prefix=a/",
                "--dst-prefix=b/",
                "--",
                str(old_path),
                str(full),
            ],
            cwd=project_root,
        )
        old_path_str = str(old_path)
        full_str = str(full)
    if result.returncode not in (0, 1):
        return f"[git diff failed: {result.stderr.strip()}]"
    if not result.stdout.strip():
        return "[no textual diff — encoding-level changes only]"
    output = result.stdout
    # git renders absolute paths after a/b prefixes with the leading slash stripped
    # (so an absolute /tmp/foo becomes a/tmp/foo); replace both stripped and
    # non-stripped variants with the project-relative artifact path.
    old_stripped = old_path_str.lstrip("/")
    full_stripped = full_str.lstrip("/")
    output = output.replace(old_stripped, f"{artifact_path} (fingerprinted)")
    output = output.replace(full_stripped, artifact_path)
    return output
