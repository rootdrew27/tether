---
title: Diction (MVP)
tags:
  - meta
  - glossary
  - mvp
type: meta
status: active
---

The canonical vocabulary for the **MVP** of tether. Terms below match what the code actually does today.

## Core concepts

| Term                    | Definition                                                                                                                                                                                                                          | Aliases to avoid                   |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| **Tether**              | A declaration of connection between two artifacts, with a content fingerprint at each artifact and a required description. Symmetric — neither end is privileged.                                                                   | Link, connection, edge, relation   |
| **Artifact**            | One of the two ends of a tether: a path (project-relative POSIX) plus a fingerprint. MVP refers to the whole file at the path.                                                                                                      | Knot, endpoint, side, target, node |
| **Fingerprint**         | The git blob OID of the artifact file's content, recorded at tether creation and re-recorded on refresh.                                                                                                                            | Anchor, snapshot, pin              |
| **Description**         | A required free-form sentence (or longer) that captures *why* the relationship exists. Carries the project-specific semantics of the tether; the data model itself is intentionally untyped.                                        | Note, label, comment               |
| **Refresh**             | The act of re-fingerprinting; framed as a positive assertion of alignment that travels with the content changes it ratifies.                                                                                                        | Auto-update, sync                  |
| **Drift**               | The condition where current content diverges from what was fingerprinted. The umbrella phenomenon, not a status value.                                                                                                              | Drift event                        |
| **Drift normalization** | Comparison-time pipeline applied to both sides when raw fingerprints disagree. Catches encoding-level changes (line endings, BOM, trailing whitespace, leading-tab expansion at tabstop 8) without altering the stored fingerprint. | Canonicalization, whitespace fix   |
| **Normalizer**          | The implementation of drift normalization. Language-agnostic in MVP.                                                                                                                                                                | Canonicalizer                      |
| **Tether record**       | The on-disk JSON file under `.tether/tethers/<id>.json` that is the canonical representation of a tether. Pretty-printed with sorted keys.                                                                                          | Tether file, link record           |
| **Tether graph**        | The full set of tethers in a project, considered as a graph over artifacts.                                                                                                                                                         | Link graph, network                |

## Tether state

| Term         | Definition                                                                                                                                      | Aliases to avoid             |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| **HEALTHY**  | The artifact's current blob OID matches the fingerprint (or normalization rescues equivalence). For a whole tether, both artifacts are HEALTHY. | FRESH, OK, valid, clean      |
| **DRIFTED**  | The file exists at the recorded path but its content's blob OID no longer matches the fingerprint (and normalization does not rescue).          | Changed, modified, dirty     |
| **BROKEN**   | The file is not present at the recorded path; the artifact cannot be located. Any BROKEN artifact makes the aggregate BROKEN.                   | Missing, invalid, gone       |

The aggregate state is derived from per-artifact states: both HEALTHY → HEALTHY; one HEALTHY + one DRIFTED → DRIFTED; both DRIFTED → DRIFTED; any BROKEN → BROKEN.

## Operations

| Term                        | Definition                                                                                                                                                                                                                               | Aliases to avoid           |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------- |
| **tether init**             | Initialize tether state in a project (`.tether/` directory). Refuses outside a git repository.                                                                                                                                           | Setup, bootstrap           |
| **tether init claude-code** | Install the Claude Code integration: hooks, permissions, the agent fragment.                                                                                                                                                             | Install                    |
| **tether add**              | Create a new tether between two existing on-disk artifacts, recording fingerprints for both and a required description.                                                                                                                  | Create, link, connect      |
| **tether status**           | Report the current state of tethers (per-artifact and aggregate). With a tether ID, includes a unified diff for any DRIFTED or normalization-rescued side.                                                                               | Check, query, inspect      |
| **tether show**             | List every tether with its description, regardless of state. Structural only — reads records from disk without computing drift or touching git; output is paged through `$PAGER` on a TTY. Takes no tether ID; it lists the whole graph. | List, browse, dump, ls     |
| **tether refresh**          | Re-fingerprint both artifacts of a tether, asserting they are aligned at their current contents. Refuses on a BROKEN tether.                                                                                                             | Update fingerprint, re-pin |
| **tether update**           | Modify a tether's metadata (path, description) without re-fingerprinting.                                                                                                                                                                | Edit, retarget             |
| **tether mv**               | Bulk path rewrite: rewrite every artifact pointing at OLD_PATH to NEW_PATH. Structural only; no alignment assertion.                                                                                                                     | Bulk rename                |
| **tether rm**               | Delete a tether record.                                                                                                                                                                                                                  | Remove, delete, unlink     |
| **tether refs**             | List tethers referencing a path (where the artifact's `a.path` or `b.path` matches),                                                                                                                                                     |                            |

## Actors

| Term              | Definition                                                                                                  | Aliases to avoid          |
| ----------------- | ----------------------------------------------------------------------------------------------------------- | ------------------------- |
| **User**          | A human developer who creates, refreshes, or reviews tethers via the CLI.                                    | Developer, author         |
| **Coding agent**  | An autonomous LLM-driven tool (e.g. Claude Code) that queries tether and edits content within turns.        | Agent, LLM, bot           |
| **Reviewer**      | A teammate inspecting tethers as part of a pull request review.                                              | Approver                  |
| **Asserter**      | The entity (user or agent) running `tether refresh`, on record as claiming alignment.                        | Refresher                 |

## Git integration

| Term                  | Definition                                                                                                                                                                               | Aliases to avoid         |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------ |
| **Git blob OID**      | A SHA hash naming a git blob object; the content-addressed identity of file bytes in `.git/objects/`.                                                                                    | Git hash, object ID      |
| **Fingerprint write** | The operation that writes artifact bytes into git's object store via `git hash-object -w` so the OID is retrievable.                                                                     | Anchor write, object pin |
| **Audit trail**       | The lifecycle of a tether visible via `git log .tether/tethers/<id>.json`: when created, fingerprinted, refreshed.                                                                       | History, log             |
| **Rename detection**  | Identifying that a file has been moved to a new path. Tether uses git internals (see `git diff-index) to identify renamed files, tracking files even when they are renamed *and* edited. | Path detection           |

## Project boundaries

| Term                  | Definition                                                                                             | Aliases to avoid     |
| --------------------- | ------------------------------------------------------------------------------------------------------ | -------------------- |
| **Content axis**      | What bytes exist in the project and how they evolve. Git's domain.                                     | Storage layer        |
| **Relationship axis** | Which pieces of content are intentionally related and whether they are still aligned. Tether's domain. | Link layer           |
| **Project root**      | The directory containing a `.tether/` folder; tether commands walk upward from cwd to find it.         | Workspace, repo root |
| **State directory**   | The `.tether/` directory holding tether records and (when installed) the Claude Code agent fragment.   | Tether dir           |

## Relationships

- A **Tether** has exactly two **Artifacts** named `a` and `b`. The labels carry stable ordering (whichever was passed to `tether add` first becomes `a`), not direction; neither end is privileged.
- Each **Artifact** has a `path` and a single **Fingerprint** (git blob OID).
- A **Tether** carries a required **Description**. The data model has no relationship type and no directionality flag; the description is where the nuance lives.
- **Refresh** updates both artifacts' fingerprints atomically; it is never partial.
- **Refresh** refuses on a **BROKEN** tether (alignment cannot be asserted for content that cannot be located).
- A **Tether record** is one file per tether under `.tether/tethers/`, named by UUIDv7 and committed alongside content.
- The aggregate state of a **Tether** is the most severe of its per-artifact states (HEALTHY < DRIFTED < BROKEN).
## Flagged ambiguities

- **"Tether" as system vs. unit.** The word names both the project ("tether") and an individual link ("a tether"). Context disambiguates in practice; prefer "the tether system" or "tether (the tool)" when ambiguity matters in user-facing prose.
- **"Fingerprint" as noun vs. verb.** "A fingerprint" is the recorded git blob OID; "to fingerprint" is the act of recording it. Recommend keeping the noun as primary and using "re-fingerprint" / "record a fingerprint" for the verb forms.
- **"Drift" vs. "DRIFTED".** "Drift" is the umbrella phenomenon (content diverging from fingerprint); **DRIFTED** is a specific state value (per-artifact or aggregate). When discussing state, use the all-caps state name; when discussing the phenomenon, use lowercase "drift".
- **"Artifact" vs. "tethered file".** The README and casual conversation say "tethered file"; technical writing should use **Artifact**. Acceptable as shorthand since MVP's artifacts are always whole files.
- **`a` and `b` are not "source" and "destination".** They are stable labels for the two ends of a symmetric relationship — the order in which the user passed them to `tether add`. Avoid "source"/"destination" or "src"/"dst" phrasing in prose; it implies an asymmetry the data model does not carry.
- **"Refresh" as command vs. concept.** `tether refresh` is the command; **Refresh** (the concept) is the deliberate assertion of alignment. The concept is the more important framing — refresh is an *assertion*, not a side effect of editing.
- **"Update" vs. "refresh".** `tether update` changes path or description without asserting alignment; `tether refresh` asserts alignment by re-fingerprinting. These are distinct operations and should not be conflated — update follows a move, refresh ratifies a coherent change.
