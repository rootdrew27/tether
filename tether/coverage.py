from __future__ import annotations

from pathlib import Path

import msgspec

from .git import ls_files
from .storage import load_all_tethers

# The state directory is committed but is tether-owned infrastructure, not
# project content; counting its files would deflate coverage on exactly the
# projects using tether most.
_TETHER_DIR_PREFIX = ".tether/"


class Coverage(msgspec.Struct, frozen=True, kw_only=True):
    tethered: list[str]
    untethered: list[str]
    errors: list[tuple[Path, str]]

    @property
    def tracked(self) -> int:
        return len(self.tethered) + len(self.untethered)


def compute_coverage(root: Path) -> Coverage:
    """Partition git-tracked files by whether any tether references them.

    Structural-only: no drift computation, no fingerprint checks. A path
    referenced by a BROKEN tether still counts as tethered (coverage answers
    "is it tethered?", not "is it healthy?"); a recorded path that is not a
    tracked file simply doesn't intersect.
    """
    tracked = {p for p in ls_files(root) if not p.startswith(_TETHER_DIR_PREFIX)}
    result = load_all_tethers(root)
    referenced = {p for t in result.tethers for p in (t.a.path, t.b.path)}
    return Coverage(
        tethered=sorted(tracked & referenced),
        untethered=sorted(tracked - referenced),
        errors=result.errors,
    )
