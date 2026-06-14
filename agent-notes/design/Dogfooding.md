# Dogfooding

tether is dogfooded on its own repository: tethers track drift-sensitive
relationships inside tether's own source, and the Claude Code integration runs
live in this repo's development sessions. This is the project's longest-lived
real usage — graph decay and rubber-stamp-refresh failure modes only surface
with time, and this repo is the one with time on it (see
`agent-notes/research/Ecosystem-Positioning-Analysis.md`).

This document records the setup decision and its mechanics. The human-facing
operational runbook lives in the vault (`tether-vault/other/Dogfooding.md`).

## Two-binary architecture

The dogfood runs at full integration — hooks, permissions, the agent fragment,
and the onboard skill (`tether init claude-code`) — but the binary the hooks
invoke is **decoupled** from the editable working tree. Two installs coexist:

- **Editable `.venv/bin/tether`** — the dev/test loop only. `uv run pytest`,
  pyright, and exercising changes import tether from the working tree; it tracks
  edits live.
- **Pinned `.venv-tether-stable/bin/tether`** — a non-editable, in-repo venv.
  The *only* binary that touches the real `.tether/` graph: both the Claude Code
  hooks and manual `tether` commands.

### Why decouple

The hooks fire every session (`SessionStart`, `Stop`, `PreToolUse(Read)`). If
they invoked the editable install, a half-finished refactor or syntax error in
`tether/` would run inside the session's own instrumentation — the Stop hook
erroring, Read hooks throwing. Pinning to a non-editable snapshot means source
edits cannot affect the running hooks until a deliberate re-pin.

Unifying *both* the hooks and manual dogfood commands on the stable binary
removes two further failure modes:

- **CLI drift** — manual `tether` commands behave consistently mid-refactor
  instead of running whatever is half-edited.
- **Schema skew** — the real graph is read and written by exactly one version,
  so there is never a maintainer-binary-vs-hook-binary mismatch over record
  shape or the `hook claude-code` surface.

## What is installed

`tether init claude-code`, run from the stable binary, produces:

| Path | Committed? | Contents |
|---|---|---|
| `.tether/tethers/<id>.json` | yes | the tether graph (records) |
| `.tether/tether.md` | yes | the agent fragment |
| `.claude/skills/tether-onboard/SKILL.md` | yes | the onboard skill |
| `CLAUDE.md` | yes | `@.tether/tether.md` import appended |
| `.claude/settings.json` | yes | tether deny (`.tether/**`) + allow permission rules |
| `.claude/settings.local.json` | no (gitignored) | the three hooks, anchored to the stable binary |
| `.venv-tether-stable/` | no (gitignored) | the pinned binary |
| `.vscode/settings.json` | no (gitignored) | PATH canonicalization |

Hooks live in the gitignored local settings because their command embeds a
machine-specific path. Because the stable venv is *inside* the repo,
`detect_tether_command` (`tether/claude_code/settings.py`) anchors that path to
`${CLAUDE_PROJECT_DIR}/.venv-tether-stable/bin/tether` rather than an absolute
one.

## PATH canonicalization

So that bare `tether` resolves to the stable binary (not the editable one),
`.vscode/settings.json` disables the Python extension's terminal
auto-activation of `.venv` and prepends the stable venv's bin to the integrated
terminal's PATH:

```json
{
  "python.terminal.activateEnvironment": false,
  "terminal.integrated.env.linux": {
    "PATH": "${workspaceFolder}/.venv-tether-stable/bin:${env:PATH}"
  }
}
```

Dev tooling runs through `uv run` (which uses `.venv` regardless of
activation), and the editor's interpreter stays `.venv`, so in-editor
IntelliSense and go-to-definition still resolve to the working-tree source. The
committed allow rules already cover bare `tether <subcommand>`, so no extra
permission rule is needed for the stable path.

## Re-pinning

The pin is "last known-good," re-synced on purpose. Rebuild the stable binary
from current source and regenerate the integration artifacts whenever a change
affects what the hooks read or emit, or what `init` generates — the record
schema, the `hook claude-code` surface, the agent fragment (`fragment.py`), or
the onboard skill (`skill.py`):

```bash
uv pip install --python .venv-tether-stable/bin/python --reinstall . \
  && .venv-tether-stable/bin/tether init claude-code
```

The first step reinstalls tether non-editable into the stable venv from current
source; the second regenerates `.tether/tether.md` and the onboard `SKILL.md`,
re-adds the `CLAUDE.md` import, and re-merges permissions and hooks (all
idempotent). Relaunch the VSCode integrated terminal afterward so bare `tether`
picks up the rebuilt binary.

## Compatibility with project invariants

- **Vault boundary.** Tethers may reference `tether-vault/**` files — a record
  stores a path and a blob OID, and `tether add` / `refresh` write only under
  `.tether/`. Dogfooding never writes into the read-only vault.
- **Test isolation.** The `project` fixture builds isolated tmp-dir projects
  (`tests/conftest.py`), and `find_project_root` walks upward from cwd — from a
  tmp dir it never reaches the repo-root `.tether/`. The committed dogfood graph
  does not leak into the suite.
- **The graph is a second codebase.** Descriptions are unfingerprinted prose;
  nothing curates the graph except diligence. Favor precision over recall —
  `tether coverage` is a progress signal, not a target to maximize.
