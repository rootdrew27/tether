from pathlib import Path

import pytest

from tether.errors import InvalidTetherError, TetherNotFoundError
from tether.model import Artifact, Tether
from uuid_utils import uuid7

from tether.storage import (
    delete_tether,
    load_tether,
    load_all_tethers,
    _record_tether_path,
    save_tether,
)


def _make_tether(id_: str | None = None) -> Tether:
    return Tether(
        id=id_ or str(uuid7()),
        schema_version=1,
        a=Artifact(path="a.md", fingerprint="a" * 40),
        b=Artifact(path="b.py", fingerprint="b" * 40),
        description="d",
        created_at="2026-05-13T10:00:00Z",
        refreshed_at="2026-05-13T10:00:00Z",
    )


def test_save_and_load_roundtrip(project: Path):
    t = _make_tether()
    save_tether(project, t)
    loaded = load_tether(project, t.id)
    assert loaded == t


def test_load_missing_raises(project: Path):
    with pytest.raises(TetherNotFoundError):
        load_tether(project, "0192abc1-23ef-7890-abcd-ef0123456789")


def test_delete_tether_removes_file(project: Path):
    t = _make_tether()
    save_tether(project, t)
    assert _record_tether_path(project, t.id).exists()
    delete_tether(project, t.id)
    assert not _record_tether_path(project, t.id).exists()


def test_delete_tether_missing_raises(project: Path):
    with pytest.raises(TetherNotFoundError):
        delete_tether(project, "0192abc1-23ef-7890-abcd-ef0123456789")


def test_load_tether_rejects_non_uuid_id(project: Path):
    with pytest.raises(InvalidTetherError, match="UUID"):
        load_tether(project, "../../secret")


def test_delete_tether_rejects_traversal_id(project: Path):
    # "../../" from .tether/tethers/ lands at the project root; a crafted id
    # must not reach files outside the tethers directory.
    secret = project / "secret.json"
    secret.write_text("{}\n")
    with pytest.raises(InvalidTetherError, match="UUID"):
        delete_tether(project, "../../secret")
    assert secret.exists()


def test_load_all_tethers_returns_sorted_uuid_order(project: Path):
    ts = [_make_tether() for _ in range(3)]
    for t in ts:
        save_tether(project, t)
    result = load_all_tethers(project)
    ids = [t.id for t in result.tethers]
    assert ids == sorted(ids)
    assert result.errors == []


def test_load_all_tethers_skips_corrupt_records(project: Path):
    t = _make_tether()
    save_tether(project, t)
    bad = project / ".tether" / "tethers" / "corrupt.json"
    bad.write_text("{not valid json")
    result = load_all_tethers(project)
    assert [x.id for x in result.tethers] == [t.id]
    assert len(result.errors) == 1
    assert result.errors[0][0] == bad


def test_load_all_tethers_skips_invariant_violations(project: Path):
    t = _make_tether()
    save_tether(project, t)
    bad = project / ".tether" / "tethers" / "0192abc1-23ef-7890-abcd-ef0123456789.json"
    bad.write_text(
        '{"id":"0192abc1-23ef-7890-abcd-ef0123456789","schema_version":1,'
        '"a":{"path":"same.md","fingerprint":"a"},"b":{"path":"same.md","fingerprint":"b"},'
        '"description":"d",'
        '"created_at":"2026-05-13T10:00:00Z","refreshed_at":"2026-05-13T10:00:00Z"}'
    )
    result = load_all_tethers(project)
    assert [x.id for x in result.tethers] == [t.id]
    assert len(result.errors) == 1
    assert "self-tethers" in result.errors[0][1]


def test_load_validates_on_read(project: Path):
    bad = project / ".tether" / "tethers" / "0192abc1-23ef-7890-abcd-ef0123456789.json"
    bad.write_text(
        '{"id":"0192abc1-23ef-7890-abcd-ef0123456789","schema_version":1,'
        '"a":{"path":"same.md","fingerprint":"a"},"b":{"path":"same.md","fingerprint":"b"},'
        '"description":"d",'
        '"created_at":"2026-05-13T10:00:00Z","refreshed_at":"2026-05-13T10:00:00Z"}'
    )
    with pytest.raises(InvalidTetherError):
        load_tether(project, "0192abc1-23ef-7890-abcd-ef0123456789")
