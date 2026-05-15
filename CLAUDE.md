# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@tether-vault/DICTION.md

## Project status

Work-in-progress with **no active users**. Nothing ships on compatibility guarantees yet: rename APIs, reshape JSON on disk, and change the CLI surface freely. No migration code, deprecation shims, or back-compat branches needed unless asked for explicitly.

Source code lives in `tether/`. Design intent and any non-code documentation live in `tether-vault/` — treat the vault as the source of truth for design questions, and the code as the source of truth for current behavior.

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

- `playground/` at the repo root is gitignored; use it as a throwaway project dir for hand-experimentation (`cd playground && uv run tether init . && ...`). Nothing committed there, recreate as needed.

## Testing notes

- `tests/conftest.py` provides a `project` fixture that returns an initialized project root. Prefer it over manually constructing `.tether/` directories.
- No `pytest-timeout` plugin installed — don't add `@pytest.mark.timeout` decorators.

## Documentation

All project documentation — design notes, research, specs, integration investigations — lives in `tether-vault/`, which is an Obsidian vault. Put new docs there, not at the repo root or under `src/`. Treat the vault as the single source of truth for everything that isn't code, tests, or `README.md` / `CLAUDE.md` themselves. Filenames use Title-Case-Kebab (e.g. `Tether-Design-MVP.md`) so Obsidian's wikilinks stay predictable; acronyms stay uppercase.

Ongoing Claude Code integration research (hooks, MCP, skills, subagents) lives in the vault as well — browse it there rather than looking for a specific file path here, since the set will grow.
