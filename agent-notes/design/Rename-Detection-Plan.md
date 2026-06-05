This document is the implementation plan for synthetic-diff rename detection. The mechanism and its empirical validation live in [Rename-Detection-Research](../research/Rename-Detection-Research.md); the edge-case catalog is in [Rename-Detection-Edge-Cases](../research/Rename-Detection-Edge-Cases.md). This plan records the design decisions taken on top of that research and the concrete code changes they imply. Conceptual framing for how tether rides git's read APIs is in [Git-Integration](Git-Integration.md) and [Tether-Design-MVP](Tether-Design-MVP.md) §"How tether is built on top of git".

## Goal and shape

Rename detection is **notify-only**. When an [Artifact](../../tether-vault/DICTION.md) is BROKEN — its file is not present at the recorded path — tether reports the BROKEN state as it does today and *attaches* a best-match rename candidate with a similarity score when one can be found. Resolution stays the deliberate `tether update --a-path/--b-path <new>` → `tether refresh` once aligned. Nothing here auto-follows a rename, mutates a record, or asserts alignment.

The candidate-finder is replaced wholesale: git's `diffcore-rename` similarity engine, fed a synthetic "before" tree, supersedes the current exact-OID `git log --find-object` scan (`find_paths_for_blob` in `tether/git.py`). The synthetic diff subsumes exact-OID matching for every in-working-tree path — an exact match surfaces as `R100` — and additionally follows a file that was renamed *and* edited.

## Decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Detection direction | One-directional: from a BROKEN artifact's known `old_path` + Fingerprint, find where that content went. | The reverse case — an agent Reads a file at a path no tether records, and tether announces "this is the moved target of tether X" — needs a content-scan of every BROKEN Fingerprint on each Read, since `find_by_path` is path-keyed. Deferred. |
| 2 | Relation to `find_paths_for_blob` | **Replaced.** Synthetic-diff is the sole candidate source in the status path. | `find-object` only returns paths where the blob is in committed history (hence reachable, hence not GC-eligible) — exactly the case the synthetic diff reports as `R100`. Its only unique output is non-actionable cross-branch / deleted-history paths, which would dilute the "paths you can switch to" contract. |
| 3 | Candidate cardinality | Single best match per BROKEN artifact. `rename_candidates` stays a `tuple` (≤1 element). | `git diff-index -M` emits exactly one best-match target per source deletion; there is no native ranked list. Surfacing "N near-matches" needs a separate scoring pass — deferred. The tuple shape keeps that future open. |
| 4 | State machine | Artifact stays **BROKEN**; the candidate is attached as supplementary info. | A renamed file genuinely is not at its recorded path, so it satisfies BROKEN by definition. A new `MOVED` state would ripple through `AggregateState`, `SEVERITY`, `STATE_ORDER`, `aggregate()`, and every surfacing site for no behavioral gain under notify-only. |
| 5 | Candidate model | `RenameCandidate(path: str, similarity: int)`, score non-nullable (0–100, git's R-score). | With the scoreless `find-object` source gone, every candidate carries a real similarity score. |
| 6 | Similarity threshold | `-M30` (30%), as a hardcoded module constant. No CLI flag. | Lower than git's 50% default so heavier edits still surface rather than dead-ending as "BROKEN, no candidate." Cheap to be wrong under notify-only. A constant keeps it a one-line change; per-invocation config is a documented future knob. |
| 7 | Batching | One T_old holding **every** BROKEN `{old_path → Fingerprint}` entry, one seeded T_new, one `git diff-index` per status run. | `diffcore-rename` pairs all deletions against all current additions in a single similarity pass, so cost is one git diff regardless of tether count. |
| 8 | Claude Code surfacing | Candidates ride as the `rename_candidates` array on each artifact in the `RefsReport` JSON. | `tether refs` JSON already carries the field; surfacing in the hook payload is the same struct. Tuple shape extends cleanly if N candidates ever land. |
| 9 | Tests | Minimal: migrate the breaking test + `find_renames` smoke tests; full matrix deferred. | Covers the model/orchestration change and the core paths; the broader matrix in *Open* stays a known gap. |

## Resolutions applied (post-review)

A review pass before implementation resolved the following on top of the decisions above:

- **PreRead stays candidate-free.** The per-Read `PreToolUse` hook is *not* migrated to the
  batched checker — a Read never triggers the working-tree scan. Candidates surface in
  `tether status` / SessionStart / Stop / `tether refs`. The `rename_candidates` field
  (decision 8) is therefore populated by `tether refs <path>` JSON, never by the per-Read
  injection (where it stays an empty array).
- **R100 exact-duplicate ambiguity deferred** → documented limitation (no `--raw` post-filter;
  the diff stays `--name-status`).
- **Hardening folded in:** the diff runs `git -c diff.renameLimit=0 -c core.quotePath=false
  diff-index -M30% --find-renames -z --name-status`; `find_renames` is keyed by
  `(old_path, fingerprint)` so same-path/different-fingerprint colliders attach correctly; a
  fresh/no-commit repo (no `.git/index`) falls back to an empty seeded index; any git failure
  degrades to a partial/empty mapping (never raises).
- **Tests: minimal.** The one breaking test was migrated to `check_all` + the `RenameCandidate`
  shape, plus `find_renames` smoke tests (edited-rename match, sub-threshold miss, missing-blob
  no-crash). The full matrix in *Open* stays deferred.

## Mechanism

The plumbing is the verified sequence from the research doc, generalized from one BROKEN entry to many. All steps run against throwaway index files via `GIT_INDEX_FILE`; the user's real index and working tree are never touched. Temp index paths must **not already exist** (a `mktemp`-created 0-byte file fails with `index file smaller than expected`); use a name-only path and clean up the matching `.lock`.

1. **Filter** the BROKEN `(old_path, fingerprint)` set to fingerprints whose blob is still in the object store (`git cat-file -e "$FP^{blob}"`). A rename + edit needs git to *read* the blob to score similarity; a GC'd uncommitted Fingerprint cannot be scored and yields no candidate.
2. **T_old** — one tree containing every surviving BROKEN entry, built with `git update-index --add --cacheinfo 100644,<FP>,<old_path>` then `git write-tree`. De-duplicate by path; on the rare same-path / different-Fingerprint collision, score those colliders in a separate pass.
3. **T_new** — seeded from the real index (`cp "$(git rev-parse --git-path index)" "$TI_NEW"` then `GIT_INDEX_FILE="$TI_NEW" git add -A`). The copy reuses git's stat cache (only modified files re-hash) and carries committed-but-clean files, so committed renames are covered.
4. **Diff** — `GIT_INDEX_FILE="$TI_NEW" git -c diff.renameLimit=0 -c core.quotePath=false diff-index -M30% --find-renames -z --name-status "$TREE_OLD"`. Every BROKEN `old_path` is a deletion; every current file is an addition; `diffcore-rename` pairs each deletion with its best match, emitting `R<score>\0<old_path>\0<new_path>` rows. `diff.renameLimit=0` makes detection independent of user gitconfig; `core.quotePath=false` keeps non-ASCII paths literal.
5. **Map** each row's `old_path` back to its BROKEN artifact(s) and attach the `(new_path, score)` candidate.

## Code changes

- **`tether/git.py`**
  - Add an `env` keyword to `run_git` so `GIT_INDEX_FILE` can be set per call.
  - New batch primitive `find_renames(broken: list[tuple[str, str]], root: Path) -> dict[tuple[str, str], tuple[str, int]]` mapping `(old_path, fingerprint) → (new_path, score)`. It performs the five-step mechanism above and manages temp index lifecycle (creation at non-existent paths, `.lock` cleanup). It returns raw tuples so `git.py` keeps no dependency on the domain structs.
  - `find_paths_for_blob` drops out of the status path. (The function may be removed once nothing references it.)

- **`tether/status.py`**
  - New `RenameCandidate(msgspec.Struct, frozen, kw_only)` with `path: str`, `similarity: int`.
  - `ArtifactCheck.rename_candidates` becomes `tuple[RenameCandidate, ...]`.
  - New orchestrator `check_all(tethers, project_root, tabstop=8) -> list[TetherCheck]`:
    1. Compute per-tether states with no rename work (existing `check_artifact` logic minus the `find_paths_for_blob` call).
    2. Collect every BROKEN `(path, fingerprint)`.
    3. If any, one `find_renames` call.
    4. Patch candidates back into the BROKEN `ArtifactCheck`s via `msgspec.structs.replace`.
  - Any git failure degrades to empty candidates — `tether status` must never crash on rename detection.

- **`tether/cli.py` / `tether/claude_code/hooks.py`** — replace the `[check_tether(t, root) for t in …]` comprehensions (status single + multi in `cli.py`, `_evaluate` in `hooks.py`) with `check_all`, so a single batched diff serves the whole run. Single-tether `tether status <id>` calls `check_all([t], root)`.

- **`tether/output.py`** — `ArtifactStatus.rename_candidates` carries the `RenameCandidate` struct; JSON emits `{ "path": …, "similarity": … }`.

- **`tether/render.py`**
  - `item_lines` and `_broken_block`: render the candidate as a best-match line with its score, e.g. `best match: \`new.py\` (R96)`.

## Documentation follow-ups

- Propose a diff to `tether-vault/DICTION.md`'s "Rename detection" entry — it currently names only the `find-object` query — for a human to apply (the vault is read-only for Claude).
- Update the [Tether-Design-MVP](Tether-Design-MVP.md) §"How tether is built on top of git" rename paragraph to describe the synthetic-diff mechanism.

## Known limitations

Carried forward from the research; documented, not fixed:

- **Sub-threshold rewrites.** A file edited past the 30% similarity floor degrades to add + delete and surfaces no candidate.
- **Decoy outscoring.** Single-best matching can surface a coincidentally-similar decoy over a heavily-edited true target.
- **R100 exact-duplicate ambiguity.** When several working-tree files share the BROKEN content, git reports an arbitrary one as the rename and the rest as silent additions; tether surfaces that single match and does not flag the ambiguity.
- **`.gitignore` respected.** `T_new` is built with `git add -A`, so a rename *into* a gitignored path is invisible (deliberate: keeps the candidate set small and excludes build trees).
- **Object-store side effect.** `git add -A` writes loose blobs for non-ignored untracked files into `.git/objects` (git-gc reclaims them); the real index, working tree, and refs are untouched.
- **`diff.renameLimit`.** Neutralized with `-c diff.renameLimit=0` so detection is independent of user gitconfig; the limit is on the rename *matrix* (≈ `renameLimit²` pairs), so only a very large BROKEN set against a very large tree could still degrade.
- **GC race.** An uncommitted Fingerprint blob that has been garbage-collected cannot be scored, so the rename + edit case yields no candidate (pre-filtered; no crash).

## Open

- **Tests.** Shipped minimal coverage (committed rename `R100` via `check_all`, edited-rename match, sub-threshold miss, missing-blob no-crash). Still deferred from the recommended core matrix: explicit uncommitted pure rename, multiple BROKEN artifacts in one run (batched-diff correctness), and non-invasiveness (real index and working tree untouched).
- **Threshold tuning** and **per-invocation config** — whether `-M30` is the right floor, and whether to expose a `--rename-threshold` flag.
- **Candidate-set size on large repos** — raise `diff.renameLimit` vs. fall back to a bounded set, trading committed-rename coverage for speed.
- **Reverse direction** — detecting that a file being Read *is* the moved target of some BROKEN tether (decision 1's deferred case).
