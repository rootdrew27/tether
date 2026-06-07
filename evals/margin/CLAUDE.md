# CLAUDE.md — working on the margin evals

Operational notes for modifying or interpreting this harness. User-facing
overview is in `README.md`.

## The two agent definitions are forks of Margin's

Both are derived from Margin's repo-owned `claude-code` definition (cached at
`~/.margin/configs/agent-definitions/claude-code`):

- **`claude-code-tether/`** — the *only* change from upstream is the
  `tether-setup` block in `hooks/run-prepare.js` (plus `name`/`description` in
  `definition.toml`). Everything else is verbatim.
- **`claude-code-stock/`** — byte-identical to upstream except `name`/
  `description`. It exists so the control arm references committed state instead
  of machine-local `~/.margin`.

When Margin's definition changes (new CLI version, changed hook contract),
re-sync by re-copying from `~/.margin/...` and re-applying the local diffs
above. There is no automatic drift detection.

## tether install path (`claude-code-tether/hooks/run-prepare.js`)

The `tetherSetup` block runs before the agent launches:

- Wheel is bind-mounted `<repo>/dist` → `/opt/tether-dist` by `run-smoke.sh`
  (`--agent-bind`). The `wheelDir` constant in the hook must match that target.
- Installs into an **isolated uv venv at `/opt/tether-venv`** with `--python
  3.12` — never the testbed's own interpreter (swebench pythons predate 3.12;
  tether requires ≥3.12). `tether` is symlinked into `/usr/local/bin`.
- Runs `tether init` + `tether init claude-code` in `run.cwd`.
- All output goes to stderr as `tether-setup: …` markers, captured in each
  instance's `run/agent_server_pty.log`. **`verify-smoke.py` matches these exact
  strings** — keep the marker text and the verifier in sync.

### Pre-trust block — keep it

`claudeState.projects[run.cwd]` pre-accepts the trust dialog so project-level
`.claude/settings.local.json` hooks load headless. A scratch experiment showed
hooks fire without it in a *plain local* CLI, but that did not isolate the
margin context (isolated HOME, `bypassPermissions`). Removing it is unvalidated
risk — only drop it after a tether-arm smoke run confirms SessionStart still
fires.

## Pins live in BOTH configs — change them together

`tether-sonnet/config.toml` and `baseline-sonnet/config.toml` each pin the model
(`--model` arg *and* `settings_json`) and `claude_version`. Bump both arms in
lockstep or the A/B diverges on something other than tether. Current pins:
`claude-sonnet-4-6` / Claude Code `2.1.167`.

## Wheel build + recording (`scripts/run-smoke.sh`)

- Builds from `git archive <ref>` in a temp dir — never the working tree.
  Stamps the version `0.1.0+g<sha7>` by `sed` on the extracted `pyproject.toml`.
- The first non-flag arg is treated as a committish if it resolves; the rest
  pass through to `margin run`.
- Discovers the run dir by diffing `runs/` before/after (margin owns the
  `run_id` naming), then writes `<run-dir>/tether-build.json`
  (`ref`, `commit`, `branch`, `wheel`, `built_at`).

## verify-smoke.py mechanics

- Reads `run/agent_server_pty.log` per instance: checks the `tether-setup:`
  setup markers, extracts the stamped version and cross-checks it against
  `tether-build.json`, and counts `hook_response` stream-json events by event.
- **Hooks:** Claude Code 2.1.x emits stream-json hook events for **SessionStart
  only**. The Stop and PreToolUse hooks run but emit nothing when their output
  is empty — always the case on the tether-free swe-minimal repos (verified with
  marker-file hooks). So the verifier *requires* SessionStart and reports the
  others only if they appear (seeded graphs / future CLI versions).

## Gotchas

- `runs/` is gitignored. `--dry-run` leaves junk run dirs there — `rm -rf`
  freely.
- uv and the Python patch version are **not** pinned (tether arm only) — low
  impact, it's tether's runtime, not the agent's.
- The suite is not pinned in the command; margin records the resolved commit in
  `<run-dir>/internal/bundle.json`. `margin suite pull` refreshes the cache.
