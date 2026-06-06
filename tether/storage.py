from __future__ import annotations

from pathlib import Path

import msgspec

from .errors import InvalidTetherError, TetherNotFoundError
from .model import Tether, validate, validate_tether_id
from .project import tethers_dir


def _record_tether_path(project_root: Path, tether_id: str) -> Path:
    # The id becomes a filename component; validating (and canonicalizing) it
    # here keeps caller-supplied ids from escaping the tethers directory.
    return tethers_dir(project_root) / f"{validate_tether_id(tether_id)}.json"


def save_tether(project_root: Path, t: Tether) -> Path:
    validate(t)
    raw = msgspec.json.encode(t, order="sorted")
    pretty = msgspec.json.format(raw, indent=2)
    path = _record_tether_path(project_root, t.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pretty + b"\n")
    return path


def _decode_tether(path: Path) -> Tether:
    """Decode and validate one record; raises InvalidTetherError without path context.

    Callers that report per-file errors (`load_all_tethers`) already carry the
    path alongside the message, so it is left out here; `load_tether` adds it.
    """
    try:
        t = msgspec.json.decode(path.read_bytes(), type=Tether)
    except msgspec.ValidationError as e:
        raise InvalidTetherError(f"schema error: {e}") from e
    except msgspec.DecodeError as e:
        raise InvalidTetherError(f"invalid JSON: {e}") from e
    validate(t)
    return t


def load_tether(project_root: Path, tether_id: str) -> Tether:
    path = _record_tether_path(project_root, tether_id)
    if not path.exists():
        raise TetherNotFoundError(f"no tether record at {path}")
    try:
        return _decode_tether(path)
    except InvalidTetherError as e:
        raise InvalidTetherError(f"{path}: {e}") from e


def delete_tether(project_root: Path, tether_id: str) -> None:
    path = _record_tether_path(project_root, tether_id)
    if not path.exists():
        raise TetherNotFoundError(f"no tether record at {path}")
    path.unlink()


class LoadTethersResult(msgspec.Struct, frozen=True, kw_only=True):
    tethers: list[Tether]
    errors: list[tuple[Path, str]]


def load_all_tethers(project_root: Path) -> LoadTethersResult:
    tethers: list[Tether] = []
    errors: list[tuple[Path, str]] = []
    d = tethers_dir(project_root)
    if not d.is_dir():
        return LoadTethersResult(tethers=[], errors=[])
    for path in sorted(d.glob("*.json")):
        try:
            tethers.append(_decode_tether(path))
        except InvalidTetherError as e:
            errors.append((path, str(e)))
    return LoadTethersResult(tethers=tethers, errors=errors)


def find_by_path(project_root: Path, rel_path: str) -> LoadTethersResult:
    """Return tethers whose `a.path` or `b.path` equals `rel_path`.

    Path comparison is exact string equality on the stored project-relative
    POSIX form. Load errors are surfaced via the returned `LoadTethersResult` so the
    caller can decide whether to report them.
    """
    result = load_all_tethers(project_root)
    matches = [t for t in result.tethers if rel_path in (t.a.path, t.b.path)]
    return LoadTethersResult(tethers=matches, errors=result.errors)
