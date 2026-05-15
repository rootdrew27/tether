---
title: Future work
tags:
  - design
  - deferred
type: design
status: active
---

Deferred design and CLI work explicitly scoped out of MVP but discussed and shaped during design. Each item has rationale for the deferral and a rough trigger for picking it up. Distinct from [[Claude-Code-Integration-Open]], which tracks items specific to the Claude Code integration.

## Locator extensions

The MVP ships only the `WholeFile` locator — every tether endpoint is the whole file at its recorded path. The data model is locator-aware, so additional locator types are strictly local additions.

### `LineRange` (contiguous start–end line interval)

Tether between a region of one file and a region of another (e.g., lines 14-16 of `file1` connected to lines 200-220 of `file2`). Three sub-questions need answers before this ships:

- **CLI surface.** Positional (`tether add docs/spec.md:§2 describes src/impl.py:80-120`) vs. flag-based (`--src-range 80-120`). The fragment example syntax flows from this.
- **Resolution semantics under edits.** Three viable models — fixed line numbers (brittle), content-tracking re-locate (heuristic, needs ambiguous-match handling), or hybrid with anchor-context windows.
- **State machine extension.** A "same content, different lines" condition probably wants its own pseudo-state (e.g., `MOVED`) to distinguish from content drift.

When LineRange lands, the `.tether/tether.md` fragment intro updates to introduce sub-file relationships and the examples gain a line-range case. That fragment update is tracked separately in [[Claude-Code-Integration-Open]].

### Language-aware locators

Markdown section paths, AST queries via tree-sitter, explicit region markers, language-server-driven symbol references. Each is a local addition to the locator vocabulary; the data model already supports them. The substantive discussion lives in [[Tether-Design-MVP]] §"Looking forward: language-aware extensions" — this section is the cross-reference.

## Project-wide files

Some files apply to *every other file* in a project rather than to a specific peer: `CLAUDE.md`, `AGENTS.md`, `.cursorrules`, top-level style guides, `README.md`, `LICENSE`. They don't behave like ordinary artifacts under tether's current model.

A few axes where the friction shows up:

- **Relationship semantics.** A `describes` tether from `CLAUDE.md` to `src/auth.py` is technically valid but semantically weak — `CLAUDE.md` describes the whole codebase, not `auth.py` in particular. Asserting alignment with `tether refresh` claims a connection narrower than what the file actually represents.
- **Drift radius.** When a project-wide file changes, every implicit relationship it participates in is affected, not one. The per-tether refresh model isn't a natural fit when one edit logically invalidates every artifact paired with it.
- **Cardinality.** Materializing the relationship explicitly (every code file holding a tether to `CLAUDE.md`) explodes the tether graph for no real informational gain — the relationship is universal, not selective.

Tether may want to handle these uniquely. The shape of "uniquely" is open: a "project" pseudo-target that tethers can name without picking a specific peer, a separate registry outside the tether graph for files whose audience is everything, or a dedicated relationship class whose other side is the project itself. No direction chosen — flagging the question so it doesn't get lost when the first user asks "should I tether `CLAUDE.md` to my code?"

## Storage and fingerprints

### Ref-pinning for fingerprint bytes

The MVP writes fingerprint blobs to git's object store via `git hash-object -w` and accepts the GC race: unreachable blobs are garbage-collected after git's default two-week grace period. A tether against content that stays uncommitted for 2+ weeks loses its fingerprinted bytes — drift detection still works (the stored OID is in the tether record) but diff inspection breaks (`git cat-file -p <oid>` fails).

The hardening is to pin each fingerprint with a tether-managed ref under e.g. `refs/tether/<uuid>-src`, making the blobs reachable and immune to GC. Operational cost:

- Ref naming scheme — per-side-per-tether vs. flat-per-blob.
- Cleanup on `tether rm` (delete refs) and `tether refresh` (replace refs to new OIDs).
- Handling when two branches refresh the same tether — each branch writes its own ref; merge picks the winner.

A hybrid that pins only when the blob isn't already reachable from a commit is the most efficient option but adds a `git log --find-object=<oid>` check per `tether add` — not free at scale.

### Custom git merge driver

The MVP trusts git's text merge for tether records, relying on sorted-key pretty-printed JSON to keep most merges clean and read-validation to catch corrupted resolutions. A custom merge driver registered via `.gitattributes` could be tether-aware: for fingerprint conflicts, pick the side whose OID matches the merged file's actual current content; for description conflicts, fall back to text merge.

Adds: a `.gitattributes` entry written by `tether init`, a merge-driver subcommand, and tests covering the common conflict scenarios.

### Append-only record model

A more radical alternative: each refresh produces a *new* tether record with a new UUID, and the old record is marked superseded. Merge conflicts at the record level become impossible because each branch writes a separate file. The "current" tether is whichever record in the supersession chain has no successor.

Downsides: breaks "one JSON file per tether" — supersession chains add a layer of indirection; loses the UUIDv7 = creation-order property at the per-tether level; status output has to walk chains. Heavier audit trail in exchange for zero-conflict storage.

## CLI surface

### `tether watch`

A long-running process listening to filesystem events. On `FileMovedEvent`, rewrites tether paths immediately — eliminates the "user renamed a file in the editor, tether went BROKEN" case. Doubles as the substrate for an event subscription model.

Deferred because it introduces a process-lifecycle model nothing else in tether uses (daemonization, session-bound process management, event-stream schema, inotify-watch-limit handling). For MVP, renames go through `tether mv` (explicit) instead of being auto-detected.

### `tether reconcile`

A one-shot offline scan. Compares a content-hash snapshot (gitignored, at `.tether/snapshot.json`) against current disk state; unique hash matches infer rename and rewrite paths. Multi-match reported as ambiguous; no-match reported as broken.

The companion to the watcher — covers renames the watcher can't see live (editor write-then-replace produces delete+create, not move). MVP defers this; every rename produces a BROKEN tether the user resolves explicitly. Reconcile lands when manual resolution becomes the limiting factor.

When reconcile ships, `tether init` starts writing `.tether/.gitignore` with `snapshot.json` to keep derived state out of git.

### Event subscription model

The README mentions: "Users (i.e. applications) can subscribe to events and filter events based on link type, file name, etc." Subscriptions imply a long-running event source (the watcher) and a stable consumer contract: event JSON schema, filter semantics, delivery guarantees.

No consumer exists yet — the Claude Code integration uses one-shot hook subcommands. Designing the contract speculatively risks locking in shapes that don't fit the first real consumer. Defer until there's a concrete need.

### "How tethered is this file" utility

Obsidian-CLI-style query: given a path, list every tether that references it. Useful for the agent when deciding whether to create a new tether or follow an existing one, and for humans browsing relationships in unfamiliar code. Locator-aware output once sub-file locators ship.

Suggested surface: `tether refs <path>` or `tether for <path>` — name TBD.

## Background automation

The MVP keeps the user on the hook for path moves and dead-tether cleanup: every rename produces a BROKEN tether, every removed-file pair sits in `tether status` until the user runs `tether rm`. The intended trajectory is for tether to handle these silently — the user should not think about tether between session boundaries unless the system genuinely needs a human in the loop (semantic alignment, ambiguous matches). Everything below is the path from MVP-explicit to background-by-default.

The line automation must not cross is `tether refresh`. Refresh asserts "these two artifacts mean the same thing right now" — that is the user's voice, and the drift signal exists precisely because someone has to actively re-assert it. Auto-refresh erases the signal tether exists to produce. The items below are identity bookkeeping (paths, presence, archival) and stay on the safe side of that line.

### Journal and undo

Every automatic action is logged and reversible. A `.tether/journal.log` (newline-delimited JSON) captures each auto-mutation — `{"action": "auto-update", "tether": "<uuid>", "from": "doc-a.md", "to": "docs/usage.md", "reason": "unique content match", "ts": "..."}` — and a `tether undo <action-id>` command rolls back individual actions, with `tether undo --since <ts>` for batches. Foundational: without it, automation is unauditable and users will not trust it. The rest of this section assumes this substrate exists.

### Refined BROKEN diagnostics

`check_artifact` today returns BROKEN with optional `rename_candidates` from `git log --find-object`. Extend it to disambiguate the silent cases:

- **Deleted in HEAD's history.** `git log -1 --diff-filter=D -- <path>` — if the path existed and was deleted, surface the commit and date. High-confidence "this is dead."
- **Never seen.** Blob OID has never appeared in `git log --all` and the path has no commit history. Low-confidence; possibly uncommitted, possibly gc'd. Stays manual.
- **In flux.** `git status` shows an un-staged move involving the path. The user is mid-rename; automation holds off.

Surfaced as adjacent fields on the existing BROKEN state, not as new state values — adding `DEAD` to the enum doubles the per-artifact state space without buying clarity that fields cannot.

### Reconcile-on-status

Fuse `tether reconcile` into every `tether status` invocation (including hook-driven calls). For each BROKEN tether, hash the working tree and look for a file whose current content matches the fingerprinted blob. Unique match → auto-update the path and journal it. Multi-match → report ambiguity. No-match → BROKEN with the refined diagnostics above.

The shift in posture: reconcile stops being a manual command and becomes ambient. The standalone `tether reconcile` survives as the explicit hammer for "force a full scan now."

- Works for *uncommitted* renames — content matching does not need git history.
- Foot-gun: a copy looks like a move. Mitigate by requiring the original path to be absent on disk; a copy leaves both old and new, a move leaves only new.
- Cost: O(tracked-files × broken-tethers) hashing per status call. `.tether/snapshot.json` (already planned for `tether reconcile`) is the natural cache.

### Auto-archive confidently-dead tethers

When both artifacts are BROKEN, no content matches exist, and both paths are deleted in HEAD's history, tether silently moves the record to `.tether/tethers/archived/<uuid>.json` and removes it from active counts. Logged. Recoverable via `tether restore <uuid>`.

The never-committed-and-now-gone case is deliberately *not* auto-archived. Ambiguity (uncommitted? deleted? renamed-not-staged?) stays in front of the user; only "deleted in HEAD" is treated as definitive.

Subsumes the manual `tether prune` command that would otherwise be needed for bulk cleanup.

### Hooks as the daemon you do not write

Most workflows do not need a long-running watcher because the Claude Code integration already provides natural trigger points.

- **SessionStart** runs reconcile-on-status. Coming back to a session, tether catches up automatically.
- **Stop** runs reconcile-on-status. Within-session edits get reconciled at the end of each turn.
- **Optional git pre-commit hook** (installed by `tether init --with-git-hooks`, off by default) runs reconcile + auto-archive at commit boundaries. Catches renames committed without `tether mv` and marks newly-deleted artifacts.

`tether watch` becomes one trigger among several — useful for users who edit outside Claude Code or want sub-second response, but not a prerequisite for hands-off behavior.

### Coding-agent self-healing

Extend the Stop hook from reporting to acting. When Stop finds a unique-content-match BROKEN tether, the hook performs the auto-update before reporting. When it finds a confidently-dead tether, it archives. The output then reads "tether auto-updated X, auto-archived Y — 0 active issues remain" instead of "3 BROKEN, fix manually."

Composes the primitives above (reconcile-on-status, auto-archive, journal) inside the harness. The agent sees the auto-actions in its own transcript and can mention them, ask the user about ambiguous cases, or trigger undo if the user complains — becoming an interpreter of tether's automation rather than a competitor to it.

### Sequencing

Journal first (substrate). Then refined BROKEN diagnostics (cheap, read-only). Then reconcile-on-status and auto-archive (the substantive primitives). Then hook-as-trigger plumbing (delivery). The watcher comes last, and only if the hook-driven model leaves a real gap.

## Other integrations

### Per-harness fragments

The Claude Code integration is one harness. Cursor, Aider, Codex, and others have their own memory/hook/permission conventions. Each gets its own per-harness fragment (`.cursor/tether.md`, `.aider/tether.md`, etc.) and a corresponding `tether init cursor` / `tether init aider` subcommand. Same pattern as `tether init claude-code`, different file paths and vocabulary.

Deferred — MVP is Claude-Code-only. The "Note on scope" in [[Claude-Code-Integration]] acknowledges this is the first harness, not the only one.

The "how tethered is this file" CLI utility above is also the foundation for the **PreToolUse Read hook for tethered-file context injection** — a Claude-Code-specific deferred feature tracked in [[Claude-Code-Integration-Open]]. Both ship together.

## Normalizer extensions

The MVP normalizer pipeline is fixed in code with a hardcoded tabstop of 8. Three future directions:

### Tabstop configuration (`.tether/config.json` + `.editorconfig`)

The MVP normalizer is locked to `tabstop=8`. Projects using a non-default tab width (2, 4) see false DRIFTED on tab-vs-space reformats. The planned surface, specified in [[Normalization]] §"Configuration":

- Read `normalize.tabstop` from `.tether/config.json` (project-level override).
- Read `.editorconfig` per file for `tab_width` and `indent_style`/`indent_size` (per-file override).

When this ships, `tether init` starts writing a minimal `.tether/config.json`, and the design doc's claim that init writes that file becomes accurate. Tracked here because both pieces (the config file's existence and its consumers) move together.

### Broader configurability

Per-project overrides in `.tether/config.json` for which passes run (e.g., "disable trailing-whitespace normalization for this project"). Adds when a real use case appears; speculative configurability is just surface to maintain.

### Language-aware passes (v1.5)

Indent-unit detection, lexical-equivalent normalization, per-language quote/semicolon/import-order canonicalization, AST-equivalent normalization, comment-aware modes. The substantive discussion is in [[Tether-Design-MVP]] §"Looking forward: language-aware extensions"; this section is the cross-reference.
