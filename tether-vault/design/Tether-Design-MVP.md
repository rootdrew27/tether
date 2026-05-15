---
title: Tether design (MVP)
tags:
  - design
  - mvp
type: design
status: active
---

This document describes what tether is, the architectural decision to build it as a layer on top of git, and how that shape supports its primary use cases. It is conceptual; specific JSON schemas, CLI surfaces, and implementation details are intentionally omitted and live in companion documents and the source.

---

## What tether is

> A typed-relationship annotation layer over content, built on top of git.

A *tether* is a typed, directional (or bidirectional) link between two pieces of content in a project — most commonly between a documentation file and a code file, or between a test and the code it exercises. Tethers are first-class records: they have IDs, types, creation timestamps, and most importantly, **fingerprints of the content they linked at the moment they were created**.

The defining question tether answers is not "what files exist" or "what changed" — git answers those. The question tether answers is:

> Is this intentional relationship still aligned with reality?

When a developer says "this doc describes that code," tether records the assertion *and* the content of both files at that moment. Later, anyone (a human, a coding agent, a CI check) can ask whether the relationship still holds — whether the doc and code have moved together, moved apart, or drifted in inconsistent directions.

---

## The core insight: relationships and content are orthogonal

Two axes that tether keeps separate:

1. **Content axis.** What bytes exist in the project, how they have evolved, who edited them, when. This is git's domain. Git has a deeply considered answer: a content-addressable object store, immutable commits, branches, merges, rename detection, distributed sync.

2. **Relationship axis.** Which pieces of content are intentionally related, what kind of relationship, and whether the relationship is still aligned. Git is silent on this axis. Tether exists for this purpose.

Trying to build tether *as a replacement for git* would mean reimplementing the content axis just to host the relationship axis. Trying to build tether *without referencing git* would mean recording relationships against ephemeral pointers (paths) rather than stable identities (hashes). Both fail.

The right shape — and the one this project commits to — is layered:

```
+---------------------------------------------------+
|  tether: typed relationships, drift detection     |
|  (annotations referencing content versions)       |
+---------------------------------------------------+
|  git: content storage, history, sync, renames     |
+---------------------------------------------------+
|  filesystem                                       |
+---------------------------------------------------+
```

Tether records the *meaning* of relationships. Git owns the *bytes* those relationships point at. Each layer does what it is good at; neither duplicates the other.

---

## What a tether records

Two artifacts are *tethered* when a tether record names them as its two sides. `tether add` is the operation that creates a tether between two artifacts; running it is what causes those artifacts to become tethered. "Tethered" is therefore not a property an artifact carries on its own — it is derived from the existence of a tether record.

A tether is conceptually a small record:

- **Two artifacts**, each identifying content by *path* and *locator*. The locator says which part of the file the tether refers to: the whole file, a contiguous line range, a section, a function, an explicit marker range. Whole-file is the trivial case of "all of this file"; sub-file locator types extend the same model with finer-grained selectors.
- **A typed relationship** drawn from a closed vocabulary: `describes`, `tests`, `references`, `related`. The set is intentionally small; relationship nuance lives in the description field rather than in proliferating type names. Directional types read as src-has-relation-to-dst; the symmetric type (`related`) reads as undirected. `describes` and `tests` are strictly unidirectional and may not be flipped to bidirectional; `references` defaults to unidirectional but may be marked bidirectional; `related` defaults to bidirectional.
- **An optional description** — free-form prose, authored by a human or a model, that elaborates *why* the relationship exists or captures nuance the type alone can't (for example: "this function implements step 3 of the algorithm in §2 of the spec; the loop bounds derive from the proof in §2.1"). Descriptions can be as terse or as verbose as the relationship warrants. Types are coarse-grained classifiers; descriptions carry the rich, project-specific semantics that make a tether legible to a future reader or agent — and let an LLM author a tether whose meaning a downstream model can recover without re-deriving it from the artifacts. Always optional; tethers without descriptions are first-class.
- **Content fingerprints** — each artifact carries a fingerprint, recorded at tether creation and re-recorded on refresh. With the MVP's `WholeFile`-only locator, a fingerprint is a single git blob OID: tether writes the file's bytes to git's object store via `git hash-object -w`, and the OID is stored in the tether record. This single value powers drift detection (compare the file's current OID to the stored one), supports inspection (`git cat-file -p <oid>` retrieves the fingerprinted bytes for diffing), and lets git's rename detection find renamed files (`git log --find-object=<oid>`). When sub-file locators ship, the fingerprint extends to a `{file_blob_oid, region_hash}` pair with no breaking schema change. Fingerprints are mandatory: every tether on disk carries one for each side, and `tether add` requires both files to exist on disk.

The shape is locator-aware from the start. **Tether MVP ships only the `WholeFile` locator** — every tether endpoint is the whole file at its recorded path. Additional locator types — `LineRange` (contiguous start–end line interval), markdown section paths, AST queries via tree-sitter, explicit region markers, language-server-driven symbol references — are additive: they extend the locator vocabulary without changing the rest of the record. Adding a new locator type is a strictly local extension. LineRange and sub-file locators are tracked in [[Future-Work]].

Tether records are also binary: each record names exactly two artifacts. Higher-arity relationships (one-to-many, many-to-many) are expressed as multiple binary tethers sharing an endpoint — this keeps the state machine binary and per-tether drift independent, which is more informative than a single aggregate "group drift" state.

---

## On-disk schema

Each tether is stored at `.tether/tethers/<uuid>.json`. The file is pretty-printed with sorted keys so diffs are reviewable and most git text-merges resolve cleanly.

```json
{
  "id": "0192abc1-23ef-7890-abcd-ef0123456789",
  "schema_version": 1,
  "src": {
    "path": "docs/auth.md",
    "fingerprint": "abc123def456..."
  },
  "dst": {
    "path": "src/auth.py",
    "fingerprint": "fedcba987654..."
  },
  "type": "describes",
  "bidirectional": false,
  "description": "Covers password reset and 2FA enrollment flows; impl uses argon2 for hashing.",
  "created_at": "2026-05-13T10:23:45Z",
  "refreshed_at": "2026-05-13T10:23:45Z"
}
```

**Field-by-field:**

- `id` — UUIDv7. Immutable. Sort order on disk equals creation order.
- `schema_version` — integer, currently `1`. Reserved for future migrations.
- `src` / `dst` — nested endpoint objects. Each carries `path` (project-relative POSIX string) and `fingerprint` (git blob OID as a hex string). When sub-file locators ship, a `locator` field is added inside each endpoint object — WholeFile = locator absent.
- `type` — one of `"related"`, `"describes"`, `"tests"`, `"references"`. Closed vocabulary enforced at validation time.
- `bidirectional` — boolean. Defaults vary by type (`related` defaults `true`; others default `false`). Operationally a display hint — drift detection ignores it.
- `description` — free-form prose or `null`. Set on create, mutable via `tether update --description`.
- `created_at`, `refreshed_at` — UTC ISO-8601 timestamps. `created_at` is immutable; `refreshed_at` updates only on `tether refresh`. No generic `updated_at` — git's commit log records non-fingerprint edits.

**Validation invariants** (enforced on construction and on read):

- `id` is a valid UUIDv7.
- `type` is in the closed vocabulary.
- If `type ∈ {"describes", "tests"}`, then `bidirectional` is `false`.
- `src.path != dst.path` — no self-tethers.
- Both `src.path` / `src.fingerprint` and `dst.path` / `dst.fingerprint` are non-null.
- `created_at <= refreshed_at`.

Validation runs both at `tether add`-time and on every read from disk. A record that fails validation is skipped with a corruption notice in `tether status` output — the rest of the project's tethers still load and report normally. Direct hand-edits to JSON files that break invariants are caught on the next access.

---

## How tether is built on top of git

Three concrete couplings to git:

**1. Content addressing via git blob hashes.**
When a tether is created or refreshed, tether computes the git blob OID of each *tethered file's* content (the doc, the code — what the artifact points at) and writes those bytes into git's object store via git's standard plumbing. The OID is recorded as the file blob OID inside the artifact's fingerprint; the bytes live in `.git/objects/` alongside everything else git tracks, so the content the tether was made against can be retrieved later for inspection. Tether records themselves are ordinary files in the working tree and are committed to git the normal way — they are not specially written into the object store, only the *content they reference*. Fingerprinted bytes are preserved indefinitely once reachable from a commit, and for at least git's default grace period (two weeks) even if they remain unreachable. For long-lived workflows that fingerprint against uncommitted content, tether can later pin fingerprints with refs to bypass garbage collection entirely; that extension is additive and not part of v1.

**2. Diff generation, move and rename detection, and history through git's plumbing.**
Tether borrows git's read APIs for everything beyond storage. *Diff generation* between fingerprinted bytes and current content — the core textual output of drift inspection — is `git diff` against an OID. Git already produces clean unified diffs, handles encodings and binary files, and respects gitattributes; tether asks for a diff and ships it. *In-file move detection* (`git diff --color-moved=zebra`) highlights blocks that have been relocated within a file, so when a region's locator no longer matches its original lines but the same content appears elsewhere in the file, the move is visible directly in the diff the agent already reads. *File rename detection* (`git diff -M`, `git log --follow`) answers "did this file move" more reliably than any filesystem scan. *Blob history* (`git log --find-object=<oid>`) finds which commits introduced or removed a specific blob; this is how tether's status report locates a renamed file when the recorded path no longer exists. In each case, tether is a client of git's existing capabilities — it does not implement its own rename detection, similarity search, or move heuristics.

**3. Tether's own state lives inside the git working tree.**
Tether records are JSON files under `.tether/tethers/`. They are committed alongside code. Tethers branch, merge, time-travel, and synchronize with the codebase as a single unit — because they are *part of* the codebase, not a sidecar to it.

### Git is a hard requirement

Replacing git would force tether to reimplement: content hashing, packing and garbage collection, branching, merging, rename detection, multi-machine synchronization, history. None of these are tether's contribution; all of them are git's. Tether therefore *requires* a git repository to operate: `tether init` refuses to initialize outside one, with a clear error pointing the user at `git init`.

This is a deliberate architectural commitment, not a convenience. Maintaining a parallel non-git code path would tax every query, every mutation, and every test forever; the user-side cost of running `git init` once is trivial. The audience — engineers and LLM agents working on real software projects — lives in git effectively universally. Drawing the line at "tether is the relationship layer for git-versioned projects" lets the rest of the design simplify around a single, dependable substrate.

---

## How tether is version controlled by git

Everything that defines a tether's identity and history is a regular text file in the working tree:

- `.tether/tethers/<id>.json` — one file per tether, pretty-printed JSON, sorted keys. The canonical record of a relationship.

This is the only on-disk shape MVP writes. Two siblings are reserved for later, each arriving with its first consumer:

- `.tether/config.json` — project-level configuration (e.g., normalizer tabstop override). MVP uses fixed defaults; this file ships alongside per-project normalizer config in v1.5.
- `.tether/.gitignore` — gitignored derived state. MVP has none; this file ships alongside `tether reconcile`'s `snapshot.json`.

Both are tracked in [[Future-Work]].

This shape is deliberately unremarkable. Tether files are diffable, mergeable, and reviewable like any other text. Everything below falls out of putting them in git: branching and merging without interference (each tether has a globally unique UUIDv7, so parallel branches usually edit disjoint files); pull-request review on the same surface the team already uses for code; time travel via `git checkout`; provenance via `git blame` and `git log`; distribution alongside content with no separate sync step. The relationship layer rides every operation the team already performs on the content layer.

See [[Git-Integration]] for the per-mechanism elaboration.

### Merge conflicts

Tether records are diffable text; git's text merge handles most conflicts cleanly because sorted-key pretty-printed JSON keeps each field on its own line. The common cases:

- **Both branches modify different fields** (one updates `src.path`, the other edits `description`): clean merge, no conflict.
- **Both branches refresh the same tether against different content**: conflict on the `fingerprint` and `refreshed_at` lines. Manual resolution by picking the side whose OID matches the merged file's actual content.
- **Both branches edit the same `description`**: standard text conflict; manual resolution.
- **One refreshes, one deletes**: standard git modify-delete conflict.
- **Both delete the same tether**: clean (no conflict).

If a botched manual resolution leaves invalid JSON, tether's read-side validation catches it on next access. The MVP ships no custom merge driver — git's text merge is the contract. A tether-aware merge driver and an append-only-record model that sidesteps record-level conflicts entirely are tracked in [[Future-Work]].

---

## Common workflows

Two workflows, each illustrating a different axis of the design.

### Workflow 1: A solo developer keeping docs in sync with code

A developer is maintaining a personal project. They have written `docs/auth.md` describing the authentication flow and `src/auth.py` implementing it. They want to know — months later, after many edits — whether the doc still matches the code.

They tether the two:

> "These two belong together. The doc *describes* the code."

Tether records both files' current content as fingerprints. Time passes. The developer edits `src/auth.py` to add a new password parameter. They forget to update the doc.

Later, before another edit, they ask tether for status. Tether reports: *the code changed since the tether was created; the doc did not. The relationship is WEAKENED — the doc may be out of date.* The developer reads the diff, updates the doc, and refreshes the tether. The relationship is HEALTHY again.

### Workflow 2: A team reviewing tether changes in pull requests

A developer on a team adds a new module: `src/billing.py`. They write `docs/billing.md` to accompany it. As part of the same PR, they tether the two with type `describes`.

What the reviewer sees in the PR diff:
- New code file `src/billing.py`.
- New doc file `docs/billing.md`.
- New tether record `.tether/tethers/<uuid>.json` containing both artifacts, their content fingerprints, and the relationship type.

The reviewer can read the proposed relationship at a glance. They might comment "this should also be tethered to `tests/test_billing.py` as `tests` once we add the test file" — a review comment that is now natural, because the *relationship layer is part of the change under review*.

After merge, the tether is part of `main`. Anyone who later modifies the billing code or doc can ask tether whether the alignment is still intact. The reviewer's intent — that these three files form a cohesive unit — is recorded as data, not just as words in a PR description that no one will read again.

---

## How tether enables coding agents

Coding agents like Claude Code operate in turns: user message arrives, agent reads and edits files, agent finishes. Within a turn the agent is the cause of every change; across turns, control passes back to the user (and the world, including non-agent edits, may have moved on).

Three patterns make tether useful to agents, all by query rather than by subscription:

**Surface relationships at boundaries.** Hooks at session start and turn end query tether and inject the result as context the agent reads and acts on. Per-edit injection during a turn is deliberately not part of the design — once-per-turn coverage at boundaries is sufficient, much cheaper in context, and easier to make right.

**Detect drift from any source.** Tether's content fingerprints record what each artifact looked like at the moment the relationship was last explicitly asserted (created or refreshed). Any subsequent edit — by a teammate, a script, the user in another shell, or the agent itself in a previous turn — surfaces as drift. The agent doesn't need to know who edited; it sees the state and decides whether the relationship still holds.

**Refresh deliberately, not automatically.** When the agent has made a coherent change across a tether's artifacts, it explicitly re-fingerprints by running `tether refresh`. Refresh is a positive assertion that the artifacts are aligned at their current contents; it travels with the content changes through the same git commit and PR review. Tether does not auto-refresh on file touches — doing so would erase the drift signal that lets a partial change set ("code updated, doc forgotten") surface on the next query. A refresh against a BROKEN tether refuses, since alignment cannot be asserted for content that cannot be located.

**Structural changes are separate from alignment assertions.** Path updates (when a tethered file is renamed) go through `tether update --src-path` or `tether update --dst-path` — these change *where* a side points but do not touch fingerprints. Following a rename and asserting alignment is two commands: first `tether update --<side>-path <new>`, then `tether refresh` once the file's content reflects what the tether is meant to assert. This separation keeps the audit trail honest — a refresh in `git log` always corresponds to an explicit alignment assertion, never a side effect of moving a file. Bulk path rewrites across many tethers use `tether mv <old-path> <new-path>`, which is the same structural-only operation applied to every tether referencing the path.

### Boundaries

Two boundaries make the integration safe in practice.

**Tether records are mutated only through tether's commands.** Direct edits to `.tether/tethers/*.json` bypass schema validation and the audit trail; a hand-written record can claim alignment it doesn't actually represent. The integration enforces this mechanically — for Claude Code, via declarative deny rules in `.claude/settings.json` that block `Edit`, `Write`, `MultiEdit`, and `NotebookEdit` calls on paths under `.tether/tethers/`. Tether's read paths additionally validate every record at access time, so any direct edit that does sneak through (e.g., via Bash) fails loudly on the next operation.

**Refresh integrity is preserved by audit trail.** Every refresh writes new fingerprint values into the tether record, committed alongside the content changes it ratifies. `git log .tether/tethers/<id>.json` shows the lifecycle: when it was created, what it fingerprinted, when it was refreshed and against what content. A reviewer scanning a PR can correlate "fingerprint changed in this commit" with "files fingerprinted to that OID also changed in this commit" — and challenge any refresh that claims alignment without the corresponding content change.

The Claude Code integration spec — hook commands, output schemas, install flow, failure contract — lives in [[Claude-Code-Integration]]. Open items (verifications, deferred features, decisions to revisit) are tracked in [[Claude-Code-Integration-Open]].

---

## Equivalence and drift normalization

Drift detection asks "did the located region change?" The naive answer — compare current bytes to fingerprinted bytes — produces false positives on changes that don't matter: trailing-whitespace strips, line-ending switches, BOM additions. None of these alter what the region *says*; they only alter how it's encoded. A tether that flips to DRIFTED on every formatter pass is a tether that gets ignored.

Tether resolves this with a **comparison-time normalizer**. Fingerprints stay raw — the file blob OID and region hash record the actual on-disk bytes at fingerprint time, so nothing about the on-disk record changes. When raw region hashes disagree, tether fetches the fingerprinted bytes from git, runs both sides through a fixed normalization pipeline (line endings, trailing whitespace, BOM, leading-tab expansion), and rescues the artifact to HEALTHY if the normalized hashes match. The raw diff is still surfaced — only the state value is rescued — so the drift signal is preserved.

Two consequences worth naming. First, **normalizer changes are forward-compatible**: when a future version adds an indent-unit detector or a per-language equivalence rule, every existing tether immediately benefits without any fingerprint migration. Second, **the audit trail stays honest**: `git log` on the tether record shows the actual fingerprinted OIDs, not normalized hashes; what the asserter committed to is exactly the bytes that were on disk at refresh time.

The full pipeline, configuration, and v1's deliberate non-goals (indent-width changes, internal whitespace) are specified in [[Normalization]].

---

## Looking forward: language-aware extensions

Tether v1's locators (`WholeFile`, `LineRange`) and its drift normalizer are language-agnostic. They cover a large fraction of realistic cases — tether a doc to a file, tether a doc section to a code range, ignore formatter-induced whitespace churn — well enough that v1 ships without per-language machinery. v2 is where parsers earn their place: not as a precondition for tether to work, but as a way to sharpen what counts as a relationship and what counts as drift.

### AST-aware locators

The natural v2 direction is **AST-aware locators** that understand source code as syntax rather than as bytes. The state of the art is well-mapped: tools like [GumTree](https://github.com/GumTreeDiff/gumtree) (the canonical AST-diff algorithm), [difftastic](https://github.com/Wilfred/difftastic) (Dijkstra over tree-sitter parse trees), [RefactoringMiner](https://github.com/tsantalis/RefactoringMiner) (Java refactoring detection at 99% precision), and [Mnemosyne](https://github.com/alessandrobrunoh/mnemosyne) (tree-sitter + structural hashes + content-addressable storage) all converge on the same pattern: parse with a language-aware grammar, identify named entities, match by structural fingerprint or by name. The tradeoff is a parser dependency per supported language in exchange for tethers that survive function renames, refactors, and intra-file moves without needing a manual `tether update`. Because tree-sitter does not provide stable node identifiers across edits, the matching is always heuristic — but the heuristics are well-understood and battle-tested.

Other locator types worth eventual consideration: markdown section paths (heading hierarchies for prose docs), explicit region markers (special comments embedded in source files for unambiguous tracking), and language-server-driven symbol references. Each is a local addition to the locator vocabulary; the data model already supports them, and the implementation work is per-locator with no breaking changes.

### Language-aware drift normalization

The v1 normalizer catches encoding-level changes safely without parsing. A v1.5 layer of language-aware rules can extend it to changes that are equivalent only modulo syntax:

- **Indent-unit detection.** Detect the file's modal leading-WS unit (2-space, 4-space, tab) and reduce leading whitespace to indent levels, so 2-space ↔ 4-space reformats stop drifting.
- **Lexical-equivalent normalization.** Once a lexer can identify string literals, internal whitespace can be safely collapsed outside them, catching `a+b` ↔ `a + b` and similar formatter outputs.
- **Per-language equivalence rules.** Quote-style normalization (`'foo'` ↔ `"foo"` where semantically identical), trailing-comma normalization, ASI-equivalent semicolon handling.
- **AST-equivalent normalization.** Import reordering and sorted-key containers, where AST-equivalent forms hash to the same canonical representation.
- **Comment-aware modes.** An opt-in per-tether mode that strips comments before hashing, for tethers that point at code and want to ignore docstring touch-ups. The default stays as drifting on comment edits, since a tether *to* a comment block legitimately wants to track its content.

These all sit on the same parser substrate as AST-aware locators and can be staged incrementally. None require changes to the on-disk fingerprint format: every existing tether picks them up the moment they ship.

A broader set of deferred work — `LineRange` and other locator extensions, ref-pinning for fingerprint bytes, the `tether watch` and `tether reconcile` CLI commands, a custom git merge driver, and the event subscription model — is collected in [[Future-Work]].

---

## Design principles

- **Relationships and content are orthogonal.** Tether owns the first; git owns the second.
- **Paths are commentary; hashes are identity.** A tether's fingerprints record what content *was*, not where it lives.
- **The tether graph is part of the codebase.** It branches, merges, reviews, and time-travels as one unit with the code.
- **Drift is a property of relationships, not of files.** A file changing means nothing on its own; a *tethered* file changing relative to its fingerprint is the signal.
- **Tether reports structural state; consumers interpret the change.** Drift detection identifies what is structurally true (the locator resolves or doesn't; the normalized content matches the fingerprint or doesn't) and includes the textual diff between fingerprinted and current content. Semantic interpretation — rename versus refactor versus deletion — is the consumer's job, equipped with both the structural state and the diff. Tether does not classify *why* content changed.
- **Refresh is an assertion, not a side effect.** Fingerprints update only when an entity explicitly asserts alignment. No tool use, no file touch, no automated process re-fingerprints a tether. The assertion — recorded as a write to the tether record, committed alongside the content it ratifies — is the point.
- **Tethers carry fingerprints of real content.** Both artifacts must exist on disk when a tether is created; every tether on disk carries fingerprints for both. Speculative or aspirational tethers are not a category — relationship planning belongs in other tools.
- **Federate, do not reimplement.** Tether requires git and delegates content storage, history, synchronization, and rename detection to it.
