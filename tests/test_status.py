import subprocess
from pathlib import Path

from tether.git import hash_object_write
from tether.status import (
    AggregateState,
    ArtifactState,
    aggregate,
    check_artifact,
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


def test_broken_surfaces_rename_candidates(project: Path):
    f = project / "src" / "auth.py"
    f.parent.mkdir(parents=True)
    f.write_text("def auth(): pass\n")
    fp = hash_object_write(f, project)
    subprocess.run(["git", "add", "-A"], cwd=project, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=project, check=True)
    subprocess.run(
        ["git", "mv", "src/auth.py", "src/authentication.py"], cwd=project, check=True
    )
    subprocess.run(["git", "commit", "-q", "-m", "rename"], cwd=project, check=True)
    c = check_artifact("src/auth.py", fp, project)
    assert c.state == ArtifactState.BROKEN
    assert "src/authentication.py" in c.rename_candidates


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


def test_aggregate_one_drifted_is_weakened():
    assert (
        aggregate(ArtifactState.HEALTHY, ArtifactState.DRIFTED)
        == AggregateState.WEAKENED
    )
    assert (
        aggregate(ArtifactState.DRIFTED, ArtifactState.HEALTHY)
        == AggregateState.WEAKENED
    )


def test_aggregate_both_drifted_is_drifted():
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
