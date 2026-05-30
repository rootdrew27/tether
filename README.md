# tether

A content-fingerprinted relationship annotation layer, layered on git.

Create durable, content-fingerprinted links ("tethers") between any two files
in a project — say, a doc and the code it describes — and tether will tell you
when one side drifts from the other. State lives as one JSON file per tether
under `.tether/tethers/`, so the graph is reviewable in pull requests and
travels with the repo.

> Status: WIP, no released users. The CLI and on-disk JSON shape may change.
> Design intent and rationale live in [`tether-vault/`](tether-vault/) (an
> Obsidian vault); the canonical design doc is
> [`Tether-Design-MVP.md`](tether-vault/design/Tether-Design-MVP.md).

## Concepts

| Term | Meaning |
|---|---|
| **Tether** | A declaration of connection between two **artifacts**, with content fingerprints recorded at both ends and a required description. |
| **Artifact** | One end of a tether: a path plus a locator. In MVP the locator is always `WholeFile`. |
| **Fingerprint** | The git blob OID of the artifact's content, captured at tether creation or refresh. |
| **Drift** | The condition where current content no longer matches the fingerprint. |
| **HEALTHY / DRIFTED / BROKEN** | Per-artifact state. A tether is **WEAKENED** when one side is HEALTHY and the other DRIFTED. |

Full glossary: [`DICTION.md`](tether-vault/DICTION.md) (MVP vocabulary, matches current code). Forward-state model lives in [`DICTION-Future.md`](tether-vault/design/future/DICTION-Future.md).

## Install

```bash
uv sync
uv run tether --help
```

Requires Python 3.12+ and a git repository (`tether init` refuses outside one).

## Quick start

```bash
cd my-project
uv run tether init
uv run tether add docs/auth.md src/auth.py --description "Covers password reset and 2FA enrollment."
uv run tether status
# edit src/auth.py ...
uv run tether status         # src/auth.py now reports DRIFTED, aggregate WEAKENED
uv run tether status <id>    # full per-artifact view with unified diff
# bring the doc in line, then:
uv run tether refresh <id>   # re-fingerprint both artifacts together
```

## CLI

| Command | Purpose |
|---|---|
| `tether init` | Initialize `.tether/` in the current git repo. |
| `tether init claude-code` | Wire up Claude Code hooks and a memory fragment. |
| `tether add A B --description "..."` | Create a tether. `--description` is required. |
| `tether status [ID] [--json] [--diff/--no-diff]` | Report tether state; per-artifact for one ID, summary for all. |
| `tether show` | List every tether with its description, regardless of state. Reads records from disk; no drift check. |
| `tether refresh ID` | Re-fingerprint both artifacts; asserts they are now aligned. |
| `tether update ID [--a-path ...] [--b-path ...] [--description ...]` | Modify a tether without touching fingerprints. |
| `tether mv OLD_PATH NEW_PATH` | Rewrite all tether artifacts pointing at `OLD_PATH` to `NEW_PATH`. |
| `tether rm ID` | Delete a tether record. |

A tether is symmetric — neither end is privileged. The two artifacts are named
`a` and `b` for stable ordering only; the relationship's meaning lives in the
required description.

## How drift works

`tether status` resolves each artifact's locator on the current on-disk bytes
and compares the result's git blob OID against the recorded fingerprint:

- **HEALTHY** — OID matches the fingerprint.
- **DRIFTED** — file resolves but content's OID differs.
- **BROKEN** — file no longer exists at the recorded path. `tether status`
  queries `git log --find-object` for paths that currently match the recorded
  blob OID and surfaces them as rename candidates.

When the raw OIDs disagree, tether re-runs the comparison through a
language-agnostic normalizer (line endings, BOM, trailing whitespace, EOF
newlines, leading-tab expansion). If the normalized hashes match, the artifact
is still HEALTHY and `tether status` notes "encoding-only drift rescued" —
the drift signal is preserved as a diff but the state is rescued. See
[`Normalization.md`](tether-vault/design/Normalization.md) for the
pipeline and its deliberate non-goals.

## Storage layout

```
project-root/
  .tether/
    tethers/
      <uuid7>.json    # one tether per file, sorted-key pretty JSON
```

Tether IDs are UUIDv7, so directory sort order is also creation order. Records
are committed alongside content; `git log .tether/tethers/<id>.json` is the
audit trail for a tether (created, refreshed, retargeted).

## Claude Code integration

`tether init claude-code` installs:

- A `.tether/tether.md` memory fragment teaching Claude the tether vocabulary
  and how to react to drift, imported from the project's `CLAUDE.md`.
- `SessionStart` and `Stop` hooks (in `.claude/settings.local.json`) that
  surface drifted and broken tethers as context at the start of a session
  and as attention items when Claude finishes a turn.
- `permissions.deny` entries (in `.claude/settings.json`) that block direct
  edits anywhere under `.tether/` so Claude goes through the CLI rather than
  rewriting fingerprints by hand, plus `permissions.allow` entries
  pre-approving the tether subcommands the agent will routinely invoke.

The hooks shell out to `tether hook claude-code session-start` and
`tether hook claude-code stop`. Both read `cwd` from stdin and emit the
relevant hook contract (markdown stdout for session-start; a JSON `stop`
block for stop). See
[`Claude-Code-Integration.md`](tether-vault/claude-code/Claude-Code-Integration.md).

## Development

```bash
uv sync
uv run pytest
uv run ruff check
uv run ruff format
uv run pyright
```

A throwaway `playground/` directory at the repo root is gitignored — use it
for hand-experimentation (`cd playground && uv run tether init . && ...`).
