# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@tether-vault/DICTION.md

## Project status

Work-in-progress with **no active users**. Nothing ships on compatibility guarantees yet: rename APIs, reshape JSON on disk, and change the CLI surface freely. No migration code, deprecation shims, or back-compat branches needed unless asked for explicitly.

Source code lives in `tether/`. Non-code documentation is split between `tether-vault/` (human-authored) and `agent-notes/` (Claude-maintained) — see **Vault access** below. The code is the source of truth for current behavior; the docs are the source of truth for design questions.

## Vault access (Claude write boundary)

`tether-vault/` is **human-authored and read-only for Claude.** It holds the human-owned material — the constitution, the canonical glossary (`DICTION.md`), case studies, evaluations, the `TODO.md`, and the Obsidian / playground conventions. Claude may freely **read** anything under the vault, but must not create, edit, move, or delete files there. To change a vault doc, propose a diff for a human to apply rather than editing in place.

The boundary is enforced by deny rules on `Edit`/`Write`/`MultiEdit`/`NotebookEdit` for `/tether-vault/**` in `.claude/settings.json` (committed). Those rules block the editing tools but **not** shell writes — and some write-capable Bash verbs (`tee`, `mkdir`) are pre-approved in the allowlist, so they run without a prompt. Claude must therefore honor the boundary from Bash by discipline: **never run any shell command that creates, modifies, moves, renames, or deletes a path under `tether-vault/`** — this includes (but is not limited to) `tee`, `mkdir`, `mv`, `cp`, `sed -i`, `rm`, and output redirection (`>` / `>>`). Reading from the vault is always fine; writing to it by any means is not.

Claude's own writable space is `agent-notes/` at the repo root — outside the vault, and outside Obsidian. It holds the engineering documentation Claude maintains — the design specs (`design/`), research (`research/`), and the Claude Code integration docs (`claude-code/`) — plus any working notes and generated logs.

This is project infrastructure for working *on* tether; it is not a feature of the tether package and is never installed into a user's project.

## Common commands

All commands run via `uv` (Python 3.12, hatchling build backend).

```bash
uv sync                                         # install deps + dev group
uv run pytest                                   # full suite
uv run pytest tests/test_status.py              # one file
uv run pytest tests/test_status.py::test_healthy_when_oid_matches  # one test
uv run pytest -k normalize                      # by keyword
uv run ruff check                               # lint
uv run ruff format                              # format
uv run pyright                                  # type check
uv run tether --help                            # exercise the CLI locally
```

## Local dev affordances

- `playground/` at the repo root is gitignored — a throwaway project dir for hand-experimentation. It has its own local git repo anchored at the `fresh` tag (pristine source); reset it with `uv run python scripts/reset_playground.py`. See `tether-vault/other/Playground.md` for the convention and bootstrap steps.

## Testing notes

- `tests/conftest.py` provides a `project` fixture that returns an initialized project root. Prefer it over manually constructing `.tether/` directories.
- No `pytest-timeout` plugin installed — don't add `@pytest.mark.timeout` decorators.

## Documentation

Project documentation is split by ownership (see **Vault access** above):

- **`tether-vault/`** — Obsidian vault, human-authored, read-only for Claude. The constitution, the canonical glossary (`DICTION.md`), case studies, evaluations, and the Obsidian / playground conventions.
- **`agent-notes/`** — Claude-writable. The engineering documentation Claude maintains: design specs (`design/`, incl. `design/future/`), research (`research/`), and the Claude Code integration docs (`claude-code/`, incl. `strategies/`).

New docs Claude writes go under `agent-notes/`, never in the vault or under `src/`. Filenames use Title-Case-Kebab (e.g. `Tether-Design-MVP.md`); acronyms stay uppercase. The code is the source of truth for current behavior; these docs are the source of truth for design intent and rationale.
