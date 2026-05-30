This document specifies how tether integrates with Claude Code. The conceptual framing — query at action time, refresh as assertion, records mutable only through tether's commands — lives in [Tether-Design-MVP](../design/Tether-Design-MVP.md) under §"How tether enables coding agents." This doc covers the concrete mechanics: which hooks fire, what they output, how they install, and how failures are handled.

## Event matrix

The integration uses three Claude Code hook events:

| Event | Purpose |
|---|---|
| `SessionStart` | Inject tether status as context at the start of every session (including `resume`, `clear`, and `compact`). Orientation. |
| `PreToolUse` (matcher `"Read"`) | When the agent reads a tethered file, inject a `<tether-context>` block describing every tether involving that file (states, peer path, description). Decision-time steering. |
| `Stop` | Check tether status before the agent ends its turn. Block the turn (force continuation) if any tether is non-HEALTHY. |

`PreToolUse` on `Edit`/`Write`/`MultiEdit` is deliberately not part of the design. Edits are frequent (8-30 per turn in typical sessions); per-edit context injection is expensive and largely redundant with the PreRead-on-Read injection that already primed the agent with the tether description before it decided to edit. Stop coverage at turn end remains the safety net for drift the agent introduced. Other PreToolUse triggers (Bash-mediated reads, prompt `@file` mentions) are tracked in [Claude-Code-Integration-Open](Claude-Code-Integration-Open.md).

A separate, declarative `permissions.deny` rule covers `.tether/tethers/` — see §"Write-denial mechanism" below.

## SessionStart hook

**Trigger:** every session start, regardless of `source` (`startup | resume | clear | compact`). Same content for all four sources; re-injecting on resume and compact is cheap insurance against stale assumptions and compacted-out tether context.

**Output: adaptive density.**

- **No tethers in project:** exit 0 with no output. Silence is better than noise.
- **All HEALTHY:** one-line affirmative.

  ```
  tether: 12 tethers, all HEALTHY.
  ```

- **Mixed states:** markdown section listing items needing attention. Each item shows tether ID, severity, paths with per-side states, and description. No diffs in the SessionStart output — those are fetched on demand.

  ```markdown
  ## Tether status

  12 tethers tracked. Counts: 9 HEALTHY, 2 WEAKENED, 1 BROKEN.

  Needs attention:

  - `0192abc1-23ef-7890-abcd-ef0123456789`: BROKEN — `docs/auth.md` (HEALTHY) — `src/auth_old.py` (BROKEN)
    Description: Auth flow spec.

  - `0192def2-...`: WEAKENED — `docs/api.md` (DRIFTED) — `src/api.py` (HEALTHY)
    Description: REST endpoints; impl uses FastAPI.

  - `0192ghi3-...`: WEAKENED — `docs/billing.md` (HEALTHY) — `src/billing.py` (DRIFTED)
    Description: Stripe integration and webhook handling.

  For diffs: `tether status <uuid>`. To assert alignment after editing both sides: `tether refresh <uuid>`.
  ```

The output is markdown on stdout, which Claude Code injects as context. The agent reads it as prose. Markdown is preferred over JSON for agent-facing surfaces; JSON is available via `tether status --json` for scripts and CI.

## PreToolUse hook

**Trigger:** every Claude Code Read tool call. Matcher is `"Read"`; the hook subprocess is `tether hook claude-code pre-tool-use`. The same subcommand defensively short-circuits to silent exit 0 on any other `tool_name`, so misconfigured matchers degrade safely.

**Behavior:**

1. Parse `cwd`, `tool_name`, `tool_input.file_path` from stdin. Empty or invalid stdin → exit 2 (fail-loud per current policy).
2. Resolve `file_path` to a project-relative POSIX path. If outside the project root, or no project root is reachable from `cwd`, exit 0 silent.
3. Look up tethers whose `a.path` or `b.path` equals the resolved path (`storage.find_by_path`).
4. If no matches, exit 0 silent with no output.
5. Otherwise compute per-tether state and emit JSON to stdout:

   ```json
   {
     "hookSpecificOutput": {
       "hookEventName": "PreToolUse",
       "additionalContext": "<tether-context>…</tether-context>\n"
     }
   }
   ```

Claude Code routes `additionalContext` into the agent's context window alongside the eventual tool result for `PreToolUse` (per the Claude Code hooks reference). The agent sees the file content and the tether context together at decision time, before the next tool call.

**XML format.** One `<tether-context>` wrapper; one `<tether>` child per matching record, severity-ordered (BROKEN → DRIFTED → WEAKENED → HEALTHY, UUIDv7 ascending tiebreaker). Each `<tether>` carries `id` and `aggregate` attributes; `<self path … state…>` and `<peer path … state…>` self-closing children with per-side state (the queried file's state can differ across tethers because each tether records its own fingerprint); `<description>` element text carries the prose verbatim, XML-escaped. Sample:

```xml
<tether-context>
  <tether id="019e36df-a270-7653-84a1-6af594d8286a" aggregate="WEAKENED">
    <self path="src/cli.py" state="DRIFTED" />
    <peer path="docs/usage.md" state="HEALTHY" />
    <description>usage.md describes the CLI surface defined in cli.py …</description>
  </tether>
</tether-context>
```

**Partial-failure policy.** Unreadable tether records are skipped — `find_by_path` returns valid matches; the `<tether-context>` payload **does not** include an `<errors>` block at this surface. The same corrupt records are surfaced at SessionStart and inside `tether status` / `tether refs` for the project-wide and per-file diagnostic surfaces respectively. PreRead intentionally stays narrow: "this file you're about to interact with has these tethers" — corruption notices unrelated to the queried file would be noise repeated per Read.

**Why `additionalContext` and not stdout text.** Claude Code's hooks reference is explicit: stdout-to-context routing applies only to `SessionStart`, `UserPromptSubmit`, and `UserPromptExpansion`. PreToolUse stdout goes to the debug log unless wrapped in the JSON shape above. The 10,000-char cap on `additionalContext` is well above the size of any plausible tether's worth of XML.

**Origin.** Empirically motivated by case-study-01, where the same agent on the same task succeeded by reading the tether description before editing (run 2) and only narrowly recovered by post-hoc reasoning when it didn't (run 1). The PreRead injection makes the success path the default — the description is delivered with the file content, every time.

## Stop hook

**Trigger:** every time the agent is about to end a turn.

**Block condition (v1, stateless):** any tether currently non-HEALTHY (WEAKENED / DRIFTED / BROKEN) blocks turn end. Pre-existing drift triggers blocking, just as new drift does. This is deliberately stateless for v1; a session-baseline-stateful variant (block only on tethers that became non-HEALTHY during this session) is a planned refinement — see [Claude-Code-Integration-Open](Claude-Code-Integration-Open.md).

**Reason format:** markdown list of non-HEALTHY tethers, ordered by severity (BROKEN → DRIFTED → WEAKENED) with UUIDv7 ascending as tiebreaker. Each entry shows the tether ID (backtick-wrapped, full UUID for copy-paste), aggregate state, paths with per-side states inline, and description on a continuation line. No diffs — those are fetched on demand. No per-state action hints — those live in the persistent CLAUDE.md fragment. Sample:

```
## Stop blocked: tethers need attention

- `0192abc1-23ef-7890-abcd-ef0123456789`: BROKEN — `docs/old.md` (HEALTHY) — `src/legacy.py` (BROKEN)
  Description: Spec for the legacy auth path; src/legacy.py may have been renamed.

- `0192def2-...`: WEAKENED — `docs/auth.md` (DRIFTED) — `src/auth.py` (HEALTHY)
  Description: Covers password reset and 2FA enrollment; impl uses argon2.

- `0192ghi3-...`: DRIFTED — `docs/api.md` (DRIFTED) — `src/api.py` (DRIFTED)
  Description: Public REST surface; impl handles auth and rate-limiting middleware.

For each entry above, either:
- resolve and `tether refresh <uuid>` once both artifacts reflect the intended state, OR
- if the resolution is a judgment call, surface the choice to the user with the options as you see them and end the turn awaiting direction.

Do not refresh until alignment is real — refresh erases the drift signal. For renames, use `tether update --a-path/--b-path <new>` before refresh.
```

A tether is symmetric, so paths are separated by an em dash with no directional arrow. Descriptions are always present (required at `tether add` time, validated on read). UUIDs are shown in full (not truncated) so the agent can copy-paste them as command arguments. No truncation of the list for MVP, regardless of count.

The "surface to user as a first-class resolution" path is deliberate: it preserves the agent's ability to defer a judgment call to the user rather than forcing a unilateral fix. When the resolution is mechanical (align two files that should match), the agent resolves and refreshes; when the resolution involves intent the agent shouldn't infer (a description that may or may not still apply, an edit that may or may not be a regression), the agent surfaces options and ends the turn. The Stop hook re-fires on the next turn end if drift remains, so deferring is safe.

**User-visible surface.** Claude Code displays the block `reason` to the user verbatim, prefixed with `Stop hook error:`. The same text is fed back into the agent's context, and the agent generates a continuation turn that acts on the instruction without requiring the user to re-prompt. Tether's `reason` is written for the agent as the primary audience; users see it as a side effect. The `Stop hook error:` prefix is Claude-Code-imposed and not configurable, so the reason text should read coherently underneath it (e.g. don't open with phrasing that contradicts the "error" framing).

**Diff format when surfaced:** when the agent fetches a diff via `tether status <uuid>`, the diff uses git-native unified diff format inside a markdown fenced code block. Models are well-tuned to this representation.

**Loop prevention:** v1 has none. The integration trusts the agent to resolve and end; if loops occur in practice, a "max N consecutive blocks per session" guard will be added. Tracked in `Claude-Code-Integration-Open.md`.

## CLAUDE.md fragment

The fragment lives at `.tether/tether.md`, fully tether-owned, imported into the project's `./CLAUDE.md` via the line:

```
@.tether/tether.md
```

It lives under `.tether/` rather than `.claude/` because it is tether's content, written and overwritten by tether, and is the kind of artifact that benefits from being committed alongside the tether records it describes. `.claude/` is reserved for Claude-Code-owned settings.

**Source of truth: `tether/claude_code/fragment.py`** (`FRAGMENT` constant). That file is what `tether init claude-code` writes to `.tether/tether.md` on every run; embedding the markdown here would drift the moment either side is edited. The contract the fragment must satisfy:

- Introduce tether (what it is, what a tether records, what drift means).
- State that tethers are symmetric (no direction, no type) and that `--description` is required at `tether add` time.
- State that `.tether/` is tether-owned and read-only to the agent; mutations go through the CLI.
- Define the per-artifact (`HEALTHY` / `DRIFTED` / `BROKEN`) and aggregate (`HEALTHY` / `WEAKENED` / `DRIFTED` / `BROKEN`) states.
- Describe resolution paths for each non-HEALTHY aggregate, including the "surface to user" option for judgment calls and the two-step `update` → `refresh` for `BROKEN`.
- Set expectations around `tether status` (diagnostic, not verification) and `tether refresh` (assertion, not auto-action).
- List the key commands with their signatures.

**Note on scope:** this fragment is Claude-Code-specific. Other harnesses (Cursor, Aider, Codex) will get their own per-harness fragments with appropriate vocabulary when those integrations ship.

**Note on sub-file locators:** the fragment is whole-file-only — MVP ships only the `WholeFile` locator. When the CLI grows `LineRange` (and beyond) locator support, the fragment's intro and example commands update to introduce sub-file relationships. Tracked in [Future-Work](../design/Future-Work.md); the fragment update itself is tracked as a blocked item in [Claude-Code-Integration-Open](Claude-Code-Integration-Open.md).

## Write-denial mechanism

Declarative `permissions.deny` entries in `.claude/settings.json` block mutating tool calls anywhere under `.tether/`:

```json
{
  "permissions": {
    "deny": [
      "Edit(.tether/**)",
      "Write(.tether/**)",
      "MultiEdit(.tether/**)",
      "NotebookEdit(.tether/**)"
    ]
  }
}
```

Three scoping decisions:

- **Scope is the whole `.tether/` directory.** Tether records (`.tether/tethers/<uuid>.json`), the agent-facing fragment (`.tether/tether.md`), and any future derived state (snapshot files, journals, config) all live under `.tether/` and are tether-owned. A single broad deny is simpler than enumerating subpaths, and naturally extends to anything tether writes in the future without needing a permissions update.
- **Read is allowed.** The agent may read anything under `.tether/` to inspect state — records, the fragment, config. Denial targets mutation, not inspection.
- **Bash is not covered.** Claude Code's permission matchers on Bash are command-prefix-based, not path-based; an agent running `sed -i .tether/tethers/<uuid>.json` would bypass the deny. This is accepted as an open gap — the CLAUDE.md fragment instructs the agent to use the CLI, and tether's read-side validation catches any corruption introduced through this path.
- **Why declarative and not a PreToolUse hook?** The rule is static. Declarative deny is enforced by Claude Code's permission engine without spawning tether on every Edit/Write — zero cost, zero hook process. A programmatic hook would be appropriate only if the rule needed runtime state, which it doesn't.

## Allow-list for tether CLI commands

Declarative `permissions.allow` entries in `.claude/settings.json` pre-approve the tether subcommands the agent will routinely invoke — read-only inspection (`status`, `refs`, `show`) and the non-destructive mutations used to clear a Stop block (`refresh`, `update`, `add`, `mv`) — so the user is not prompted on every refresh:

```json
{
  "permissions": {
    "allow": [
      "Bash(tether status:*)",
      "Bash(uv run tether status:*)",
      "Bash(poetry run tether status:*)",
      "Bash(conda run -n * tether status:*)",
      "Bash(.venv/bin/tether status:*)",
      "Bash(${CLAUDE_PROJECT_DIR}/.venv/bin/tether status:*)",
      "...the same six invocation forms for refresh/update/add/mv/refs/show..."
    ]
  }
}
```

**Enumerated-prefix rationale.** Six invocation forms are pre-approved per subcommand; across the seven subcommands (`status`, `refresh`, `update`, `add`, `mv`, `refs`, `show`) that is forty-two total patterns:

1. `tether` — bare, when `tether` is on PATH (pipx, system install, active venv).
2. `uv run tether` — uv-managed projects.
3. `poetry run tether` — poetry-managed projects.
4. `conda run -n * tether` — conda environments. The wildcard captures the env name (`-n myenv`).
5. `.venv/bin/tether` — direct invocation of the local venv binary.
6. `${CLAUDE_PROJECT_DIR}/.venv/bin/tether` — the same form anchored to the Claude Code project directory variable; matches the path our own SessionStart/Stop hooks use, so the agent imitating the hook command works without a prompt.

Enumerating rather than relying on a single leading-wildcard pattern (e.g. `Bash(*tether <sub>:*)`) keeps the patterns within the well-tested prefix shape (literal prefix + `:*` trailing wildcard) documented as reliable in the Claude Code [permissions reference](https://code.claude.com/docs/en/permissions). Leading-wildcard forms are documented as supported but empirically fail to match commands like `uv run tether status`, so tether avoids them.

Exotic invocation forms (`hatch run tether`, `pdm run tether`, absolute paths outside `.venv`) are not pre-approved and will prompt the user on first invocation; the user can hand-add a pattern if they want. The fragment at `.tether/tether.md` lists the pre-approved forms so the agent gravitates toward one it knows will not prompt.

`tether rm` is **deliberately not pre-approved.** Removing a tether is the assertion that a relationship no longer applies, which is a judgement call worth surfacing to the user — the Bash permission prompt on `tether rm` is the speed bump that prevents an agent from "resolving" drift by silently deleting the record. `tether init` and `tether init claude-code` are setup commands the agent has no business running mid-session and are likewise omitted.

These entries merge alongside any user-authored allow entries; the signature predicate is described under §"`tether init claude-code`".

## Hook subcommand implementation

Tether exposes three Claude-Code-specific subcommands, all hidden from the default `tether --help` output:

- `tether hook claude-code session-start` — reads hook input JSON on stdin, runs `api.status()`, formats per the SessionStart adaptive schema, emits to stdout.
- `tether hook claude-code stop` — reads hook input JSON on stdin, runs `api.status()`, emits `{"decision": "block", "reason": "..."}` if any tether is non-HEALTHY, exits 0 with no output otherwise.
- `tether hook claude-code pre-tool-use` — reads PreToolUse hook input JSON on stdin (`tool_name`, `tool_input.file_path`), short-circuits to silent exit 0 on non-Read tools or files outside the project, looks up matching tethers via `storage.find_by_path`, and emits `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "<tether-context>…</tether-context>"}}` when at least one tether matches.

**CLI placement:**

```
tether
├── init
│   └── claude-code     # tether init claude-code — installs the integration
├── ...other user-facing commands...
└── hook                # hidden group
    └── claude-code     # hidden subgroup
        ├── session-start   # called from .claude/settings.local.json
        ├── stop            # called from .claude/settings.local.json
        └── pre-tool-use    # called from .claude/settings.local.json
```

The `hook` group is hidden because hook subcommands are integration-specific, not user-facing. They're invocable for debugging via `tether hook --help`, but they don't clutter the default surface a developer or agent sees when discovering tether's CLI.

**Where hooks live: `.claude/settings.local.json`, not `.claude/settings.json`.** Hook commands embed the detected absolute or `${CLAUDE_PROJECT_DIR}`-anchored path to the tether binary on the installing machine, which is not portable across machines or users. Committing those paths into the team-shared `settings.json` would break every other developer's clone. Claude Code provides `.claude/settings.local.json` as the per-user-per-project override layer (gitignored by convention), which is exactly the right home: hooks are project-scoped (they only fire in this project) but machine-specific (each user runs `tether init claude-code` once after cloning to generate their own copy). The committed `.claude/settings.json` carries only the portable bits — the permission denies and allows that depend on `.tether/tethers/` and the tether CLI, both of which are the same on every machine.

Claude Code resolves each settings key independently from its layered files: hooks in `settings.local.json` and permissions in `settings.json` *both* apply in the same session, because permission rules merge across scopes and a key only "wins" when it appears in multiple scopes (which it does not for hooks here, since `settings.json` carries none). Documented under "Settings precedence" at <https://code.claude.com/docs/en/settings>.

**Settings.local.json hook configuration** (written by `tether init claude-code`):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PROJECT_DIR}/.venv/bin/tether hook claude-code session-start",
            "timeout": 10
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PROJECT_DIR}/.venv/bin/tether hook claude-code stop",
            "timeout": 10
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Read",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PROJECT_DIR}/.venv/bin/tether hook claude-code pre-tool-use",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

The `${CLAUDE_PROJECT_DIR}/.venv/bin/tether` form shown above is what gets written when tether is installed as a project-local Python dependency (the recommended pattern). For a global install (pipx, system pip), the command is the absolute path to the binary (e.g. `/home/<user>/.local/pipx/venvs/tether/bin/tether`) — see §"Binary path detection" below. The 10s timeout is a ceiling; tether's hook commands should complete well under 1s p50 on typical projects.

**Binary path detection.** At `tether init claude-code` time, the installer resolves the tether binary path as follows:

1. Prefer `Path(sys.executable).parent / "tether"` — the binary adjacent to the currently-running Python interpreter. This is the binary that's actually being used to run `tether init`, so resolving it from its own `sys.executable` is the most honest signal.
2. Fall back to `shutil.which("tether")` if no adjacent binary is found.
3. If neither resolves, error out with an actionable message ("Install tether before running init").
4. If the resolved path lives inside the project root, write it as `${CLAUDE_PROJECT_DIR}/<relpath>` so the hook is portable across project moves on the same machine. Otherwise write the absolute path.

`${CLAUDE_PROJECT_DIR}` is Claude Code's standard substitution token for the project root at hook-fire time; using it instead of a bare relative path closes the launch-cwd footgun for the in-project case.

**Matcher syntax gotcha.** Claude Code's hook matchers accept only letters, digits, `_`, and `\|`. A plain `|` is not in the allowed character set — `"matcher": "startup|clear"` is treated as a literal exact-match string and never fires. To match multiple sources, either use the escaped form (`"matcher": "startup\\|clear"` in JSON, which yields the literal `startup\|clear`) or list each source as its own entry. Tether's own config uses `"matcher": "*"` and so is unaffected; this note exists for anyone customizing the integration or debugging adjacent hooks. Verified against Claude Code docs as of 2026-05-14 (v2.1.141).

**Shell-interpreter gotcha.** Claude Code executes hook commands via `/bin/sh`, which on Debian/Ubuntu is `dash` — not bash. Bash-only constructs silently break the hook: `set -o pipefail` fails with `Illegal option -o pipefail`, and the hook is logged at debug level only (no user-visible error, no context injected). The same trap applies to `[[ ... ]]`, `<( ... )` process substitution, arrays, and `${var^^}`-style parameter expansion. If a hook needs any of these, wrap the body in `bash -c '...'` (escape inner single quotes as `'\''`); otherwise stick to POSIX sh. Tether's own hook invocations are single commands (`tether hook claude-code session-start`) and so are unaffected; this note exists for anyone writing adjacent hooks alongside tether's.

**Project-root discovery gotcha.** Claude Code loads project-level settings — `.claude/settings.json` and `.claude/settings.local.json` alike, and therefore every key inside them including `hooks` and `permissions` — **only from the launch cwd's `.claude/` folder. There is no parent-directory walk-up.** Launching `claude` from a subdirectory of the tether project (e.g. `playground/tests/` rather than `playground/`) means the SessionStart and Stop hooks never fire, because Claude Code looks for `<cwd>/.claude/settings*.json`, finds nothing, and falls back only to user-level (`~/.claude/`) and managed settings — not to a parent project. The asymmetric exception is subagents, commands, and output styles, which *are* discovered by walking up from cwd. Hooks and `settings.json` keys are not.

Operational consequence: users must launch Claude Code from the directory containing `.tether/` and `.claude/`. To work in a subdirectory afterward, the right pattern is to launch from the project root with `claude --add-dir <subdir>` (or use `/add-dir` mid-session) — `--add-dir` extends file access without changing project discovery, so the parent's `.claude/settings.json` and `.claude/settings.local.json` still drive hooks. There is no CLI flag to override project-root discovery; the docs explicitly recommend "Launch Claude Code from the directory containing the `.claude/` configuration you want."

Documented under "Additional directories grant file access, not configuration" at <https://code.claude.com/docs/en/permissions>; verified empirically on 2026-05-14. Worth surfacing to users at install time (a final-line tip from `tether init claude-code`) and in the `.tether/tether.md` fragment, but those touchpoints are not yet implemented — tracked in [Claude-Code-Integration-Open](Claude-Code-Integration-Open.md) under launch-cwd UX.

## `tether init claude-code`

A single all-in-one subcommand that sets up the integration. Idempotent — re-running updates tether-owned content without disturbing the rest.

**Files touched:**

| File | Action |
|---|---|
| `.tether/` | Project init (skipped if already initialized) |
| `.tether/tether.md` | Fully tether-owned; overwritten on every run |
| `./CLAUDE.md` | `@.tether/tether.md` import appended once if not present; otherwise untouched; created with just the import line if file doesn't exist |
| `.claude/settings.json` | Tether-owned **permissions** merged in via signature-matched replacement (see below); everything else preserved. Committed to git; portable across machines. |
| `.claude/settings.local.json` | Tether-owned **hooks** merged in via signature-matched replacement, with the machine-specific tether binary path embedded. Gitignored; per-user-per-project. |
| `.gitignore` | `.claude/settings.local.json` entry appended once if not present; otherwise untouched; created with the entry if no `.gitignore` exists. Ensures the local-settings file doesn't get committed by accident. |

**Why two settings files.** Hooks carry machine-specific binary paths and cannot be portably committed; permissions don't and can. Splitting them along the boundary that matches their portability lets the team share a single `settings.json` while each developer's `settings.local.json` reflects their own install layout. See §"Where hooks live" above for the resolution semantics.

**Settings merge rules.** Re-running init must update tether's entries without clobbering anything the user wrote. The signature predicates:

- For `hooks.SessionStart` and `hooks.Stop` (in `settings.local.json`): an entry is tether-owned if any of its `hooks[*].command` strings contains the substring `hook claude-code`. This deliberately matches regardless of the binary path prefix (so it catches both `${CLAUDE_PROJECT_DIR}/.venv/bin/tether hook claude-code ...` and `/abs/path/tether hook claude-code ...` and any legacy variants). On re-init, remove every tether-owned entry, then append the current-version entries with the freshly-detected command prefix.
- For `permissions.deny` (in `settings.json`): an entry is tether-owned if its path glob references `.tether/`. This deliberately matches both the current `.tether/**` form and any narrower legacy forms (e.g. `.tether/tethers/**`) so re-install cleans up stale entries from earlier versions. Same replace-and-append logic.
- For `permissions.allow` (in `settings.json`): an entry is tether-owned if it appears in the enumerated `ALLOW_PATTERNS` set (six invocation prefixes × five subcommands) or if it matches the shape `Bash(*tether <subcmd>:*)` for one of the pre-approved subcommands. See §"Allow-list for tether CLI commands" for the invocation list. Same replace-and-append logic.

User-authored entries (custom hooks, custom deny rules, custom allow rules, or anything in either file outside the predicates above) are never touched.

**Sample output (first run):**

```
$ tether init claude-code
Initialized tether project at /home/user/project/.tether
Wrote .tether/tether.md
Created CLAUDE.md with `@.tether/tether.md`
Updated .claude/settings.json:
  - added 4 deny rule(s)
  - added 42 allow rule(s)
Updated .claude/settings.local.json:
  - added SessionStart hook
  - added Stop hook
  - hook command resolved to `${CLAUDE_PROJECT_DIR}/.venv/bin/tether`
Created .gitignore with `.claude/settings.local.json`
```

**Sample output (re-run, all current):**

```
$ tether init claude-code
Initialized tether project at /home/user/project/.tether
Wrote .tether/tether.md
CLAUDE.md already imports `@.tether/tether.md`
Updated .claude/settings.json:
  - added 4 deny rule(s)
  - added 42 allow rule(s)
Updated .claude/settings.local.json:
  - added SessionStart hook
  - added Stop hook
  - hook command resolved to `${CLAUDE_PROJECT_DIR}/.venv/bin/tether`
```

Re-runs emit the same change lines because merge is signature-matched and replaces tether-owned entries unconditionally; the written file content is byte-stable across runs (verified by `test_install_idempotent`), but the report doesn't distinguish "added because absent" from "added because replacing identical entry" in v1. A future polish could compare pre- and post-merge state and emit "unchanged" when no real change occurred.

## Output formats

Tether's agent-facing CLI output is **markdown by default**; JSON is opt-in behind `--json` for programmatic consumers. (`tether show` is the exception — a plain-text, paged catalog for browsing the whole graph; it is agent-callable but stands outside the markdown/JSON contract.) The two surfaces, by audience:

| Surface | Default format | When |
|---|---|---|
| `tether status` (no args, no `--json`) | Markdown | Agent runs it; human at a terminal. |
| `tether status <uuid>` | Markdown (with fenced diff blocks for drifted sides) | Agent fetches details on one tether. |
| `tether status --json` / `tether status --json <uuid>` | JSON | Scripts, CI, future automation. |
| Hook subcommands (`tether hook claude-code session-start` / `stop`) | Markdown to stdout (SessionStart); markdown reason inside `{"decision": "block", "reason": "..."}` (Stop) | Claude Code's hook engine consumes. |

Markdown is the default because Claude reads it natively at lower token cost than JSON; the SessionStart and Stop reason formats specified above are markdown. The `--json` form's schema is documented separately (see `tether status --json` in the CLI surface) and is the contract for non-agent consumers.

## Hook input contract

Both hook subcommands read Claude Code's hook event JSON from stdin. Tether uses exactly one field:

- `cwd` — used to anchor the project-root walk (walk upward from `cwd` looking for `.tether/`).

Every other field (`session_id`, `hook_event_name`, `transcript_path`, etc.) is consumed and ignored. This minimizes coupling: if Claude Code's hook input schema evolves around other fields, tether is unaffected. `session_id` will be needed when the stateful-Stop variant ships — at that point it gets added to the contract.

Sketch:

```python
def hook_main():
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw else {}
    cwd = payload.get("cwd") or os.getcwd()
    root = walk_upward_for_tether_dir(Path(cwd))
    # ... call api.status(root=root), format, emit ...
```

If `cwd` is missing or no `.tether/` is found in the walk, the hook exits 2 with stderr — the integration is misconfigured (see §"Failure contract").

## Partial-failure handling

A single corrupt tether file (bad merge resolution, hand-edit that escaped `permissions.deny` via Bash, future schema version the current binary doesn't recognize) is not a hook-subcommand failure — it's a data-state issue that the hook discovers. Treating it as a hard failure would let a single broken record block every Stop until manual repair, which is a denial-of-service trap.

**Policy: skip and report.** Unreadable tether files are skipped; the rest of the project's tethers load and report normally. Both SessionStart and `tether status` append a notice section listing the affected files:

```
12 tethers tracked, 1 unreadable. Counts: 9 HEALTHY, 2 WEAKENED.

[... normal "needs attention" section ...]

Unreadable tether files (skipped):
- `.tether/tethers/0192xyz-....json`: invalid JSON at line 4
```

Hook subcommands still exit 0 on partial corruption — the *hook* succeeded; the *data* is partially broken, and the report says so. This is the fail-loud principle applied at the right granularity (loud about the corruption itself, not loud about the hook).

## Failure contract

**Current policy (early development, sole user): fail-loud.** Hook subcommands that error exit 2 with stderr describing the failure. Claude Code surfaces stderr to both the user and the agent, and treats exit 2 as a blocking error. Loud failures during this phase ensure that any integration breakage is caught immediately rather than silently degrading the safety mechanism.

**Future policy (before any wider release): fail-open-but-visible.** Move to exit 1 on error — Claude Code shows a non-blocking notice; session/turn proceeds. The user knows tether had a problem; the agent isn't impeded. This switch is a one-line change in each hook subcommand and a documentation update. Tracked in `Claude-Code-Integration-Open.md`.

The Stop hook must *never* return `{"decision": "block", "reason": ...}` from an error path under any policy. Blocking is reserved exclusively for "status query succeeded and the project legitimately has non-HEALTHY tethers."

**Performance budget.** Hook subcommands should complete in <500ms p50 on a project with a few hundred tethers. The 10s timeout in settings.json is the failure ceiling, not the expected runtime.
