import subprocess
from pathlib import Path

from tether.git import find_renames, hash_object_write, hash_object_write_bytes
from tether.locators import extract_region
from tether.model import Artifact, Locator, RegionFingerprint, Tether
from tether.status import (
    AggregateState,
    ArtifactState,
    aggregate,
    artifact_diff,
    check_all,
    check_artifact,
)
from uuid_utils import uuid7


def _tether(a_path: str, a_fp: str, b_path: str, b_fp: str) -> Tether:
    return Tether(
        id=str(uuid7()),
        schema_version=1,
        a=Artifact(path=a_path, fingerprint=a_fp),
        b=Artifact(path=b_path, fingerprint=b_fp),
        description="d",
        created_at="2026-05-13T10:00:00Z",
        refreshed_at="2026-05-13T10:00:00Z",
    )


def test_healthy_when_oid_matches(project: Path):
    f = project / "x.md"
    f.write_text("hello\n")
    fp = hash_object_write(f, project)
    c = check_artifact(Artifact(path="x.md", fingerprint=fp), project)
    assert c.state == ArtifactState.HEALTHY
    assert c.normalization_rescued is False
    assert c.rename_candidates == ()


def test_drifted_when_content_changes(project: Path):
    f = project / "x.md"
    f.write_text("hello\n")
    fp = hash_object_write(f, project)
    f.write_text("hello world\n")
    c = check_artifact(Artifact(path="x.md", fingerprint=fp), project)
    assert c.state == ArtifactState.DRIFTED
    assert c.normalization_rescued is False


def test_broken_when_file_missing(project: Path):
    c = check_artifact(Artifact(path="nope.md", fingerprint="a" * 40), project)
    assert c.state == ArtifactState.BROKEN
    assert c.rename_candidates == ()


def test_broken_surfaces_rename_candidate(project: Path):
    f = project / "src" / "auth.py"
    f.parent.mkdir(parents=True)
    f.write_text("def auth(): pass\n")
    fp = hash_object_write(f, project)
    peer = project / "peer.md"
    peer.write_text("peer\n")
    peer_fp = hash_object_write(peer, project)
    subprocess.run(["git", "add", "-A"], cwd=project, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=project, check=True)
    subprocess.run(
        ["git", "mv", "src/auth.py", "src/authentication.py"], cwd=project, check=True
    )
    subprocess.run(["git", "commit", "-q", "-m", "rename"], cwd=project, check=True)

    t = _tether("src/auth.py", fp, "peer.md", peer_fp)
    check = check_all([t], project)[0]
    assert check.a.state == ArtifactState.BROKEN
    assert len(check.a.rename_candidates) == 1
    candidate = check.a.rename_candidates[0]
    assert candidate.path == "src/authentication.py"
    assert candidate.similarity == 100  # committed pure rename is an exact match


def test_normalization_rescues_crlf_change(project: Path):
    f = project / "x.md"
    f.write_bytes(b"hello\nworld\n")
    fp = hash_object_write(f, project)
    f.write_bytes(b"hello\r\nworld\r\n")
    c = check_artifact(Artifact(path="x.md", fingerprint=fp), project)
    assert c.state == ArtifactState.HEALTHY
    assert c.normalization_rescued is True


def test_normalization_rescues_trailing_whitespace(project: Path):
    f = project / "x.md"
    f.write_bytes(b"hello\nworld\n")
    fp = hash_object_write(f, project)
    f.write_bytes(b"hello   \nworld\t\n")
    c = check_artifact(Artifact(path="x.md", fingerprint=fp), project)
    assert c.state == ArtifactState.HEALTHY
    assert c.normalization_rescued is True


def test_aggregate_both_healthy_is_healthy():
    assert (
        aggregate(ArtifactState.HEALTHY, ArtifactState.HEALTHY)
        == AggregateState.HEALTHY
    )


def test_aggregate_any_drifted_is_drifted():
    assert (
        aggregate(ArtifactState.HEALTHY, ArtifactState.DRIFTED)
        == AggregateState.DRIFTED
    )
    assert (
        aggregate(ArtifactState.DRIFTED, ArtifactState.HEALTHY)
        == AggregateState.DRIFTED
    )
    assert (
        aggregate(ArtifactState.DRIFTED, ArtifactState.DRIFTED)
        == AggregateState.DRIFTED
    )


def test_aggregate_any_broken_is_broken():
    assert (
        aggregate(ArtifactState.BROKEN, ArtifactState.HEALTHY) == AggregateState.BROKEN
    )
    assert (
        aggregate(ArtifactState.DRIFTED, ArtifactState.BROKEN) == AggregateState.BROKEN
    )
    assert (
        aggregate(ArtifactState.BROKEN, ArtifactState.BROKEN) == AggregateState.BROKEN
    )


def _commit_lines(project: Path, name: str, lines: list[str]) -> str:
    f = project / name
    f.write_text("".join(lines))
    fp = hash_object_write(f, project)
    subprocess.run(["git", "add", "-A"], cwd=project, check=True)
    subprocess.run(["git", "commit", "-q", "-m", name], cwd=project, check=True)
    return fp


def test_find_renames_detects_edited_rename(project: Path):
    # An unstaged rename + a small edit still pairs by content similarity — the case
    # the old exact-OID scan could not follow.
    lines = [f"line {i} of the module body\n" for i in range(40)]
    fp = _commit_lines(project, "mod.py", lines)
    (project / "mod.py").unlink()
    lines[0] = "the first line was edited\n"
    (project / "renamed.py").write_text("".join(lines))

    result = find_renames([("mod.py", fp)], project)
    assert ("mod.py", fp) in result
    new_path, score = result[("mod.py", fp)]
    assert new_path == "renamed.py"
    assert score >= 30  # above the -M30% floor


def test_find_renames_below_threshold_returns_nothing(project: Path):
    lines = [f"original line {i}\n" for i in range(40)]
    fp = _commit_lines(project, "mod.py", lines)
    (project / "mod.py").unlink()
    # Rewrite nearly everything so similarity drops below the 30% floor.
    rewritten = [f"completely different replacement text {i}\n" for i in range(40)]
    rewritten[0] = "original line 0\n"
    (project / "renamed.py").write_text("".join(rewritten))

    assert find_renames([("mod.py", fp)], project) == {}


def test_artifact_diff_rewrites_headers_to_relative_paths(project: Path):
    f = project / "x.md"
    f.write_text("old\n")
    fp = hash_object_write(f, project)
    f.write_text("new\n")

    out = artifact_diff(Artifact(path="x.md", fingerprint=fp), project)
    assert "--- a/x.md (fingerprinted)\n" in out
    assert "+++ b/x.md\n" in out
    assert str(project) not in out  # no absolute paths leak into the diff


def test_artifact_diff_preserves_content_containing_own_path(project: Path):
    # A file whose content embeds its own absolute path (generated configs,
    # fixtures using __file__) must render verbatim — the header path rewrite
    # must not touch hunk content.
    f = project / "x.md"
    own_path = str(f)
    f.write_text(f'BASE = "{own_path}"\nold\n')
    fp = hash_object_write(f, project)
    f.write_text(f'BASE = "{own_path}"\nnew\n')

    out = artifact_diff(Artifact(path="x.md", fingerprint=fp), project)
    assert f' BASE = "{own_path}"\n' in out  # context line untouched
    assert "-old\n" in out
    assert "+new\n" in out


def test_find_renames_missing_blob_does_not_crash(project: Path):
    # A fingerprint whose blob is not in the object store (e.g. GC'd) is filtered out;
    # detection degrades to no candidate rather than raising.
    assert find_renames([("gone.py", "0" * 40)], project) == {}


# --- region (section-locator) artifacts ------------------------------------

_REGION_SRC = """def alpha(x):
    return x + 1


def beta(y):
    return y * 2
"""


def _py_region_artifact(
    project: Path, rel: str, source: str, selector: str
) -> Artifact:
    f = project / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(source)
    loc = Locator(kind="symbol", lang="python", selector=selector)
    file_oid = hash_object_write(f, project)
    region_hash = hash_object_write_bytes(extract_region(source.encode(), loc), project)
    return Artifact(
        path=rel,
        fingerprint=RegionFingerprint(file_blob_oid=file_oid, region_hash=region_hash),
        locator=loc,
    )


def test_region_healthy_when_symbol_unchanged(project: Path):
    art = _py_region_artifact(project, "m.py", _REGION_SRC, "alpha")
    assert check_artifact(art, project).state == ArtifactState.HEALTHY


def test_region_healthy_when_other_code_changes(project: Path):
    # The core promise of section locators: editing `beta` must NOT drift a
    # tether on `alpha`. A whole-file tether would go DRIFTED here.
    art = _py_region_artifact(project, "m.py", _REGION_SRC, "alpha")
    (project / "m.py").write_text(_REGION_SRC.replace("return y * 2", "return y * 99"))
    assert check_artifact(art, project).state == ArtifactState.HEALTHY


def test_region_drifted_when_symbol_body_changes(project: Path):
    art = _py_region_artifact(project, "m.py", _REGION_SRC, "alpha")
    (project / "m.py").write_text(_REGION_SRC.replace("return x + 1", "return x + 100"))
    assert check_artifact(art, project).state == ArtifactState.DRIFTED


def test_region_broken_when_symbol_renamed(project: Path):
    art = _py_region_artifact(project, "m.py", _REGION_SRC, "alpha")
    (project / "m.py").write_text(_REGION_SRC.replace("def alpha", "def renamed"))
    assert check_artifact(art, project).state == ArtifactState.BROKEN


def test_region_normalization_rescues_crlf(project: Path):
    art = _py_region_artifact(project, "m.py", _REGION_SRC, "alpha")
    (project / "m.py").write_bytes(_REGION_SRC.replace("\n", "\r\n").encode())
    c = check_artifact(art, project)
    assert c.state == ArtifactState.HEALTHY
    assert c.normalization_rescued is True


def test_region_diff_labels_selector(project: Path):
    art = _py_region_artifact(project, "m.py", _REGION_SRC, "alpha")
    (project / "m.py").write_text(_REGION_SRC.replace("return x + 1", "return x + 100"))
    out = artifact_diff(art, project)
    assert "m.py::alpha" in out
    assert "-    return x + 1\n" in out
    assert "+    return x + 100\n" in out


# --- markdown region artifacts ---------------------------------------------

_MD_SRC = """# Doc

## Alpha

Alpha body.

## Beta

Beta body.
"""


def _md_region_artifact(
    project: Path, rel: str, source: str, selector: str
) -> Artifact:
    f = project / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(source)
    loc = Locator(kind="heading", lang="markdown", selector=selector)
    file_oid = hash_object_write(f, project)
    region_hash = hash_object_write_bytes(extract_region(source.encode(), loc), project)
    return Artifact(
        path=rel,
        fingerprint=RegionFingerprint(file_blob_oid=file_oid, region_hash=region_hash),
        locator=loc,
    )


def test_md_region_healthy_when_section_unchanged(project: Path):
    art = _md_region_artifact(project, "d.md", _MD_SRC, "Doc/Alpha")
    assert check_artifact(art, project).state == ArtifactState.HEALTHY


def test_md_region_healthy_when_other_section_changes(project: Path):
    # Editing Beta must not drift a tether on Alpha — the section-locator promise.
    art = _md_region_artifact(project, "d.md", _MD_SRC, "Doc/Alpha")
    (project / "d.md").write_text(_MD_SRC.replace("Beta body.", "Beta body, revised."))
    assert check_artifact(art, project).state == ArtifactState.HEALTHY


def test_md_region_drifted_when_section_body_changes(project: Path):
    art = _md_region_artifact(project, "d.md", _MD_SRC, "Doc/Alpha")
    (project / "d.md").write_text(
        _MD_SRC.replace("Alpha body.", "Alpha body, revised.")
    )
    assert check_artifact(art, project).state == ArtifactState.DRIFTED


def test_md_region_broken_when_heading_renamed(project: Path):
    art = _md_region_artifact(project, "d.md", _MD_SRC, "Doc/Alpha")
    (project / "d.md").write_text(_MD_SRC.replace("## Alpha", "## Renamed"))
    assert check_artifact(art, project).state == ArtifactState.BROKEN


def test_md_region_diff_labels_selector(project: Path):
    art = _md_region_artifact(project, "d.md", _MD_SRC, "Doc/Alpha")
    (project / "d.md").write_text(
        _MD_SRC.replace("Alpha body.", "Alpha body, revised.")
    )
    out = artifact_diff(art, project)
    assert "d.md::Doc/Alpha" in out
    assert "-Alpha body.\n" in out
    assert "+Alpha body, revised.\n" in out
