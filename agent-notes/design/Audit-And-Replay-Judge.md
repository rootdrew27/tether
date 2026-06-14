# Audit and Replay-Judge — Assertion Integrity Design

Design for verifying the integrity of tether's *assertion layer*: a deterministic `tether audit` command, an LLM replay-judge over assertion history, and the shared data substrate both need. Companion to [Future-Work](Future-Work.md) (journal, background automation) and the Margin eval harness (`evals/margin/`); ecosystem rationale lives in [Ecosystem-Positioning-Analysis](../research/Ecosystem-Positioning-Analysis.md).

Status: design proposal — nothing here is implemented.

---

## The problem: refresh is the load-bearing trust point

`tether refresh` writes new fingerprints and asserts "these two artifacts are semantically aligned right now." Tether cannot verify that claim, even in principle — it detects *change*, never *alignment*. Every HEALTHY state in the system is therefore exactly as trustworthy as the refreshes behind it.

The Asserter is already on record (the refresh travels in a commit, with an author). What's missing is any mechanism that *uses* the record. [Tether-Design-MVP](Tether-Design-MVP.md) says a reviewer can correlate fingerprint changes with content changes in `git log` and challenge a dishonest refresh — true, but it is manual git archaeology nobody will do, the same way nobody reviews a 5,000-line lockfile diff.

The agent integration sharpens the threat: the Stop hook blocks the turn on drift, and the single cheapest action that clears the block is `tether refresh`. That is an incentive gradient pointing at the failure mode that killed snapshot testing — reflexive re-assertion (`jest -u`, lockfile delete-and-regenerate, `doorstop clear all`). The block is the feature, so the gradient cannot be removed; it must be *detectable* when someone slides down it.

Two distinct failure classes, requiring two distinct detectors:

| Failure | Shape | Detector |
| --- | --- | --- |
| **The lazy lie** — refresh ran to silence the signal; no real alignment work | Mechanically visible (one side never moved, bulk clears) | `tether audit` (deterministic) |
| **The wrong belief** — both sides edited, asserter sincerely but incorrectly believes they align | Mechanically clean; only semantics reveal it | LLM judge (reads artifacts + description) |

Audit screens cheaply and deterministically; the judge verifies semantically. Together they form a complete verifier. Neither modifies anything — both are read-side, preserving the "tether reports structural state; consumers interpret" principle.

---

## The shared substrate: replayable assertion history

Both layers consume the same thing: the sequence of assertion events (add, refresh, update, rm) with, for each, the OID pair asserted and the content behind each OID.

**What already exists, by construction:**

- The record's history: `git log -p .tether/tethers/<id>.json` yields every committed fingerprint transition.
- The asserted content: fingerprint blobs are written into the object store at assertion time (`git hash-object -w`), so `git diff <old-oid> <new-oid>` reconstructs exactly what any refresh ratified — no new data collection needed.
- The Asserter: the commit author of the record change.

**The gap: uncommitted intermediate assertions.** Agents (especially in eval runs) may refresh several times and commit once, or never. Only the final record survives; intermediate `(a-OID, b-OID)` pairs are lost (the blobs survive in the object store, but not *which pairs were asserted when*). Two fixes:

1. **Harness-side (eval-only interim):** the Margin fork's Stop hook snapshots the workspace to a shadow ref each turn. No tether changes; covers eval runs only.
2. **Tether-side (the real fix):** the `.tether/journal.log` already planned in [Future-Work](Future-Work.md) as the automation/undo substrate is also exactly this event log. If the journal records every add/refresh/update/rm with timestamp and the asserted OID pairs, the full trajectory is replayable with zero commits.

> Consequence for sequencing: the journal is promoted from "automation prerequisite, build later" to "verification prerequisite, build early." It serves undo, automation auditability, *and* this design.

---

## Layer 1: `tether audit` (deterministic)

Read-side command over assertion history. Reports refreshes whose *shape* warrants review — the same epistemics as DRIFTED: a suspicion heuristic that hands judgment to a human or model, not a verdict.

### Signals, strongest first

1. **One-sided refresh.** Between consecutive assertions, `a.fingerprint` changed but `b.fingerprint` is byte-identical (or vice versa): the refresh ratified drift on one side while the peer never moved. Severity scales with the ratified diff (`git diff old-oid new-oid --stat` — free, blobs are stored). A 240-line code change ratified with zero doc movement is the classic rubber-stamp signature. Robust to squashed/rewritten history — the comparison is record-internal, not commit archaeology.
2. **Bulk-clear bursts.** No `refresh --all` exists, but an agent can loop. N refreshes in one commit or one turn, several one-sided, is the "silencing the alarm" shape.
3. **Description-static churn.** Fingerprints have moved substantially across multiple refreshes while the description is untouched since creation — a hint the recorded *why* is rotting under the assertions.
4. **Decoupled refresh.** The refresh landed in a commit where neither artifact changed — the assertion did not travel with the change it ratifies (the integrity property [Tether-Design-MVP](Tether-Design-MVP.md) names). Weaker signal, legitimately violated sometimes; report, don't flag.

### Output sketch

```
## Refresh audit — 2 of 14 refreshes flagged

019e36df… (cli.py ↔ docs/usage.md)
  refreshed 2026-06-09 by Claude <commit abc123>
  ONE-SIDED: cli.py moved (+38/−2 since last assertion); docs/usage.md unchanged.
  Review whether the doc still covers the new surface. Diff: tether audit 019e36df --diff
```

### Framing rules (load-bearing)

- **"Review these," never "violations."** Legitimate one-sided refreshes exist — a comment-only change ratified, a refactor the doc genuinely doesn't care about; that is *why* refresh-without-peer-edit is allowed at all. If audit cries wolf it suffers the same trust erosion as noisy drift, and the verifier layer dies the way the signal layer would.
- **Audit catches the lazy lie only.** A semantically wrong two-sided refresh passes clean. Escalation to semantics is Layer 2's job (eventually surfaced as `tether audit --judge`).

### Consumers

1. **CLI / PR review / CI.** A reviewer (or bot comment) on PRs containing refreshes: "1 of 3 refreshes is one-sided; here is the ratified diff." Operationalizes the audit trail; gives the tether graph a second guaranteed consumer.
2. **The eval verifier** (below) — shells out to the same logic rather than duplicating it.
3. **Hooks, later and cautiously.** Session-start could mention "2 recent refreshes look one-sided." Optional; nag-fatigue risk.

### Why this is strategically distinctive

No adjacent tool can build it without adopting tether's architecture: it requires assertions recorded as data, content identity captured at each assertion, and history in git. LLM-judged tools (Mintlify, spec-kit-sync) have no assertion record; `LINT.IfChange` has no state; doorstop has assertions but discards the linked content bytes. Snapshot testing's answer to refresh fatigue was social discipline; tether's can be mechanical. This converts the project's best-documented failure mode (assertion decay) into a defensible feature.

---

## Layer 2: the replay-judge (semantic)

Step through assertion history via git (or the journal); at sampled points, an LLM judge reads both artifacts as they were *at that moment* plus the description, and rules on whether the structural state was truthful.

### The rubric

At any point, the structural state is deterministic; the judge's question is whether it is *truthful*:

| | Semantically aligned | Semantically misaligned |
| --- | --- | --- |
| **HEALTHY** | correct | **false health** — the worst cell; a wrong or dishonest refresh upstream |
| **DRIFTED** | false alarm (noise drift — change the relationship doesn't care about) | true alarm — the question becomes: does it get resolved? |

(BROKEN is structural and needs no judge; its handling — rename followed, record retired — is scored mechanically.)

### Metric families (fall out of the cells)

- **False-health rate** — integrity of assertions. The headline trust metric.
- **Unresolved true drift at turn boundaries** — efficacy; the thing tether exists to prevent.
- **Time-to-resolution** — turns/commits from true alarm to correct resolution.
- **False-alarm dwell time** — the noise burden that predicts trust erosion; also the empirical input for locator-granularity decisions ([Future-Work](Future-Work.md) §Locator extensions).
- **Description judgeability** — a description too vague for the judge to evaluate is itself a finding. Expect this to grade onboard-skill output whether asked or not.

### Sampling points (not every commit)

Every commit × every tether × LLM is expensive and mostly redundant. Judge at events:

1. **Every refresh** — judge the assertion with exactly the context the Asserter had.
2. **Every add** — judge initial description quality (doubles as the onboard skill's quality gate).
3. **Turn/episode boundaries** — judge what was left lingering.
4. **Anything audit flags** — always.

Audit as pre-screen bounds judge calls and affords a strong judge model.

### Judge prompt shape

Artifacts at that revision + the description → "does the relationship hold *as described*?" The required description is what makes judging feasible at all — without a recorded why (Fiberplane Drift, IfChange, every inferred system), a judge must first guess what alignment means. This is the data model paying off a second time.

### Judge calibration

The judge is fallible; validate it against ground truth before trusting its scores:

- **Known-answer scenarios.** Seed eval cases where the correct trajectory is known: true drift that must be repaired; noise drift that should be refreshed without peer edits; a stale description that should be updated rather than the files; a rename that should be followed with `update` + `refresh`, not `rm`.
- **Existing case studies as calibration set.** The vault's case-01/02 transcripts are hand-labeled known-answer episodes; the replay-judge automates exactly the evaluation they perform manually. This implements the vault TODO item "Enhanced testing framework for Claude Code integration" (do hooks fire / does Claude respond appropriately / are tethers maintained).

---

## Eval integration (Margin)

Why this matters for the eval specifically: the naive endpoint metric — "how many tethers DRIFTED at episode end" — is *gameable by the exact failure mode under study*. A reflexively-refreshing agent scores perfectly while destroying the system's value. Rubber-stamp rate (audit) and false-health rate (judge) are the correction terms that make any consistency metric meaningful. Build order inside the harness:

1. Seeded tether graphs in eval workspaces (the smoke suite's tether-free repos test plumbing only).
2. Verifier runs post-hoc on run output: replay → audit screen → judge sampled events → metric report. The eval artifact is just the resulting workspace (plus journal/shadow-ref snapshots for uncommitted trajectories).
3. Tasks where cross-file consistency is required but **unprompted** — the prompt names only one artifact; the tether is how the agent should find the other. (Case-01's prompt names both files, which even a control arm largely handles.)
4. Multi-session scenarios where drift originates outside the agent's memory.

---

## Beyond evals: one artifact, three consumers

Because the substrate is reconstructible from the repo (or repo + journal), the same replay-judge runs anywhere tether runs:

- **Eval verifier** — scores treatment arms in Margin runs.
- **Continuous monitoring** — "judge all assertions since last week" on the dogfood repo turns dogfooding into ongoing evaluation of real usage.
- **`tether audit --judge`** — the semantic escalation tier of the audit command, on demand.

That convergence is the strongest sign the underlying primitive — replayable assertion history — is the right thing to build.

---

## Sequencing and dependencies

1. **Journal** (`.tether/journal.log`, from [Future-Work](Future-Work.md)) — the substrate; records assertion events with asserted OID pairs. Interim for eval runs only: harness-side shadow-ref snapshots.
2. **`tether audit`** — deterministic signals over record history (+ journal when present). Shared core exposed so the eval verifier shells out to it.
3. **Replay-judge** — built inside `evals/margin/` first (where calibration scenarios live), generalized to `audit --judge` once stable.
4. **Seeded-graph eval cases + known-answer scenarios** — in parallel with 2–3.

## Open questions

- **Journal format and trust.** The journal is derived/append-only state — gitignored (as Future-Work assumes for derived state) or committed? A committed journal strengthens the audit trail but duplicates what record history already captures for committed work; a gitignored journal covers uncommitted assertions but is local-only and erasable by the very agent being audited. Possibly: gitignored, with the eval harness and CI treating absence-of-journal as "commit-history-only audit."
- **One-sided severity thresholds.** What ratified-diff size flags vs. merely lists? Needs dogfood data; start by reporting everything ranked, add thresholds later.
- **Judge verdict storage.** Where do replay-judge verdicts live for the dogfood/monitoring use (not the eval, which owns its run dirs)? Likely gitignored derived state under `.tether/`.
- **Judge model/cost envelope.** Per-event judging with a frontier model is affordable at eval scale; continuous monitoring may want a cheaper screen-then-escalate split mirroring audit→judge.
- **Does audit examine `update` events too?** A description rewrite that quietly weakens what alignment claims (scope-narrowing) is a subtler integrity hole; out of scope for v1, noted here so it isn't lost.
