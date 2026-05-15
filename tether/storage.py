from __future__ import annotations

from pathlib import Path

import msgspec

from .errors import InvalidTetherError, TetherNotFoundError
from .model import Tether, validate
from .project import tethers_dir


def record_path(project_root: Path, tether_id: str) -> Path:
    return tethers_dir(project_root) / f"{tether_id}.json"


def save(project_root: Path, t: Tether) -> Path:
    validate(t)
    raw = msgspec.json.encode(t, order="sorted")
    pretty = msgspec.json.format(raw, indent=2)
    path = record_path(project_root, t.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pretty + b"\n")
    return path


def load(project_root: Path, tether_id: str) -> Tether:
    path = record_path(project_root, tether_id)
    if not path.exists():
        raise TetherNotFoundError(f"no tether record at {path}")
    try:
        t = msgspec.json.decode(path.read_bytes(), type=Tether)
    except msgspec.ValidationError as e:
        raise InvalidTetherError(f"{path}: schema error: {e}") from e
    except msgspec.DecodeError as e:
        raise InvalidTetherError(f"{path}: invalid JSON: {e}") from e
    validate(t)
    return t


def delete(project_root: Path, tether_id: str) -> None:
    path = record_path(project_root, tether_id)
    if not path.exists():
        raise TetherNotFoundError(f"no tether record at {path}")
    path.unlink()


class LoadResult(msgspec.Struct, frozen=True, kw_only=True):
    tethers: list[Tether]
    errors: list[tuple[Path, str]]


def load_all(project_root: Path) -> LoadResult:
    tethers: list[Tether] = []
    errors: list[tuple[Path, str]] = []
    d = tethers_dir(project_root)
    if not d.is_dir():
        return LoadResult(tethers=[], errors=[])
    for path in sorted(d.glob("*.json")):
        try:
            t = msgspec.json.decode(path.read_bytes(), type=Tether)
            validate(t)
            tethers.append(t)
        except (msgspec.DecodeError, msgspec.ValidationError, InvalidTetherError) as e:
            errors.append((path, str(e)))
    return LoadResult(tethers=tethers, errors=errors)
