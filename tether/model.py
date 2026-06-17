from __future__ import annotations

import uuid

import msgspec

from .errors import InvalidTetherError

# The (kind, lang) locator combinations this build can resolve. A kind names the
# resolution strategy and lang the grammar; only these pairings are valid, so the
# set is pairs rather than two independent axes (a `heading` kind is meaningful
# only for `markdown`, `symbol` only for `python`). The model and the locator
# engine (tether/locators.py) must agree on this set; the file-extension →
# language map that drives add-time inference lives in the CLI.
SUPPORTED_LOCATORS: frozenset[tuple[str, str]] = frozenset(
    {("symbol", "python"), ("heading", "markdown")}
)

# Record schema versions this build accepts. A locator-bearing record is written
# as 2 (its fingerprint is a pair, not a string); whole-file records stay 1, so
# every pre-locator record remains valid and serializes unchanged.
SUPPORTED_SCHEMA_VERSIONS: frozenset[int] = frozenset({1, 2})


class Locator(msgspec.Struct, frozen=True, kw_only=True):
    """Selects a *region* of a file rather than the whole file.

    `kind` is the resolution strategy, `lang` the parser language, and `selector`
    the human-authored address. The supported pairings are `symbol`/`python` (a
    dotted symbol path like `Calculator.multiply`) and `heading`/`markdown` (a
    slash-separated heading path like `Installation/Requirements`). A locator
    names the region by what it is, so it survives edits elsewhere in the file.
    """

    kind: str
    lang: str
    selector: str


class RegionFingerprint(msgspec.Struct, frozen=True, kw_only=True):
    """The fingerprint of a located region.

    `file_blob_oid` is the whole-file git blob OID (so git's file-rename
    detection works identically to a whole-file artifact); `region_hash` is the
    git blob OID of the located region's bytes and is the drift signal.
    """

    file_blob_oid: str
    region_hash: str


class Artifact(msgspec.Struct, frozen=True, kw_only=True, omit_defaults=True):
    """One end of a tether.

    A whole-file artifact has `locator is None` and a `fingerprint` that is the
    file's git blob OID (a string). A region artifact carries a `locator` and a
    `RegionFingerprint`. `omit_defaults=True` keeps a whole-file artifact's
    on-disk JSON identical to the pre-locator format (no `"locator": null`).
    """

    path: str
    fingerprint: str | RegionFingerprint
    locator: Locator | None = None

    @property
    def file_oid(self) -> str:
        """The whole-file blob OID, regardless of artifact shape.

        This is the OID git's rename detector scores against the working tree,
        so file-level rename detection is identical for whole-file and region
        artifacts.
        """
        fp = self.fingerprint
        return fp if isinstance(fp, str) else fp.file_blob_oid


class Tether(msgspec.Struct, frozen=True, kw_only=True):
    id: str
    schema_version: int
    a: Artifact
    b: Artifact
    description: str
    created_at: str
    refreshed_at: str


def validate_tether_id(tether_id: str) -> str:
    """Validate a tether id and return its canonical hyphenated lowercase form."""
    try:
        u = uuid.UUID(tether_id)
    except ValueError as e:
        raise InvalidTetherError(f"invalid UUID {tether_id!r}: {e}") from e
    if u.version != 7:
        raise InvalidTetherError(f"UUID {tether_id} is not version 7")
    return str(u)


def validate(t: Tether) -> None:
    validate_tether_id(t.id)

    if t.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise InvalidTetherError(
            f"unsupported schema_version {t.schema_version}; "
            f"this build supports {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
        )

    if not t.a.path or not t.b.path:
        raise InvalidTetherError("artifact paths must be non-empty")

    _validate_artifact(t, t.a, "a")
    _validate_artifact(t, t.b, "b")

    # Two artifacts addressing the same content (same path AND same locator) are
    # a self-tether. Two regions of one file, or a region and its whole file, are
    # distinct artifacts and allowed.
    if t.a.path == t.b.path and t.a.locator == t.b.locator:
        raise InvalidTetherError(
            "a and b address the same content (same path and locator): "
            "self-tethers are not allowed"
        )

    if not t.description.strip():
        raise InvalidTetherError("description must be non-empty")

    if t.created_at > t.refreshed_at:
        raise InvalidTetherError(
            f"created_at ({t.created_at}) is later than refreshed_at ({t.refreshed_at})"
        )


def _validate_artifact(t: Tether, a: Artifact, label: str) -> None:
    if a.locator is None:
        if not isinstance(a.fingerprint, str) or not a.fingerprint:
            raise InvalidTetherError(
                f"artifact {label}: whole-file fingerprint must be a non-empty string"
            )
        return

    if t.schema_version < 2:
        raise InvalidTetherError(
            f"artifact {label}: a locator requires schema_version 2 (got "
            f"{t.schema_version})"
        )
    loc = a.locator
    if not loc.kind or not loc.lang or not loc.selector.strip():
        raise InvalidTetherError(
            f"artifact {label}: locator kind, lang, and selector must be non-empty"
        )
    if (loc.kind, loc.lang) not in SUPPORTED_LOCATORS:
        raise InvalidTetherError(
            f"artifact {label}: unsupported locator kind/lang "
            f"{loc.kind!r}/{loc.lang!r}; supported: {sorted(SUPPORTED_LOCATORS)}"
        )
    fp = a.fingerprint
    if (
        not isinstance(fp, RegionFingerprint)
        or not fp.file_blob_oid
        or not fp.region_hash
    ):
        raise InvalidTetherError(
            f"artifact {label}: region fingerprint must carry a non-empty "
            "file_blob_oid and region_hash"
        )
