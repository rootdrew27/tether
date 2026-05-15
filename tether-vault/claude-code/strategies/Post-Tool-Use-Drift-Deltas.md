---
title: "Strategy: PostToolUse drift deltas"
tags:
  - integration
  - claude-code
  - strategy
  - hooks
type: integration
status: deferred
---

**Strategy.** Wire a PostToolUse hook that fires on every Claude Code tool call. After each invocation, recompute tether status, diff against the last-cached status snapshot on disk, and emit only the per-tether aggregate-state *transitions* since the last check. Pre-existing drift the agent didn't touch stays silent. Drift the agent just introduced surfaces immediately, at the decision point closest to its cause.

By delivering drift signal at the moment of cause rather than at turn boundaries, the agent can incorporate it as ongoing context instead of as a turn-ending obstacle. The goal is better agent decisions (informed by live state) and fewer wasted actions (defensive status checks, post-refresh confirmations, unilateral resolutions of judgment calls).

## Problem this addresses

The current integration surfaces drift via the Stop hook at turn end. Three observed failure modes:

1. **Wrong moment.** The signal arrives after the agent has mentally wrapped up the turn. Incorporating drift news at that point reads as a forced U-turn rather than a continuation of ongoing thought.
2. **Pressure toward unilateral resolution.** Even with the block reason text rewritten to permit "surface to user", the turn-end framing still nudges the agent toward "fix it and end" rather than "surface the judgment call and end". The structural problem is the timing, not the wording.
3. **Blanket reporting.** Stop reports the full non-HEALTHY set on every block, including drift that existed before this session. The agent sees pre-existing drift repeatedly across turns with no signal distinguishing new transitions from standing state.

A symmetric set of issues affects compensating agent behavior: defensive `tether status` calls before turn end, post-`refresh` confirmation calls. Both the Stop hook and the agent are working around the same gap — drift is observed at turn boundaries, not at decision time.

## Core idea

Push the drift signal to decision time. Fire a PostToolUse hook on every tool call (no tool filter, no command parsing). On each fire:

1. Recompute current tether status (full evaluation).
2. Load the last-cached status snapshot from disk.
3. Diff current vs. cached.
4. Emit only the per-tether aggregate-state transitions (e.g. `HEALTHY → WEAKENED`).
5. Update the cache.

If no transitions occurred, the hook produces no output.

The PostToolUse matcher is `*` — no tool filtering. Bash commands that mutate files, MCP tools that write to disk, and any future tool Claude Code adds are all covered without command-string parsing or per-tool heuristics. The unit of work is "tool call boundary"; what the tool did is irrelevant to the hook.

## Behavior example

Session timeline for an agent editing a tethered code file:

| Tool call | Action                            | Tether X aggregate    | Hook output                                                                                                                                                            |
| --------- | --------------------------------- | --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1         | `Read docs/auth.md`               | HEALTHY               | (silent)                                                                                                                                                              |
| 2         | `Read src/auth.py`                | HEALTHY               | (silent)                                                                                                                                                              |
| 3         | `Edit src/auth.py`                | HEALTHY → WEAKENED    | `Tether X (describes docs/auth.md → src/auth.py) just became WEAKENED — docs/auth.md unchanged. Decide: align the doc, surface to user, or update the description.` |
| 4         | `Read docs/auth.md`               | WEAKENED              | (silent — no transition)                                                                                                                                              |
| 5         | `Edit docs/auth.md`               | WEAKENED              | (silent — still WEAKENED, the aggregate didn't transition)                                                                                                            |
| 6         | `Bash uv run tether refresh X`    | WEAKENED → HEALTHY    | `Tether X resolved.`                                                                                                                                                  |

Properties on display:

- The agent saw the drift exactly once (call 3), at the moment of cause.
- Repeated tool calls under unchanged aggregate state stay silent.
- The Bash-mediated `refresh` is caught without command parsing.
- The closing `Tether X resolved` confirms alignment without the agent needing to run `tether status` defensively.

## Properties

- **Bash coverage for free.** The hook runs after every tool call, including Bash, MCP tools, and any other tool Claude Code adds.
- **Signal targeted by time.** Only changes since the previous tool call are reported. Pre-existing drift inherited from a prior session is not re-surfaced here — SessionStart owns that.
- **No banner-blindness.** Each transition is reported exactly once, in the call that caused it.
- **Bounded token cost.** Most tool calls produce zero output. The cost of running the check is bounded by a stat-based fast path (see Implementation sketch).
- **Decoupled from the agent's turn shape.** No turn-end intervention; the agent ends turns on its own judgment.

## Implementation sketch

**Cache file.** `.tether/.tool-state-cache.json` (gitignored, alongside the existing `.tether/snapshot.json` pattern). Stores, per tether, the last-observed aggregate state and per-artifact `(file_oid, region_hash)` pair. The per-artifact hashes support a stat-based fast path: on the next call, files whose mtime is unchanged skip rehashing entirely. For Read/Grep-heavy turns this means most PostToolUse fires resolve in milliseconds.

**Diff and output.** Per tether, emit one short paragraph when the aggregate state changed since the cached value. Aggregate-only transitions are the v1 reporting threshold; per-artifact transitions (e.g. "the docs side just drifted while the code side is still HEALTHY") may be added later if the aggregate-only signal proves too coarse.

For BROKEN transitions, output mirrors the fragment's BROKEN guidance: suggest `tether update --src-path/--dst-path` to follow a rename, fall back to `tether rm` if the file is truly gone.

**Errors.** Corrupt records, unreadable files, etc. are reported once per error key and cached so subsequent calls don't re-spam. Entries clear when the underlying issue resolves.

**Hook config** in `.claude/settings.local.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PROJECT_DIR}/.venv/bin/tether hook claude-code post-tool",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

**Output channel.** Open question — see below.

## Interaction with SessionStart

SessionStart retains its current role: report all pre-existing non-HEALTHY tethers at session open, so the agent has a baseline before any tools run. To avoid double-reporting on the first PostToolUse call, SessionStart writes the cache file at the end of its run with the state it observed. The first PostToolUse then diffs against "what SessionStart already told you" rather than empty state. Pre-existing drift is reported once (by SessionStart) and not re-emitted as a transition by the first tool call.

## Stop hook disposition under this strategy

Two reasonable options:

- **Drop Stop entirely.** Trust PostToolUse + SessionStart + agent judgment. If the agent ends a turn with unresolved drift, the next SessionStart catches it — delayed but not lost.
- **Keep Stop as non-blocking terminal output.** No `{"decision": "block"}`; print a one-line drift summary to the terminal. The turn ends as the agent intended; the user gets visibility and can choose to follow up.

Dropping is cleaner; keeping is a low-cost user-side safety net. Defer the choice until PostToolUse is observed in practice — if PostToolUse keeps drift visible to the agent reliably, Stop is unnecessary.

## Tradeoffs and gaps

- **Per-call overhead.** Even with a stat-based fast path, every tool call incurs a subprocess fork and at minimum a stat sweep over tethered files. Negligible for the target audience of curated tethers (tens, low hundreds). Could matter for projects with thousands of tethers; not an MVP concern.
- **Agent ignorance.** If the agent receives a transition message and chooses to ignore it, the turn ends with unresolved drift. PostToolUse alone has no enforcement teeth — this is the same tradeoff already accepted in exchange for agent autonomy.
- **Multi-step resolutions are chatty.** A `tether update --description` followed by `tether refresh` produces transitions on both calls. Probably fine; each transition is informative on its own.
- **Aggregate-only granularity may hide nuance.** Both-sides-DRIFTED that "evolves" into a different both-sides-DRIFTED is silent under aggregate-only diffing. Adding per-artifact diffing closes this but adds output volume.

## Open questions

1. **PostToolUse output channel semantics.** Hook output can go to stderr (Claude Code surfaces as tool feedback) or be JSON with `additionalContext` / `hookSpecificOutput`. Verification owed: which channel Claude Code currently routes back into the agent's context reliably for PostToolUse, and whether the agent reads it as a useful signal vs. ignores it as noise. The viability of this entire strategy depends on this.
2. **Diff granularity.** Aggregate transitions only, or also per-artifact transitions? Start with aggregate; revisit if practice shows it's too coarse.
3. **Stop disposition.** Drop entirely vs. keep as non-blocking terminal output. Defer until PostToolUse is observed.
4. **Cache hygiene.** Cleared when? On `tether init`? On explicit `tether reset-cache`? Stale-entry pruning when tethers are deleted via `tether rm`?
5. **Empirical validation.** Will the agent actually use transition messages well, or will it default to running `tether status` anyway? The test-project / agent-task-battery harness in [[Claude-Code-Integration-Open]] is what would answer this — this strategy and that harness ship in roughly the same window.

## Status

**Deferred — not MVP.** The current integration ships with SessionStart + Stop blocking; this strategy is a planned replacement / augmentation once the MVP integration has been shaken out in practice and the empirical-validation harness exists. Implementation depends on:

- Verification of PostToolUse output channel semantics in current Claude Code.
- Decision on Stop disposition (drop vs. keep non-blocking).
- A stat-based fast path for status checks to keep per-call cost low.

## Related

- [[Claude-Code-Integration]] — current integration spec (SessionStart, Stop, fragment).
- [[Claude-Code-Integration-Open]] — open items, including the session-stateful Stop refinement this strategy generalizes and the empirical-validation harness this strategy depends on.
