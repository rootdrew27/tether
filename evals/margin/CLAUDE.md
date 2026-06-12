# CLAUDE.md — working on the margin evals

Operational notes for modifying or interpreting this harness. User-facing
overview is in `README.md`.

## The two agent definitions are forks of Margin's

Both are derived from Margin's repo-owned `claude-code` definition (cached at
`~/.margin/configs/agent-definitions/claude-code`):

- **`claude-code-tether/`** — changes from upstream: the `tether-setup` and
  gated `onboard` blocks in `hooks/run-prepare.js`, the optional `onboard`
  boolean in `schema.json`, and `name`/`description` in `definition.toml`.
  Everything else is verbatim.
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

### Onboard block (gated)

Agent configs whose `[input]` sets `onboard = true` (currently
`tether-onboard-sonnet`) get a second setup block after `tether init
claude-code`: a headless `claude -p "/tether-onboard"` run (same binary,
model, and effort as the main agent; fresh session) that seeds a tether
graph in the case workspace before the SWE task starts.

- Capped at 2400s via `timeout --kill-after=60`. **Fail-fast:** on timeout or
  nonzero exit the hook logs the record count and coverage for the
  post-mortem, emits the FAILED marker, and exits nonzero before the agent
  launches — an instance never runs the SWE task on a partial graph. Pair
  the arm with `eval-configs/onboard-smoke.toml`
  (`instance_timeout_seconds = 5400`) so the cap leaves the SWE task room.
- Markers use the `tether-onboard:` prefix (`begin`, `done`/`FAILED`, record
  count, coverage summary) — deliberately distinct from the `tether-setup:`
  strings the verifier *requires*. `verify-smoke.py` reports onboard markers
  only when present, so plain smoke runs are unaffected; keep marker text and
  verifier regexes in sync here too.
- The skill itself ships in the wheel (`tether init claude-code` writes
  `.claude/skills/tether-onboard/`), so the wheel ref must contain it.

### Pre-trust block — keep it

`claudeState.projects[run.cwd]` pre-accepts the trust dialog so project-level
`.claude/settings.local.json` hooks load headless. A scratch experiment showed
hooks fire without it in a *plain local* CLI, but that did not isolate the
margin context (isolated HOME, `bypassPermissions`). Removing it is unvalidated
risk — only drop it after a tether-arm smoke run confirms SessionStart still
fires.

## Pins live in ALL the agent configs — change them together

`tether-sonnet/`, `tether-onboard-sonnet/`, and `baseline-sonnet/` each pin
the model (`--model` arg *and* `settings_json`) and `claude_version`. Bump
all arms in lockstep or the A/B diverges on something other than tether.
Current pins: `claude-sonnet-4-6` / Claude Code `2.1.167`. The onboard pass
reuses `startup_args`, so it runs the same pinned model as the agent.

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
