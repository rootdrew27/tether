from __future__ import annotations

import tempfile
from enum import Enum
from pathlib import Path

import msgspec
from msgspec.structs import replace

from .errors import GitError
from .git import (
    blob_exists,
    cat_blob,
    find_renames,
    hash_object,
    run_git,
)
from .model import Artifact, Tether
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


# Single source of truth for the four aggregate states' ordering. Listed
# healthiest-first (the display order), each paired with a severity rank where a
# lower number is more severe (the worst-first sort key). SEVERITY and
# STATE_ORDER derive from this table so a new state or reorder lands in one place.
STATES: tuple[tuple[AggregateState, int], ...] = (
    (AggregateState.HEALTHY, 3),
    (AggregateState.WEAKENED, 2),
    (AggregateState.DRIFTED, 1),
    (AggregateState.BROKEN, 0),
)

SEVERITY: dict[AggregateState, int] = {state: rank for state, rank in STATES}

STATE_ORDER: tuple[str, ...] = tuple(state.value for state, _ in STATES)


class RenameCandidate(msgspec.Struct, frozen=True, kw_only=True):
    path: str
    similarity: int


class ArtifactCheck(msgspec.Struct, frozen=True, kw_only=True):
    state: ArtifactState
    normalization_rescued: bool = False
    rename_candidates: tuple[RenameCandidate, ...] = ()


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
        # Rename candidates are attached at the batch level by `check_all`, which can
        # pair every BROKEN artifact against the working tree in a single git diff.
        return ArtifactCheck(state=ArtifactState.BROKEN)

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


def check_all(
    tethers: list[Tether], project_root: Path, tabstop: int = 8
) -> list[TetherCheck]:
    """Check every tether and attach rename candidates to BROKEN artifacts.

    State is computed per tether (no rename work), then every BROKEN artifact across the
    whole set is paired against the working tree in a single batched `find_renames` call.
    Use this wherever candidates should surface; `check_tether` stays the state-only
    primitive for callers (e.g. refresh) that only need the aggregate state.
    """
    checks = [check_tether(t, project_root, tabstop=tabstop) for t in tethers]

    broken: list[tuple[str, str]] = []
    for t, ck in zip(tethers, checks):
        if ck.a.state == ArtifactState.BROKEN:
            broken.append((t.a.path, t.a.fingerprint))
        if ck.b.state == ArtifactState.BROKEN:
            broken.append((t.b.path, t.b.fingerprint))
    if not broken:
        return checks

    renames = find_renames(broken, project_root)
    if not renames:
        return checks

    patched: list[TetherCheck] = []
    for t, ck in zip(tethers, checks):
        new_a = _attach_candidate(ck.a, t.a, renames)
        new_b = _attach_candidate(ck.b, t.b, renames)
        if new_a is ck.a and new_b is ck.b:
            patched.append(ck)
        else:
            patched.append(replace(ck, a=new_a, b=new_b))
    return patched


def _attach_candidate(
    art_check: ArtifactCheck,
    artifact: Artifact,
    renames: dict[tuple[str, str], tuple[str, int]],
) -> ArtifactCheck:
    if art_check.state != ArtifactState.BROKEN:
        return art_check
    match = renames.get((artifact.path, artifact.fingerprint))
    if match is None:
        return art_check
    new_path, score = match
    return replace(
        art_check,
        rename_candidates=(RenameCandidate(path=new_path, similarity=score),),
    )


def artifact_diff(artifact_path: str, fingerprint: str, project_root: Path) -> str:
    full = project_root / artifact_path
    if not full.is_file():
        return f"[file not present: {artifact_path}]"
    if not blob_exists(fingerprint, project_root):
        return f"[fingerprinted bytes for {fingerprint} unavailable (likely git-gc'd)]"
    current_oid = hash_object(full, project_root)
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
