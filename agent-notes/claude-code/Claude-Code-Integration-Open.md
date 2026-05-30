Tracking for the integration spec at [Claude-Code-Integration](Claude-Code-Integration.md). Three categories: verifications owed before implementation, decisions to revisit, and deferred features. General (non-Claude-Code-specific) future work — locator extensions, watcher/reconcile, ref-pinning, custom merge driver, etc. — lives in [Future-Work](../design/Future-Work.md).

## Verifications owed

One-time lookups against current Claude Code docs / behavior before implementing the spec:

- **`Tool(path-glob)` permission matcher syntax.** Confirm that the form `Edit(.tether/tethers/**)` (with `**` for recursive glob) is the current syntax, that it matches paths relative to `cwd`, and that it works for all four tools (`Edit`, `Write`, `MultiEdit`, `NotebookEdit`). If the syntax has changed, update the deny entries in the init flow.
- **`@file` import in `./CLAUDE.md`.** Confirm that `@.tether/tether.md` is current, stable (not preview), and not size-limited in a way that would clip the fragment. If imports work differently than expected (e.g., must appear at a specific position in the file, or require a leading slash), adjust the init logic.
- **Stop hook `{"decision": "block"}` continuation semantics.** The docs are silent on what happens after a Stop block. Empirical test owed: does the agent automatically continue in the same turn given the `reason` text as effective input? Or does it wait for the next user prompt? If the latter, the integration's "continuation" framing needs reworking — possibly toward a UserPromptSubmit hook that re-injects context on the user's next prompt.

## Decisions to revisit

These were resolved with a clear "decide now, change later" intent. Both are reversible (low cost to switch).

- **Stop block strategy (currently stateless; planned: session-baseline stateful).** v1 blocks on any non-HEALTHY tether. The eventual target is blocking only on tethers that became non-HEALTHY during this session (baseline captured at SessionStart, diffed at Stop). The upgrade is additive: write a baseline file at SessionStart, read-and-diff at Stop. Pre-existing drift stops being a nag.
- **Failure contract (currently fail-loud; planned: fail-open-but-visible).** v1 exits 2 on hook errors so any breakage is impossible to miss during early development. Before the project has external users, switch to exit 1 — non-blocking notice, user-visible but not impeding. One-line change per subcommand.

## Blocked items

- **Sub-file locator language and examples in `.tether/tether.md`.** The fragment is currently whole-file-only because MVP ships only the `WholeFile` locator. When the CLI grows `LineRange` (and beyond — see [Future-Work](../design/Future-Work.md)), update:
  - The fragment intro sentence to introduce tethers as connecting files *or regions within files*.
  - The "When to create tethers" examples to include a line-range case.
  - The "Key commands" `tether add` entry to reflect the new positional / option syntax for sub-file endpoints.

  Close this item alongside the CLI line-range PR.

## Deferred features

In rough priority order:

- **Loop prevention guard in Stop.** v1 has none. If Stop-block-then-blocked-again loops occur in practice, add a "max N consecutive blocks per session" guard. Telemetry / observability needed to detect.
- **Session-baseline cleanup.** Only relevant once Stop becomes stateful. Baseline files at `.tether/.session-baseline-<session_id>.json` would accumulate; need LRU cap or age-based pruning.
- **`tether init claude-code --dry-run`.** Print what init would do without writing. Easy add when someone wants it.
- **`tether uninstall claude-code`.** Reverse the init flow — remove tether-owned permission entries from `.claude/settings.json`, remove tether-owned hook entries from `.claude/settings.local.json`, remove the `.claude/settings.local.json` line from `.gitignore` if tether added it, remove the import line from `./CLAUDE.md`, leave `.tether/tether.md` for the user to delete manually. Predicates are symmetric with init.
- **Launch-cwd UX.** Claude Code only loads project settings (`.claude/settings.json` and `.claude/settings.local.json` — and therefore both tether's permissions and tether's hooks) from the launch cwd's `.claude/` folder. There is no parent-directory walk-up. Documented under "Project-root discovery gotcha" in [Claude-Code-Integration](Claude-Code-Integration.md). Two touchpoints worth adding to make this surface to users without their having to read the vault: (1) a final-line tip printed by `tether init claude-code` ("Tip: run `claude` from this directory so tether's hooks fire; for work in subdirs, use `claude --add-dir <subdir>`"), and (2) a short paragraph in `.tether/tether.md` explaining the same. Either alone helps; both together close the gap. Defer until a second user actually hits the footgun.
- **PreToolUse on additional triggers.** The MVP injects `<tether-context>` only on `Read`. Other triggers worth exploring as the integration matures:
  - **Edit / Write / MultiEdit.** Belt-and-suspenders for the case where the agent edits a tethered file without reading it first (e.g., the file is already in conversation context from a previous turn). Adds redundancy in the common Read-then-Edit flow; the win is the cold-edit path.
  - **Bash-mediated reads** (`cat`, `head`, `tail`, `less`, `jq` on JSON sources). Requires parsing the Bash command string to extract paths — heuristic, but the existing `if` field in Claude Code hooks v2.1.85+ lets us filter to specific Bash subcommand shapes before spawning.
  - **Prompt `@file` mentions** via `UserPromptSubmit` or `UserPromptExpansion`. Surfaces tether context when the user pulls a tethered file into the conversation directly, before any tool call fires.
  - Implementation note: the existing `pre_tool_use` hook subcommand is already generic — extending it to additional tool names is a matcher change in `settings.local.json` plus the file-path-extraction path for whichever tool. No new subcommand is needed for Edit/Write/MultiEdit since their `tool_input.file_path` lives in the same place as Read's.
- **Observability — `tether.log` for hook activity.** Useful for understanding what the PreToolUse hook saw and emitted on each Read across a session: which file, which tethers matched, whether output was emitted, latency. A gitignored newline-delimited JSON file under `.tether/` is the natural shape. Defer until hook misbehavior or silent regressions surface as real friction.
- **Bash write-denial via PreToolUse heuristic.** Plug the "agent runs `sed -i .tether/tethers/...`" gap by adding a PreToolUse Bash hook that scans the command string. Heuristic, defeatable, but raises the bar. Defer unless the gap is actually exploited.

## Empirical validation

Most of the agent-facing surfaces in the integration — the `.tether/tether.md` fragment content, the SessionStart message density choices, the Stop reason format — are currently authored to taste. No measurement yet shows which phrasings actually steer agent behavior best. Two related pieces of work would replace these guesses with measured choices:

- **Test project / environment.** A scaffolded sample project that uses tether, seeded with a mix of HEALTHY, WEAKENED / DRIFTED, and BROKEN tethers, plus a battery of agent-driven tasks with expected outcomes — for example: "agent should `tether refresh` the WEAKENED tether after aligning both sides, then end the turn cleanly", "agent should propose a path update for the BROKEN tether before doing other work", "agent should create a new tether when adding a doc/code pair." Acts as a regression harness for the integration: any change to the fragment, hook output formats, or hook semantics gets evaluated against the same task battery.
- **Fragment content experiments.** Once the test environment exists, run controlled variations of `.tether/tether.md` content (terser vs. more verbose; with/without per-state action mappings; with/without the "create tethers freely" framing; different ordering of sections; etc.) and compare task-battery outcomes. Use this to retire authored guesses in favor of measured choices, and to detect regressions when the fragment is edited.

Without this scaffolding, every change to the agent-facing surfaces is a hunch. With it, fragment edits become testable, and the "decisions to revisit" items above (stateless→stateful Stop, fail-loud→fail-open) gain an objective signal for when to flip.

## ADRs to consider

When the spec hardens and the integration starts being depended on by users beyond the author, two decisions are worth documenting as ADRs:

- Why Stop is stateless in v1 (rationale: simplicity during early development; trade-off explicitly accepted).
- Why failure is fail-loud in v1 (rationale: catch integration breakage immediately during sole-user phase; trade-off explicitly accepted).

Both currently fail the "hard to reverse" ADR criterion (cost of upgrade is small), so they're not ADRs *yet*. If the upgrade gets harder than expected — e.g., because user behavior comes to depend on the loud-fail noise — the ADR criterion will be met retroactively.
