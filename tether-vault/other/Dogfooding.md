This repo dogfoods **tether** — tethers track drift-sensitive relationships
inside tether's own source, and the Claude Code integration runs in development
sessions here. This note is the operational runbook; the full setup rationale
and mechanics live in `agent-notes/design/Dogfooding.md` (outside the vault).

## Two tether binaries

Two installs coexist and never overlap:

- **`.venv-tether-stable/bin/tether`** — a pinned, non-editable copy. Runs the
  Claude Code hooks *and* every manual `tether` command. Bare `tether` resolves
  here.
- **`.venv/bin/tether`** — the editable dev install. Only the dev/test loop
  uses it, always through `uv run` (e.g. `uv run pytest`). Never run it against
  the real graph.

The split prevents edits of tether's own source code from breaking the
hooks that instrument the very session doing the editing.

## Updating the stable tether version

The stable binary is a frozen snapshot — it does **not** pick up source edits
until re-pinned. Re-pin after any change that affects what the hooks read or
emit, or what `init` writes: the record schema, the `hook claude-code`
commands, the agent fragment, or the onboard skill.

```bash
uv pip install --python .venv-tether-stable/bin/python --reinstall . \
  && .venv-tether-stable/bin/tether init claude-code
```

The first line reinstalls tether (non-editable) into the stable venv from
current source. The second regenerates `.tether/tether.md` and the onboard
skill, re-adds the `@.tether/tether.md` import to `CLAUDE.md`, and re-merges
permissions and hooks — all idempotent.

> [!warning]+ Relaunch the terminal
> After re-pinning, relaunch the integrated terminal so bare `tether` resolves
> to the rebuilt binary.

## Bootstrapping on a fresh clone

`.venv-tether-stable/` and `.vscode/settings.json` are gitignored, so a fresh
clone has neither. To set up:

1. Create the stable venv and install tether into it (non-editable):

   ```bash
   uv venv .venv-tether-stable
   uv pip install --python .venv-tether-stable/bin/python .
   ```

2. Install the integration from the stable binary:

   ```bash
   .venv-tether-stable/bin/tether init claude-code
   ```

3. Make bare `tether` resolve to the stable binary by creating
   `.vscode/settings.json`:

   ```json
   {
     "python.terminal.activateEnvironment": false,
     "terminal.integrated.env.linux": {
       "PATH": "${workspaceFolder}/.venv-tether-stable/bin:${env:PATH}"
     }
   }
   ```

4. Relaunch the integrated terminal.

## Day-to-day

- Use bare `tether …` for all tether work (status, add, refresh, …) — it is the
  stable binary.
- Use `uv run …` for dev tooling (`uv run pytest`, `uv run ruff`,
  `uv run pyright`).
- Drift surfaces automatically: the Stop hook blocks a turn on drift, and
  tethered files inject their tether context on Read. See [[DICTION]] for the
  state vocabulary.
- Seed the graph with the onboard skill rather than by hand; `tether coverage`
  is a progress signal, not a target.

See also [[Playground]] for the sibling gitignored dev sandbox.
