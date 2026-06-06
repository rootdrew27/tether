import subprocess
from pathlib import Path

from tether.git import find_renames, hash_object_write
from tether.model import Artifact, Tether
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
    c = check_artifact("x.md", fp, project)
    assert c.state == ArtifactState.HEALTHY
    assert c.normalization_rescued is False
    assert c.rename_candidates == ()


def test_drifted_when_content_changes(project: Path):
    f = project / "x.md"
    f.write_text("hello\n")
    fp = hash_object_write(f, project)
    f.write_text("hello world\n")
    c = check_artifact("x.md", fp, project)
    assert c.state == ArtifactState.DRIFTED
    assert c.normalization_rescued is False


def test_broken_when_file_missing(project: Path):
    c = check_artifact("nope.md", "a" * 40, project)
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
    c = check_artifact("x.md", fp, project)
    assert c.state == ArtifactState.HEALTHY
    assert c.normalization_rescued is True


def test_normalization_rescues_trailing_whitespace(project: Path):
    f = project / "x.md"
    f.write_bytes(b"hello\nworld\n")
    fp = hash_object_write(f, project)
    f.write_bytes(b"hello   \nworld\t\n")
    c = check_artifact("x.md", fp, project)
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

    out = artifact_diff("x.md", fp, project)
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

    out = artifact_diff("x.md", fp, project)
    assert f' BASE = "{own_path}"\n' in out  # context line untouched
    assert "-old\n" in out
    assert "+new\n" in out


def test_find_renames_missing_blob_does_not_crash(project: Path):
    # A fingerprint whose blob is not in the object store (e.g. GC'd) is filtered out;
    # detection degrades to no candidate rather than raising.
    assert find_renames([("gone.py", "0" * 40)], project) == {}
