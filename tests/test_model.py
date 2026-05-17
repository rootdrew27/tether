import uuid

import pytest

from tether.errors import InvalidTetherError
from uuid_utils import uuid7

from tether.model import Artifact, Tether, validate


def _make(
    *,
    a_path: str = "a.md",
    b_path: str = "b.py",
    a_fp: str = "a" * 40,
    b_fp: str = "b" * 40,
    description: str = "d",
    created_at: str = "2026-05-13T10:00:00Z",
    refreshed_at: str = "2026-05-13T10:00:00Z",
    id: str | None = None,
) -> Tether:
    return Tether(
        id=id or str(uuid7()),
        schema_version=1,
        a=Artifact(path=a_path, fingerprint=a_fp),
        b=Artifact(path=b_path, fingerprint=b_fp),
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


def test_self_tether_rejected():
    with pytest.raises(InvalidTetherError, match="self-tethers"):
        validate(_make(a_path="x.md", b_path="x.md"))


def test_empty_fingerprint_rejected():
    with pytest.raises(InvalidTetherError, match="fingerprints"):
        validate(_make(a_fp=""))


def test_empty_description_rejected():
    with pytest.raises(InvalidTetherError, match="description"):
        validate(_make(description=""))


def test_whitespace_only_description_rejected():
    with pytest.raises(InvalidTetherError, match="description"):
        validate(_make(description="   \n\t "))


def test_refreshed_before_created_rejected():
    with pytest.raises(InvalidTetherError, match="later than"):
        validate(
            _make(
                created_at="2026-05-13T10:00:00Z",
                refreshed_at="2026-05-12T10:00:00Z",
            )
        )
