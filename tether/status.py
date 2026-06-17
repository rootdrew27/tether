from __future__ import annotations

import tempfile
from enum import Enum
from pathlib import Path

import msgspec
from msgspec.structs import replace

from .errors import GitError, LocatorError
from .git import (
    blob_exists,
    cat_blob,
    find_renames,
    hash_object,
    hash_object_bytes,
    run_git,
)
from .locators import extract_region
from .model import Artifact, Locator, RegionFingerprint, Tether
from .normalize import normalize


class ArtifactState(str, Enum):
    HEALTHY = "HEALTHY"
    DRIFTED = "DRIFTED"
    BROKEN = "BROKEN"


class AggregateState(str, Enum):
    HEALTHY = "HEALTHY"
    DRIFTED = "DRIFTED"
    BROKEN = "BROKEN"


# Single source of truth for the three aggregate states' ordering. Listed
# healthiest-first (the display order), each paired with a severity rank where a
# lower number is more severe (the worst-first sort key). SEVERITY and
# STATE_ORDER derive from this table so a new state or reorder lands in one place.
STATES: tuple[tuple[AggregateState, int], ...] = (
    (AggregateState.HEALTHY, 2),
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
    if ArtifactState.DRIFTED in (a, b):
        return AggregateState.DRIFTED
    return AggregateState.HEALTHY


def check_artifact(
    artifact: Artifact,
    project_root: Path,
    tabstop: int = 8,
) -> ArtifactCheck:
    full = project_root / artifact.path
    if not full.is_file():
        # Rename candidates are attached at the batch level by `check_all`, which can
        # pair every file-missing artifact against the working tree in one git diff.
        return ArtifactCheck(state=ArtifactState.BROKEN)

    fp = artifact.fingerprint
    if artifact.locator is None:
        # validate() guarantees a whole-file artifact's fingerprint is a string.
        assert isinstance(fp, str)
        return _check_whole_file(full, fp, project_root, tabstop)
    assert isinstance(fp, RegionFingerprint)
    return _check_region(full, artifact.locator, fp, project_root, tabstop)


def _check_whole_file(
    full: Path, fingerprint: str, project_root: Path, tabstop: int
) -> ArtifactCheck:
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


def _check_region(
    full: Path,
    locator: Locator,
    fp: RegionFingerprint,
    project_root: Path,
    tabstop: int,
) -> ArtifactCheck:
    try:
        region = extract_region(full.read_bytes(), locator)
    except LocatorError:
        # The file exists but the region cannot be located — the symbol was
        # renamed/removed, the match is ambiguous, or the file no longer parses
        # such that the region resolves. The locator does not resolve → BROKEN,
        # mirroring the whole-file "file absent" case. Region-rename suggestion
        # is future work; never silently fall through to HEALTHY.
        return ArtifactCheck(state=ArtifactState.BROKEN)

    current_hash = hash_object_bytes(region, project_root)
    if current_hash == fp.region_hash:
        return ArtifactCheck(state=ArtifactState.HEALTHY)

    try:
        fingerprinted = cat_blob(fp.region_hash, project_root)
    except GitError:
        return ArtifactCheck(state=ArtifactState.DRIFTED)

    nc = normalize(region, tabstop=tabstop)
    nf = normalize(fingerprinted, tabstop=tabstop)
    if nc is not None and nf is not None and nc == nf:
        return ArtifactCheck(state=ArtifactState.HEALTHY, normalization_rescued=True)
    return ArtifactCheck(state=ArtifactState.DRIFTED)


def check_tether(t: Tether, project_root: Path, tabstop: int = 8) -> TetherCheck:
    a = check_artifact(t.a, project_root, tabstop=tabstop)
    b = check_artifact(t.b, project_root, tabstop=tabstop)
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

    # Only artifacts whose *file* is missing are file-rename candidates. A region
    # that is BROKEN because its symbol moved within a present file is not a file
    # rename; it is keyed by file_oid below but git finds no match (the path still
    # exists), so it simply gets no candidate.
    broken: list[tuple[str, str]] = []
    for t, ck in zip(tethers, checks):
        for art, art_ck in ((t.a, ck.a), (t.b, ck.b)):
            if (
                art_ck.state == ArtifactState.BROKEN
                and not (project_root / art.path).is_file()
            ):
                broken.append((art.path, art.file_oid))
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
    match = renames.get((artifact.path, artifact.file_oid))
    if match is None:
        return art_check
    new_path, score = match
    return replace(
        art_check,
        rename_candidates=(RenameCandidate(path=new_path, similarity=score),),
    )


def artifact_diff(artifact: Artifact, project_root: Path) -> str:
    """Unified diff between an artifact's fingerprinted content and its current.

    Whole-file artifacts diff the fingerprinted blob against the live file;
    region artifacts diff the fingerprinted region blob against the freshly
    extracted region. The returned string is the git diff with temp/absolute
    paths rewritten to the artifact's display label, or a bracketed status note.
    """
    full = project_root / artifact.path
    if not full.is_file():
        return f"[file not present: {artifact.path}]"
    fp = artifact.fingerprint
    if artifact.locator is None:
        assert isinstance(fp, str)
        return _whole_file_diff(artifact.path, fp, full, project_root)
    assert isinstance(fp, RegionFingerprint)
    return _region_diff(artifact, artifact.locator, fp, full, project_root)


def _whole_file_diff(
    artifact_path: str, fingerprint: str, full: Path, project_root: Path
) -> str:
    if not blob_exists(fingerprint, project_root):
        return f"[fingerprinted bytes for {fingerprint} unavailable (likely git-gc'd)]"
    if hash_object(full, project_root) == fingerprint:
        return "[no textual diff — encoding-level changes only]"

    with tempfile.TemporaryDirectory() as td:
        old_path = Path(td) / Path(artifact_path).name
        try:
            old_path.write_bytes(cat_blob(fingerprint, project_root))
        except GitError as e:
            return f"[failed to fetch fingerprinted bytes: {e}]"
        result = _git_diff_no_index(old_path, full, project_root)
        old_str, new_str = str(old_path), str(full)
    return _finish_diff(
        result, old_str, f"{artifact_path} (fingerprinted)", new_str, artifact_path
    )


def _region_diff(
    artifact: Artifact,
    locator: Locator,
    fp: RegionFingerprint,
    full: Path,
    project_root: Path,
) -> str:
    label = f"{artifact.path}::{locator.selector}"
    try:
        region = extract_region(full.read_bytes(), locator)
    except LocatorError as e:
        return f"[region not locatable: {e}]"
    if not blob_exists(fp.region_hash, project_root):
        return (
            f"[fingerprinted region for {fp.region_hash} unavailable (likely git-gc'd)]"
        )
    if hash_object_bytes(region, project_root) == fp.region_hash:
        return "[no textual diff — encoding-level changes only]"

    with tempfile.TemporaryDirectory() as td:
        old_path = Path(td) / "fingerprinted"
        new_path = Path(td) / "current"
        try:
            old_path.write_bytes(cat_blob(fp.region_hash, project_root))
        except GitError as e:
            return f"[failed to fetch fingerprinted region: {e}]"
        new_path.write_bytes(region)
        result = _git_diff_no_index(old_path, new_path, project_root)
        old_str, new_str = str(old_path), str(new_path)
    return _finish_diff(result, old_str, f"{label} (fingerprinted)", new_str, label)


def _git_diff_no_index(old_path: Path, new_path: Path, project_root: Path):
    return run_git(
        [
            "diff",
            "--no-color",
            "--no-index",
            "--src-prefix=a/",
            "--dst-prefix=b/",
            "--",
            str(old_path),
            str(new_path),
        ],
        cwd=project_root,
    )


def _finish_diff(
    result,
    old_str: str,
    old_label: str,
    new_str: str,
    new_label: str,
) -> str:
    if result.returncode not in (0, 1):
        return f"[git diff failed: {result.stderr.strip()}]"
    if not result.stdout.strip():
        return "[no textual diff — encoding-level changes only]"
    # git renders absolute paths after a/b prefixes with the leading slash
    # stripped (so /tmp/foo becomes a/tmp/foo); rewrite them to the display
    # label. Paths only appear in header lines before the first hunk — content
    # lines may legitimately contain the file's own path and pass through.
    old_stripped = old_str.lstrip("/")
    new_stripped = new_str.lstrip("/")
    lines = result.stdout.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith("@@"):
            break
        line = line.replace(old_stripped, old_label)
        lines[i] = line.replace(new_stripped, new_label)
    return "".join(lines)
