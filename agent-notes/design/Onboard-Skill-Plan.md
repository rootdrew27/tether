# Onboard Skill — Implementation Plan

Implementation plan for the **`/tether-onboard` Claude Code skill** and its supporting CLI command, **`tether coverage`**. Background and mechanics research lives in [Onboard-Skill-Research](../research/Onboard-Skill-Research.md); this doc is the build plan. Decisions already made with the user: the feature is named **onboard**, is distinct from the deferred *reconcile* feature, runs largely autonomously once invoked, groups files by directory structure, uses heuristics with the model as final judge, and gets quantitative progress signal from `tether coverage`.

## Summary of what gets built

| Piece | Where | What |
|---|---|---|
| `tether coverage` | `tether/git.py`, `tether/coverage.py` (new), `tether/render.py`, `tether/output.py`, `tether/cli.py` | Structural-only command reporting what fraction of git-tracked files participate in a tether, and (on request) the untethered list. |
| Allow-list extension | `tether/claude_code/settings.py` | `coverage` joins `ALLOW_SUBCOMMANDS` so the skill runs prompt-free. |
| Skill content | `tether/claude_code/skill.py` (new) | The `SKILL.md` body as a module constant, `fragment.py`-style. |
| Skill install | `tether/claude_code/install.py` | `tether init claude-code` writes `.claude/skills/tether-onboard/SKILL.md`, overwritten on every run. |
| Fragment update | `tether/claude_code/fragment.py` | `coverage` added to the command list the agent sees. |
| Tests | `tests/test_coverage.py` (new), `tests/test_claude_code.py`, `tests/test_cli.py` | See test plan. |
| Doc sync | `agent-notes/claude-code/Claude-Code-Integration.md`, `agent-notes/design/future/DICTION-Future.md`; proposed diff for vault `DICTION.md` | See doc-sync section. |

Phases are ordered so each lands independently testable: coverage first (standalone CLI work), then the skill + installer, then doc sync, then validation.

---

## Phase 1 — `tether coverage`

### Semantics

- **Denominator:** files reported by `git ls-files` from the project root — tracked files only, `.gitignore` respected, untracked files excluded — **minus everything under `.tether/`**. The state directory is committed but is tether-owned infrastructure, not project content; counting records in the denominator would deflate coverage on exactly the projects using tether most. No other path policy is encoded (no skipping of lockfiles, vendored dirs, etc.) — judging what *deserves* a tether is the model's job, not the CLI's.
- **Numerator:** the set of `a.path` / `b.path` values across all readable tether records, intersected with the denominator. Structural-only — no drift computation, no fingerprint checks, no git object reads. A path referenced by a BROKEN tether still counts as tethered (coverage answers "is it tethered?", not "is it healthy?"); a recorded path that is not a tracked file simply doesn't intersect.
- **Partial failure:** unreadable records are skipped and reported, matching the `load_all_tethers` policy everywhere else.

### Implementation

1. **`tether/git.py`** — add `ls_files(root: Path) -> list[str]`: `git ls-files -z` via the existing `run_git_or_raise`, with `core.quotePath=false` for non-ASCII paths, split on NUL. Returns project-relative POSIX paths (git's native output form).
2. **`tether/coverage.py`** (new) — the computation: take `ls_files` output and `load_all_tethers`, return a small frozen struct (tracked count, tethered count, untethered list sorted, errors). Pure set arithmetic; trivially unit-testable without the CLI.
3. **`tether/output.py`** — `CoverageReport` msgspec struct for `--json`: `{"tracked": n, "tethered_count": n, "untethered_count": n, "percent": p, "tethered_files": [...], "untethered_files": [...], "errors": [...]}`. The two file arrays are populated only when the corresponding list flag is passed (empty otherwise) to keep the default payload small on large repos.
4. **`tether/render.py`** — `coverage_md(...)`: default human/agent surface. Summary form:

   ```
   ## Tether coverage

   34 of 120 tracked files tethered (28%). 86 untethered.

   For file lists: `tether coverage --list-untethered-files` / `--list-tethered-files`
   ```

   The two list flags **compose**: each appends its sorted file list under its own `### Untethered files` / `### Tethered files` heading, so passing both yields both sections, clearly delimited. Markdown default with `--json` opt-in follows the `tether status` precedent (agent-facing surfaces default to markdown; JSON for scripts) — coverage's primary consumer is the onboarding agent reading it as a progress signal. `--list-tethered-files` exists because the flat tethered list isn't cleanly derivable elsewhere (`tether show` is a heavyweight, description-bearing catalog) and gives a resuming onboard run a cheap "already covered" check.
5. **`tether/cli.py`** — `@main.command() coverage` with `--list-untethered-files`, `--list-tethered-files`, and `--json` flags, using `_root()` + `handle_errors` like its siblings.
6. **`tether/claude_code/settings.py`** — append `"coverage"` to `ALLOW_SUBCOMMANDS` (allow-list grows 42 → 48 patterns; the merge logic needs no change — `_ALLOW_PATTERN_SET` derives from the list).
7. **`tether/claude_code/fragment.py`** — add `tether coverage` to the fragment's command list so the agent knows it exists outside the skill.

### Why not in `status` or `show`

Coverage computes a derived metric over a set (git-tracked files) that no other command consults; `status` is per-tether drift and `show` is the record catalog. Folding it in would couple the structural-only command family to `git ls-files` semantics. Decided with the user: separate command.

---

## Phase 2 — Skill content and install

### Module: `tether/claude_code/skill.py`

`ONBOARD_SKILL` constant holding the full `SKILL.md` content, mirroring how `fragment.py` holds `FRAGMENT`. Same rationale: the installed artifact is generated from one source of truth in the package; docs reference the module rather than duplicating the markdown.

### Frontmatter (proposed)

```yaml
---
name: tether-onboard
description: Survey this project and create an initial tether graph — tethers
  with quality descriptions for every relationship whose drift would matter.
  For projects newly initialized with tether.
disable-model-invocation: true
---
```

- **`disable-model-invocation: true`** — onboarding is heavyweight and deliberate; only an explicit `/tether-onboard` triggers it. Zero context cost until invoked. (Per research; flagged as a decision below.)
- **No `context: fork`** — the skill must run in the main conversation so the agent keeps the ability to dispatch per-subsystem subagents (subagent nesting is capped at one level; a forked skill cannot fan out).
- **No `allowed-tools`** — the committed `.claude/settings.json` written by the same installer already pre-approves every tether subcommand in all six invocation forms; duplicating a partial list in frontmatter adds a second place to maintain.
- **No `model`/`effort` override in v1** — the session model judges. Revisit if playground validation shows weak descriptions.

### No load-time dynamic injection in v1

The research doc proposed seeding the skill with `` !`tether coverage` `` at load time. Implementation reality: `SKILL.md` is **committed and team-shared**, so it cannot embed the machine-specific tether binary path — the exact reason hooks live in gitignored `settings.local.json`. A bare `tether` in the injected command would fail on any machine where the binary isn't on the shell's PATH (project-local venv installs), and there is no `${CLAUDE_PROJECT_DIR}` substitution documented for skill injection commands. Rather than ship an injection that silently fails on the most common install layout, v1 makes **running `tether coverage` the model's first instructed action** — the Bash call goes through the allow-list, which already handles all six invocation forms. This also subsumes the `disableSkillShellExecution` degradation concern: there is nothing to degrade.

### Skill body (structure, not final prose)

Target well under 500 lines. Sections:

1. **Goal & framing.** Create tethers for every relationship whose drift would matter, each with a description that captures *why* the relationship exists — the description is the deliverable. Precision over recall: a tether whose drift wouldn't matter is noise that erodes trust in the Stop hook. The skill never runs `tether refresh` or `tether rm` (nothing exists to refresh; rm isn't allow-listed) — onboarding only surveys and `add`s, and every tether it creates is HEALTHY by construction.
2. **Step 0 — orient.** Run `tether coverage --list-untethered-files --list-tethered-files` (resumability: a second run must not duplicate existing tethers — the tethered list shows what's already covered, and `tether refs <path>` gives the detail before adding when a candidate file is already tethered).
3. **Step 1 — survey (fan-out).** Group tracked files by top-level directory subtree. For each subsystem, dispatch one subagent (read-only exploration) with a fixed prompt template: the subtree's file list, the candidate-pattern heuristics (doc↔code, test↔impl, schema↔consumer, config↔reader, duplicated constants, cross-language mirrors), and a required structured return — candidate pairs, draft description, confidence, one-line evidence. Subagents return candidate lists, never file dumps. Small projects (below a file-count threshold the skill states) skip fan-out and survey inline.
4. **Step 2 — judge.** The main agent reviews candidates across subsystems (cross-subsystem pairs surface here), drops low-confidence or drift-insensitive pairs, and finalizes each description against a stated quality bar: name both artifacts' roles, state what must stay aligned, concrete enough that a future agent reading it knows what to check. The fragment's calculator example is the model description.
5. **Step 3 — create.** One `tether add a b --description "..."` per accepted pair.
6. **Step 4 — measure & iterate.** Re-run `tether coverage --list-untethered-files`; sweep the remainder for missed candidates. Coverage is a progress signal, not a target — stop when the remaining untethered files genuinely have no drift-sensitive partner.
7. **Step 5 — report.** Final summary to the user: tethers created (paths + descriptions), coverage before → after, and the deliberately-untethered files with one-line reasons, so the user can scan for misses.

### Installer changes (`tether/claude_code/install.py`)

- New constants: `SKILLS_DIR = ".claude/skills"`, `ONBOARD_SKILL_DIR = "tether-onboard"`, `SKILL_NAME = "SKILL.md"`.
- In `install()`: `mkdir -p .claude/skills/tether-onboard/`, write `ONBOARD_SKILL`, report line `Wrote .claude/skills/tether-onboard/SKILL.md`. Unconditional overwrite on every run — same tether-owned-content rule as `.tether/tether.md`. No merge logic needed (the whole file is ours); no gitignore entry (the skill is meant to be committed).

---

## Phase 3 — Tests

- **`tests/test_coverage.py`** (new), using the `project` fixture:
  - empty project → 0/N, no crash; project with no tracked files → 0/0 (percent renders as `—` or `0%`, not a ZeroDivisionError);
  - tethered files counted once even when in multiple tethers; both `a` and `b` sides counted;
  - `.tether/**` excluded from the denominator;
  - tether path that isn't a tracked file (BROKEN/untracked) doesn't inflate the numerator;
  - unreadable record skipped and reported, command still exits 0;
  - `--list-untethered-files` and `--list-tethered-files` each list sorted paths under their own heading, compose when passed together, and populate the matching `--json` arrays; `--json` shape matches `CoverageReport`;
  - `ls_files` handles non-ASCII path (quotePath).
- **`tests/test_claude_code.py`** additions:
  - install writes the skill file; content starts with `---` frontmatter containing `name: tether-onboard` and `disable-model-invocation: true`;
  - install remains idempotent (byte-stable second run, existing `test_install_idempotent` pattern);
  - a user-modified `SKILL.md` is overwritten (tether-owned);
  - allow-list now carries the six `coverage` patterns.
- **`tests/test_cli.py`**: `coverage` registered, `--help` text sane.

Gate: `uv run pytest`, `uv run ruff check`, `uv run ruff format`, `uv run pyright` all clean.

---

## Phase 4 — Doc sync and vault proposals

- **`agent-notes/claude-code/Claude-Code-Integration.md`** — update the files-touched table (skill row), the allow-list section (42 → 48, `coverage` in the subcommand list), and add a short skill section pointing at `skill.py` as source of truth (same pattern as the fragment section).
- **`agent-notes/design/future/DICTION-Future.md`** — add **Onboard** (the act of creating an initial tether graph for an existing project, via the `/tether-onboard` skill) and **Coverage** (fraction of tracked files participating in ≥1 tether; a progress signal, not a target).
- **Vault `DICTION.md` (read-only — propose a diff for the user to apply):** add a `tether coverage` row to Operations once the command ships, since vault DICTION documents "what the code does today."
- **Vault `TODO.md` (read-only):** the user may want to re-word line 25, which currently names this feature "reconcile" — flag, don't edit.

## Phase 5 — Validation

1. **Playground run.** Reset `playground/`, seed it with a small multi-subsystem project (or reuse a case-study setting), run `tether init claude-code`, then `/tether-onboard` in a fresh Claude Code session. Judge: description quality against the bar, false-positive tethers, duplicate-avoidance on a second run, and the final report's usefulness.
2. **Fan-out smoke test.** Confirm the skill actually dispatches parallel subagents from main context and that their structured returns come back usable (research flagged the empirical ceiling as unverified).
3. **Case study material.** Capture transcripts/outcomes so the user can author a case-03 in the vault if desired.

---

## Decisions taken in this plan (flag any you want changed)

1. **Coverage output:** markdown default + `--json`; file lists behind `--list-untethered-files` / `--list-tethered-files`, which compose (both flags → both delimited sections, and the matching JSON arrays). No `--list-all-files` — the denominator is one `git ls-files` away.
2. **Denominator:** `git ls-files` minus `.tether/**`; no other exclusions.
3. **`disable-model-invocation: true`** — explicit `/tether-onboard` only.
4. **No load-time `!` injection in v1** — first instructed action is `tether coverage --list-untethered-files --list-tethered-files` (committed SKILL.md can't carry machine-specific binary paths).
5. **Skill installed unconditionally** by `tether init claude-code` (no opt-in flag) — it's inert until invoked and costs zero context under `disable-model-invocation`.
6. **No `model`/`effort` pin in v1.**

## Out of scope

Reconcile (deferred feature, separate vocabulary), graph visualization (deferred), batch-add / `tether suggest` CLI helpers (the agent can grep; per-`add` calls are prompt-free), per-harness skill variants (follows the existing per-harness fragment plan in [Future-Work](Future-Work.md)), and import/dependency-graph grouping (later refinement over directory grouping).
