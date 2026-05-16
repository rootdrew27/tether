"""Reset the local ``playground/`` to its initial state.

Usage:
    uv run python scripts/reset_playground.py

What it does:
    Force-resets the ``fresh`` branch in ``playground/`` to the ``fresh``
    tag (the immutable pristine commit), checks it out, removes every
    untracked and ignored file (``.venv``, ``.pytest_cache``,
    ``__pycache__``, ``.tether/``, ``.claude/``, hand-edits), then runs
    ``uv sync`` to recreate the virtualenv.

    The tag is what guarantees idempotence: if you commit on the ``fresh``
    branch while experimenting, the next reset moves the branch back to
    the tag and discards those commits (still recoverable via reflog).

Bootstrapping your own playground:
    ``playground/`` is gitignored from the main repo, so each clone starts
    without one. To create yours:

        mkdir playground && cd playground
        # drop in whatever source you want as the pristine state
        git init -q
        git add <files>            # do NOT add .tether/, .claude/, CLAUDE.md
        git commit -m "fresh"
        git branch -m fresh        # rename default branch to fresh
        git tag fresh              # immutable pointer to the pristine commit

    Once the ``fresh`` tag exists, this script will work. See
    ``tether-vault/`` for design notes.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PLAYGROUND = Path(__file__).resolve().parent.parent / "playground"


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=PLAYGROUND, check=True)


def main() -> int:
    if not (PLAYGROUND / ".git").is_dir():
        sys.stderr.write(
            f"{PLAYGROUND} is not a git repo. See the module docstring for "
            "bootstrap instructions.\n"
        )
        return 1

    run(["git", "checkout", "-f", "-B", "fresh", "refs/tags/fresh"])
    run(["git", "clean", "-fdx"])
    run(["uv", "sync"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
