import uuid

import pytest

from tether.errors import InvalidTetherError
from uuid_utils import uuid7

from tether.model import Artifact, Locator, RegionFingerprint, Tether, validate


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
    with pytest.raises(InvalidTetherError, match="fingerprint"):
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


# --- region (section-locator) artifacts ------------------------------------


def _region_fp() -> RegionFingerprint:
    return RegionFingerprint(file_blob_oid="a" * 40, region_hash="b" * 40)


def _make_region(
    *,
    schema_version: int = 2,
    a_locator: Locator | None = None,
    a_fp: str | RegionFingerprint | None = None,
    b_path: str = "b.md",
) -> Tether:
    loc = a_locator or Locator(kind="symbol", lang="python", selector="alpha")
    return Tether(
        id=str(uuid7()),
        schema_version=schema_version,
        a=Artifact(path="a.py", fingerprint=a_fp or _region_fp(), locator=loc),
        b=Artifact(path=b_path, fingerprint="b" * 40),
        description="d",
        created_at="2026-05-13T10:00:00Z",
        refreshed_at="2026-05-13T10:00:00Z",
    )


def test_valid_region_tether_passes():
    validate(_make_region())


def test_region_requires_schema_version_2():
    with pytest.raises(InvalidTetherError, match="schema_version 2"):
        validate(_make_region(schema_version=1))


def test_region_empty_selector_rejected():
    loc = Locator(kind="symbol", lang="python", selector="  ")
    with pytest.raises(InvalidTetherError, match="selector"):
        validate(_make_region(a_locator=loc))


def test_region_unsupported_lang_rejected():
    loc = Locator(kind="symbol", lang="cobol", selector="alpha")
    with pytest.raises(InvalidTetherError, match="lang"):
        validate(_make_region(a_locator=loc))


def test_valid_markdown_region_tether_passes():
    # validate() checks the (kind, lang) pairing, not the path extension.
    loc = Locator(kind="heading", lang="markdown", selector="Installation/Requirements")
    validate(_make_region(a_locator=loc))


def test_region_crossed_kind_lang_rejected():
    # Both kind and lang are individually known, but the pairing is not supported.
    loc = Locator(kind="heading", lang="python", selector="alpha")
    with pytest.raises(InvalidTetherError, match="kind/lang"):
        validate(_make_region(a_locator=loc))


def test_region_string_fingerprint_rejected():
    with pytest.raises(InvalidTetherError, match="region fingerprint"):
        validate(_make_region(a_fp="a" * 40))


def test_same_path_different_locator_allowed():
    # Two distinct regions of one file are not a self-tether.
    a_loc = Locator(kind="symbol", lang="python", selector="alpha")
    b_loc = Locator(kind="symbol", lang="python", selector="beta")
    t = Tether(
        id=str(uuid7()),
        schema_version=2,
        a=Artifact(path="m.py", fingerprint=_region_fp(), locator=a_loc),
        b=Artifact(path="m.py", fingerprint=_region_fp(), locator=b_loc),
        description="d",
        created_at="2026-05-13T10:00:00Z",
        refreshed_at="2026-05-13T10:00:00Z",
    )
    validate(t)


def test_same_path_same_locator_rejected():
    loc = Locator(kind="symbol", lang="python", selector="alpha")
    t = Tether(
        id=str(uuid7()),
        schema_version=2,
        a=Artifact(path="m.py", fingerprint=_region_fp(), locator=loc),
        b=Artifact(path="m.py", fingerprint=_region_fp(), locator=loc),
        description="d",
        created_at="2026-05-13T10:00:00Z",
        refreshed_at="2026-05-13T10:00:00Z",
    )
    with pytest.raises(InvalidTetherError, match="self-tethers"):
        validate(t)
