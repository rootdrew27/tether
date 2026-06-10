Research backing the **`tether onboard` skill** — a Claude Code Skill, installed into user projects by `tether init claude-code`, that surveys an existing codebase and autonomously creates a starter tether graph. This doc records the mechanics and constraints the design must respect; the design itself lives in the companion design doc. Scope decisions already made with the user: the skill is named **onboard**, is distinct from the deferred *reconcile* feature, runs largely autonomously once invoked, groups files by **directory structure**, and leans on heuristics with the model as final judge. A new structural-only CLI command, `tether coverage`, gives the model a quantitative read on remaining work.

The code is the source of truth for current tether behavior; this is the source of truth for why the skill is shaped the way it is.

## Claude Code skill mechanics (verified v2.1.168, 2026-06-06)

Verified against the live docs at `code.claude.com/docs/en/skills.md` and `features-overview.md` via the `claude-code-guide` agent. Findings below are current as of v2.1.168; flagged uncertainties are called out inline. The installed CLI on this machine is v2.1.160 (per `tether-vault/design/Claude Code.md`) — close enough that the skill surface is stable, but the design doc should re-verify any field it depends on against the version actually installed at implementation time.

### Format and layout

A project skill is a directory under `.claude/skills/<dir-name>/` containing `SKILL.md` (YAML frontmatter + markdown body). **The directory name becomes the invocation command** (`/<dir-name>`); the frontmatter `name` is only a display label. So the install writes `.claude/skills/tether-onboard/SKILL.md` and the command is `/tether-onboard`. Supporting files (templates, reference docs, scripts) may sit alongside `SKILL.md` and are loaded only when the body references them.

### Frontmatter fields relevant to onboarding

| Field | Use for onboarding |
|---|---|
| `description` + `when_to_use` | How the model decides to auto-invoke. **Combined text is truncated at 1,536 chars** — keep it tight. |
| `disable-model-invocation` | `true` ⇒ model can't auto-trigger; only `/tether-onboard` works. **Zero context cost until invoked** (description not loaded). |
| `user-invocable` | `false` ⇒ hidden from the `/` menu (Claude-only). We want the opposite — leave default (true). |
| `allowed-tools` | Pre-approve `Bash(tether *)` (or the specific subcommands) so the autonomous run isn't interrupted by permission prompts. |
| `context: fork` | Runs the whole skill **as a subagent**. **Has a fatal interaction with fan-out — see below. Do not set for onboarding.** |
| `agent` | Which subagent type when forked. N/A once we decide not to fork. |
| `model` / `effort` | Optional override for the onboarding run (it's survey-heavy; a stronger judge may be warranted). Decision deferred to design. |
| `paths` | Globs that gate auto-invocation. Not useful here — onboarding is whole-project. |
| `shell` | `bash` (default) for the dynamic-injection commands below. |

### The fan-out constraint (key finding)

Subagent nesting is capped at one level:

- **Main conversation** → can spawn subagents (it holds the subagent-spawning Task/Agent tool).
- **A subagent** → cannot spawn further subagents (the tool isn't in its pool).
- **A skill with `context: fork`** → runs *as* a subagent, so it inherits the subagent restriction and **cannot fan out**.

Consequence for the design: **the onboarding skill must run in the main conversation context (no `context: fork`)** so the main agent keeps the ability to dispatch one subagent per subsystem. A forked skill would survey everything in a single context — losing both the parallelism and the per-subsystem context isolation that make large-repo onboarding tractable.

The tradeoff of not forking: the skill body, the subagent summaries, and the `tether add` outputs all accumulate in the main session window. This is acceptable because onboarding is a dedicated, user-initiated session — the whole point of that session is the onboard — and the heavy file-reading stays isolated inside the per-subsystem subagents, which return only structured candidate lists. (Caveat: the guide agent could not find a documented example of a skill orchestrating many parallel subagents; the *mechanism* — main-context skill body instructing the agent to use the Task/Agent tool — is the standard documented path and is reliable, but the empirical ceiling on concurrent subagents from a single skill is unverified. The design should treat aggressive fan-out (10+ concurrent) as needing a smoke test.)

This nesting rule is consistent with the existing integration spec's note that subagents/commands are discovered by walking up from cwd while hooks are not (`Claude-Code-Integration.md` §"Project-root discovery gotcha"). Skills are commands, so they *are* discovered up-tree.

### Dynamic data injection

The `!`backtick`` syntax runs a shell command **once at skill-load time** and substitutes its stdout into the body as plain text before the model reads it. Inline (`` !`tether coverage` ``) and fenced (```` ```! ... ``` ````) forms both work; substitution is single-pass (injected output isn't re-scanned). This is directly useful: the skill can open with a live coverage read and a file-tree snapshot, so the model starts grounded in the actual project state rather than a stale description.

Caveat: `"disableSkillShellExecution": true` in settings disables this (output becomes a `[shell command execution disabled by policy]` placeholder). The skill must degrade gracefully — instruct the model to run `tether coverage` itself as a Bash call if the injected block is the disabled placeholder. Don't make load-time injection the *only* path to the data.

### Invocation and the auto-trigger decision

By default a skill is both user-invocable (`/name`) and model-auto-invocable (semantic match on description). For onboarding, auto-invocation is a liability — we don't want the model deciding mid-session to onboard the whole project. Two viable postures, decision deferred to the design doc:

- **`disable-model-invocation: true`** — only `/tether-onboard` triggers it. Cleanest; zero context cost; but the model can't act on a natural-language "tether up this project" without the user typing the command.
- **Leave model-invocation on, with a tightly-scoped description** ("Use ONLY when explicitly asked to create an initial tether graph for a not-yet-tethered project") — lets natural-language requests work, at the cost of a small always-on description budget and some auto-trigger risk.

Leaning toward `disable-model-invocation: true`: onboarding is heavyweight and deliberate, and the user already expects to invoke it explicitly.

### Context cost

- Skill **descriptions** load at session start for every non-`disable-model-invocation` skill (~tens of tokens each). The body loads only on invocation and then **persists in the session** (compaction preserves up to 5,000 tokens/skill, 25,000 across all skills).
- Implication: keep the `SKILL.md` body lean (the guide suggests <500 lines) and push any long reference material into sibling files the body pulls in on demand. The heavy lifting belongs in subagents, whose contexts don't count against the main window.

### Distribution and install gotchas

- **Where:** project scope (`.claude/skills/tether-onboard/`), committed, team-shared — matches the rest of the integration. The installer overwrites tether-owned skill content the same way it overwrites `.tether/tether.md`.
- **Precedence:** managed > user (`~/.claude/skills`) > project. A user-level skill with the same dir name would shadow ours. **Name collisions within a scope are resolved silently** (one kept, one dropped, no warning) — so the distinctive `tether-onboard` prefix matters.
- **Discovery & live reload:** project skills are picked up by walking up from cwd and take effect within the session without restart — so a freshly-installed skill is usable immediately after `tether init claude-code` in an already-running session (though the hooks half of the install still requires the launch-cwd rule).
- **Trust/permissions:** project skills require workspace trust; `allowed-tools` in frontmatter is what keeps the autonomous run prompt-free.

## Survey and heuristic strategies

The skill's job is to turn an untethered repo into candidate relationship pairs, then judge them. Heuristics propose; the model disposes (per the user's framing).

### Grouping: directory structure (decided)

Group git-tracked files by directory subtree. Cheap, language-agnostic, and maps naturally onto the subagent fan-out: one subagent per top-level subsystem (`src/`, `docs/`, `tests/`, `schema/`, …), each surveying its subtree plus cross-references out of it. Dependency/import-graph grouping is richer but language-specific and heavier — explicitly deferred as a later refinement.

### Candidate relationship patterns (heuristic seeds)

These are prompt-level guidance for the survey, not CLI features. The model greps for them and decides which are real:

- **Doc ↔ code** — a markdown/rST file that names, documents, or specifies a source file (README sections, `docs/usage.md` ↔ `cli.py`, design notes ↔ implementation). Strongest tether class; mirrors case-01/case-02.
- **Test ↔ impl** — `tests/test_foo.py` ↔ `foo.py`, `*_test.go` ↔ `*.go`, spec files ↔ subjects. High-precision by naming convention.
- **Schema ↔ consumer** — a JSON/proto/SQL/`.toml` schema and the code that reads or validates against it.
- **Config ↔ reader** — a config file and the module that parses it.
- **Duplicated constants / contracts** — the same magic value, route table, or error code defined in two places that must move together.
- **Cross-language mirrors** — an API contract reflected in both a backend handler and a client stub.

Precision over recall: a tether whose drift wouldn't matter is noise that trains the user to ignore the Stop hook. The model should skip pairs it isn't confident carry a real, drift-sensitive relationship, and record *why* in the description — which is the actual deliverable (case-01 showed description quality, not tether count, is what makes the integration work).

### The loop

Survey (fan-out per subsystem) → judge + author descriptions → `tether add` → measure (`tether coverage`) → iterate on the untethered remainder → report. Coverage is a **progress signal, not a target**: 100% is wrong because many files have no drift-sensitive partner. The model decides when returns diminish and lists what it deliberately left untethered, with reasons.

## Large-repo context budget

The constraints above dictate the strategy:

- **Isolate file-reading in subagents.** Each subsystem subagent reads its files and returns a compact, structured candidate list (pairs + draft descriptions + confidence), never raw file dumps, to the main context.
- **Use `tether coverage` as durable state, not memory.** Because coverage is recomputable from disk at any time, onboarding is **resumable across sessions** — a second `/tether-onboard` run picks up the untethered remainder without re-surveying what's done. This keeps any single session bounded.
- **Keep the skill body lean** and let subagents carry the verbose survey instructions (a subagent's prompt doesn't persist in the main window).
- **Inject coverage at load time** so the model's first action is informed by the current state, avoiding a redundant initial full scan.

## Open questions for the design doc

1. **Auto-invocation posture** — `disable-model-invocation: true` (lean) vs. tightly-scoped auto-invocable description.
2. **`tether coverage` surface** — confirmed as its own structural-only command (not `tether show --untethered`). Design owes: output shape (human markdown vs. `--json`), what "tracked file" means precisely (respect `.gitignore`; include/exclude untracked? — almost certainly `git ls-files` only), and whether it lists the untethered set or just the percentage (likely both, behind a flag).
3. **Fan-out ceiling** — how many concurrent subsystem subagents is safe/effective; needs a smoke test on a real mid-size repo.
4. **Description-quality bar** — how the skill instructs the model to author descriptions good enough to be the deliverable, and whether the report self-grades them.
5. **Model/effort override** — whether the skill pins a stronger judge model via frontmatter.
6. **Graceful degradation** when `disableSkillShellExecution` blocks load-time injection.

## References

- Claude Code Skills docs — `code.claude.com/docs/en/skills.md` (format, frontmatter, dynamic injection, discovery/precedence).
- Claude Code features overview — `code.claude.com/docs/en/features-overview.md` (context costs, skill content lifecycle).
- [Claude-Code-Integration](../claude-code/Claude-Code-Integration.md) — existing hook/permission/install mechanics the skill install extends; §"Project-root discovery gotcha" for the walk-up asymmetry.
- [CC-Integration-Research](CC-Integration-Research.md) — pre-MVP survey of CC surfaces (skills/subagents/hooks); superseded on specifics but useful background.
- `tether-vault/case-studies/case-01` and `case-02` — empirical basis for "description quality is the deliverable."
- [Future-Work](../design/Future-Work.md) §"`tether reconcile`" — the deferred repair feature this skill is deliberately *not*.
