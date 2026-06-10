## Core concepts

| Term                  | Definition                                                                                                          | Aliases to avoid                       |
| --------------------- | ------------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| **Tether**            | A typed, directional or bidirectional link between two pieces of content, with content fingerprints at both artifacts. | Link, connection, edge, relation       |
| **Artifact**          | One of the two sides of a tether: a path plus a locator identifying which part of the file the tether refers to.   | Knot, endpoint, side, target, node, anchor point |
| **Locator**           | The selector that identifies which part of a file an artifact refers to (e.g. `WholeFile`, `LineRange`).            | Selector, range, span                  |
| **Fingerprint**       | The per-artifact record containing two values — a file blob OID and a region hash — recorded at tether creation or refresh that pin the artifact to specific content. | Anchor, snapshot, pin                  |
| **File blob OID**     | The git object ID of the whole artifact file's content at fingerprint time. Supports rename detection through git.  | File hash, content hash (of file)      |
| **Region hash**       | The hash of just the located region's bytes at fingerprint time. Powers drift detection on the located region.      | Chunk hash, range hash, section hash   |
| **Relationship type** | A free-form, project-defined string describing the kind of link (e.g. `describes`, `tests`, `implements`).          | Tag, label, kind, category             |
| **Drift**             | The condition where current content diverges from what was fingerprinted. The umbrella phenomenon, not a status value. | Drift event                            |
| **Drift normalization** | Comparison-time pipeline applied to both sides of a region equality check. Catches encoding-level changes (line endings, trailing whitespace, BOM, leading-tab expansion) without altering the stored fingerprint. Runs only when raw region hashes disagree. | Canonicalization, whitespace fix       |
| **Normalizer**        | The implementation of drift normalization. Language-agnostic in v1; future tiers add language-aware rules.            | Canonicalizer                          |
| **Tether record**     | The on-disk JSON file under `.tether/tethers/<id>.json` that is the canonical representation of a tether.           | Tether file, link record               |
| **Tether graph**      | The full set of tethers in a project, considered as a graph over content artifacts.                                 | Link graph, network                    |

## Locator types

| Term                   | Definition                                                                                                       | Aliases to avoid     |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------- | -------------------- |
| **WholeFile**          | Locator covering all of an artifact file. The trivial case.                                                       | Full file, all       |
| **LineRange**          | Locator covering a contiguous start-end line interval of an artifact file.                                         | Range, line span     |
| **AST-aware locator**  | Future locator class that identifies regions by syntax tree structure rather than by lines or bytes (v2 direction). | Syntax locator       |

## Tether state

| Term         | Definition                                                                                                         | Aliases to avoid                |
| ------------ | ------------------------------------------------------------------------------------------------------------------ | ------------------------------- |
| **HEALTHY**  | The artifact (or whole tether) is aligned with its fingerprint; located region matches recorded region hash.       | FRESH, OK, valid, clean         |
| **DRIFTED**  | The locator resolves but the located content's hash no longer matches the fingerprint; the content has changed.    | Changed, modified, dirty        |
| **BROKEN**   | The locator cannot resolve at the recorded path or position; the file or region has moved or been removed.         | Missing, invalid, gone          |

## Operations

| Term                  | Definition                                                                                                         | Aliases to avoid           |
| --------------------- | ------------------------------------------------------------------------------------------------------------------ | -------------------------- |
| **tether init**       | Initialize tether state in a project. Refuses outside a git repository.                                             | Setup, bootstrap           |
| **tether add**        | Create a new tether between two existing on-disk artifacts, recording fingerprints for both.                        | Create, link, connect      |
| **tether status**     | Report the current state of tethers (per-artifact and aggregate), including diffs of drifted content.               | Check, query, inspect      |
| **tether refresh**    | Deliberately re-fingerprint both artifacts of a tether, asserting that they are aligned at their current contents.  | Update fingerprint, re-pin |
| **tether update**     | Modify a tether's path or locator (e.g. follow a renamed file) without asserting content alignment.                  | Edit, retarget             |
| **tether rm**         | Delete a tether record.                                                                                            | Remove, delete, unlink     |
| **Refresh**           | The act of re-fingerprinting; framed as a positive assertion of alignment that travels with the content changes it ratifies. | Auto-update, sync          |
| **Reconcile**         | Offline rename detection that compares a content-hash snapshot at `.tether/snapshot.json` to current disk state.    | Sync, repair               |
| **tether coverage**   | Report what fraction of git-tracked files participate in at least one tether; flags list the (un)tethered files. Structural-only. | Stats, audit               |
| **Coverage**          | The fraction of tracked files referenced by ≥1 tether. A progress signal for onboarding, not a target — many files have no drift-sensitive partner. | Completeness, score        |
| **Onboard**           | Create the initial tether graph for an existing project: survey, judge candidate relationships, `tether add` with quality descriptions. Implemented as a coding-agent skill (`/tether-onboard`), not a CLI command. Distinct from **Reconcile** (repairing existing tethers). | Bootstrap, import, scan    |

## Actors

| Term              | Definition                                                                                                  | Aliases to avoid          |
| ----------------- | ----------------------------------------------------------------------------------------------------------- | ------------------------- |
| **User**          | A human developer who creates, refreshes, or reviews tethers via the CLI or API.                             | Developer, author         |
| **Coding agent**  | An autonomous LLM-driven tool (e.g. Claude Code) that queries tether and edits content within turns.        | Agent, LLM, bot           |
| **Reviewer**      | A teammate inspecting tethers as part of a pull request review.                                              | Approver                  |
| **Asserter**      | The entity (user or agent) running `tether refresh`, on record as claiming alignment.                        | Refresher                 |

## Git integration

| Term                       | Definition                                                                                                       | Aliases to avoid              |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| **Git blob OID**           | A SHA hash naming a git blob object; the content-addressed identity of file bytes in `.git/objects/`.            | Git hash, object ID            |
| **Fingerprint write**      | The operation that writes artifact bytes into git's object store via `git hash-object -w` so the OID is retrievable. | Anchor write, object pin      |
| **Pinned fingerprint**     | A future extension where fingerprinted bytes are kept reachable via dedicated refs to bypass git garbage collection. | Pinned anchor, ref-pinned     |
| **Audit trail**            | The lifecycle of a tether visible via `git log .tether/tethers/<id>.json`: when created, fingerprinted, refreshed. | History, log                  |
| **Move detection**         | Identifying that a region within a file has been relocated, surfaced via `git diff --color-moved=zebra`.          | Block move                    |
| **Rename detection**       | Identifying that a file has been moved to a new path, via `git diff -M`, `git log --follow`, or `git log --find-object`. | Path detection                |

## Project boundaries

| Term                  | Definition                                                                                                  | Aliases to avoid          |
| --------------------- | ----------------------------------------------------------------------------------------------------------- | ------------------------- |
| **Content axis**      | What bytes exist in the project and how they evolve. Git's domain.                                            | Storage layer             |
| **Relationship axis** | Which pieces of content are intentionally related and whether they are still aligned. Tether's domain.         | Link layer                |
| **Project root**      | The directory containing a `.tether/` folder; tether commands walk upward from cwd to find it.                 | Workspace, repo root      |
| **State directory**   | The `.tether/` directory holding tether records, config, and gitignored derived state.                        | Tether dir                |

## Relationships

- A **Tether** has exactly two **Artifacts**.
- Each **Artifact** has exactly one **Locator** and exactly two fingerprint values: a **File blob OID** and a **Region hash**.
- A **Tether** carries one **Relationship type** and a directionality flag (uni- or bidirectional).
- **Refresh** updates both artifacts' fingerprints atomically; it is never partial.
- **Refresh** refuses on a **BROKEN** tether (alignment cannot be asserted for content that cannot be located).
- A **Tether record** is one file per tether under `.tether/tethers/`, named by UUIDv7 and committed alongside content.
- The aggregate state of a **Tether** is the most severe of its per-artifact states (HEALTHY < DRIFTED < BROKEN); any BROKEN artifact yields BROKEN.

## Example dialogue

> **Dev:** "I added a `describes` **Tether** from `docs/auth.md` to `src/auth.py`. After my edits this morning, what's the **Tether status**?"
> **Tether expert:** "The doc **Artifact** is **HEALTHY**, but the code **Artifact** is **DRIFTED** -- its **Region hash** no longer matches the **Fingerprint**. Aggregate state is **DRIFTED**."
> **Dev:** "Got it -- so I need to update the doc and then `tether refresh`?"
> **Tether expert:** "Right. **Refresh** re-fingerprints both **Artifacts** together; it's the assertion that they're now aligned. Don't refresh until you've actually updated the doc, or you'll erase the drift signal."
> **Dev:** "What if I'd renamed `auth.py` to `authentication.py` instead of just editing it?"
> **Tether expert:** "Then the **Locator** wouldn't resolve at the recorded path -- the code **Artifact** would be **BROKEN**. Tether queries `git log --find-object` against the **File blob OID** to suggest the new path; you'd run `tether update --b-path authentication.py` to follow it."

## Flagged ambiguities

- **"Tether" as system vs. unit.** The word names both the project ("tether") and an individual link ("a tether"). Context disambiguates in practice; prefer "the tether system" or "tether (the tool)" when ambiguity matters in user-facing prose.
- **"Fingerprint" as noun vs. verb.** "A fingerprint" is the recorded `(file blob OID, region hash)` pair; "to fingerprint" is the act of recording it. The doc uses both. Recommend keeping the noun as primary and using "re-fingerprint" / "record a fingerprint" for the verb forms.
- **"Drift" vs. "DRIFTED".** "Drift" is the umbrella phenomenon (content diverging from fingerprint); **DRIFTED** is a specific state value. When discussing state, use the all-caps state name; when discussing the phenomenon, use lowercase "drift".
- **"Artifact" vs. "tethered file".** The README and casual conversation say "tethered file"; technical writing should use **Artifact**. An **Artifact** is more precise (path + locator), since a single file can host multiple artifacts with different locators. "Tethered file" is acceptable shorthand only when the locator is `WholeFile`.
- **"Refresh" as command vs. concept.** `tether refresh` is the command; **Refresh** (the concept) is the deliberate assertion of alignment. The concept is the more important framing -- refresh is an *assertion*, not a side effect of editing.
- **"Chunk" vs. "region".** The README uses "chunk" for sub-file selections; the design doc uses "region". Recommend **region** as canonical, since "chunk" suggests fixed-size partitioning (as in chunked encoding) which isn't the model here.
- **"Snapshot" overloading.** Used in the codebase for `.tether/snapshot.json` (reconcile's content-hash index) and informally for "what was fingerprinted". Recommend reserving **snapshot** for the reconcile artifact and using **fingerprint** / **fingerprinted content** for what the tether records.
- **"Update" vs. "refresh".** `tether update` changes path or locator without asserting alignment; `tether refresh` asserts alignment by re-fingerprinting. These are distinct operations and should not be conflated -- update follows a move, refresh ratifies a coherent change.
