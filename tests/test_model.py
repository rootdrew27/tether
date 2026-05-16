import uuid

import pytest

from tether.errors import InvalidTetherError
from uuid_utils import uuid7

from tether.model import Artifact, Tether, default_bidirectional, validate


def _make(
    *,
    src_path: str = "a.md",
    dst_path: str = "b.py",
    src_fp: str = "a" * 40,
    dst_fp: str = "b" * 40,
    type_: str = "describes",
    bidirectional: bool = False,
    description: str | None = None,
    created_at: str = "2026-05-13T10:00:00Z",
    refreshed_at: str = "2026-05-13T10:00:00Z",
    id: str | None = None,
) -> Tether:
    return Tether(
        id=id or str(uuid7()),
        schema_version=1,
        src=Artifact(path=src_path, fingerprint=src_fp),
        dst=Artifact(path=dst_path, fingerprint=dst_fp),
        type=type_,  # type: ignore[arg-type]
        bidirectional=bidirectional,
        description=description,
        created_at=created_at,
        refreshed_at=refreshed_at,
    )


def test_validate_passes_on_minimal_valid_tether():
    validate(_make())


def test_invalid_uuid_rejected():
    with pytest.raises(InvalidTetherError, match="UUID"):
        validate(_make(id="not-a-uuid"))


def test_non_v7_uuid_rejected():
    v4 = str(uuid.uuid4())
    with pytest.raises(InvalidTetherError, match="version 7"):
        validate(_make(id=v4))


def test_unknown_type_rejected():
    with pytest.raises(InvalidTetherError, match="invalid type"):
        validate(_make(type_="cites"))


def test_describes_cannot_be_bidirectional():
    with pytest.raises(InvalidTetherError, match="cannot be bidirectional"):
        validate(_make(type_="describes", bidirectional=True))


def test_tests_cannot_be_bidirectional():
    with pytest.raises(InvalidTetherError, match="cannot be bidirectional"):
        validate(_make(type_="tests", bidirectional=True))


def test_references_can_be_bidirectional():
    validate(_make(type_="references", bidirectional=True))


def test_related_can_be_bidirectional():
    validate(_make(type_="related", bidirectional=True))


def test_self_tether_rejected():
    with pytest.raises(InvalidTetherError, match="self-tethers"):
        validate(_make(src_path="x.md", dst_path="x.md"))


def test_empty_fingerprint_rejected():
    with pytest.raises(InvalidTetherError, match="fingerprints"):
        validate(_make(src_fp=""))


def test_refreshed_before_created_rejected():
    with pytest.raises(InvalidTetherError, match="later than"):
        validate(
            _make(
                created_at="2026-05-13T10:00:00Z",
                refreshed_at="2026-05-12T10:00:00Z",
            )
        )


def test_default_bidirectional_per_type():
    assert default_bidirectional("related") is True
    assert default_bidirectional("describes") is False
    assert default_bidirectional("tests") is False
    assert default_bidirectional("references") is False
