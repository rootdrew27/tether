---
title: Rename detection research
tags:
  - research
  - git
  - rename
type: research
status: active
---

Research into how tether can follow a renamed [[DICTION#Artifact|Artifact]] toward its new path more seamlessly than the current manual flow. The headline finding: because tether already stores each Artifact's content as a [[DICTION#Git blob OID|git blob]] at [[DICTION#tether add|tether add]] time, tether can synthesize the one input git's rename detector is otherwise missing and reuse git's own similarity engine — making rename detection work on the live, unstaged working tree, including when the file was renamed *and* edited.

> [!info]+ Headline
> tether owns both halves git needs to detect a rename: the **old path** (in the [[DICTION#Tether record|tether record]]) and the **old content** (the [[DICTION#Fingerprint|Fingerprint]] blob in git's object store). Feeding those to git's `diffcore-rename` via a throwaway index detects renames git's normal working-tree diff cannot — with no daemon, no new dependency, and the user's real index untouched.

## Problem

A rename moves a [[DICTION#Artifact|Artifact]]'s file off its recorded path. The [[DICTION#Tether state|state machine]] reports the Artifact [[DICTION#BROKEN|BROKEN]] (the file is not present at the recorded path), which makes the aggregate [[DICTION#Tether|tether]] BROKEN and refuses [[DICTION#Refresh|Refresh]]. Resolution today is the deliberate two-step `tether update --a-path/--b-path <new>` then `tether refresh` once aligned (or `tether mv` for a bulk path rewrite). The goal of this research is to make the *identification* of the new path automatic and high-confidence, so the only thing left to a human or [[DICTION#Coding agent|Coding agent]] is the alignment judgment — never the bookkeeping.

The design draws a firm line here ([[Future-Work]] §"Background automation"): rewriting a **path** is identity bookkeeping and is safe to automate, because the content [[DICTION#Git blob OID|OID]] still matches the Fingerprint so the tether stays [[DICTION#HEALTHY|HEALTHY]]; **Refresh** is an alignment assertion and must never be automated. Everything below stays on the safe side of that line.

## Current MVP mechanism

[[DICTION#Rename detection|Rename detection]] today queries `git log --all --find-object=<fingerprint>` (`find_paths_for_blob` in `git.py`) and surfaces matching historical paths as rename candidates on a BROKEN Artifact. This is exact-OID matching against committed history. It has three structural limits:

- **Uncommitted renames are invisible.** A renamed file that has not been committed at its new path does not appear in `git log`.
- **It cannot survive an edit.** The moment the moved file's content changes, its OID changes, and the Fingerprint OID no longer appears anywhere at the new path.
- **Ambiguity is unranked.** Multiple historical paths come back with no confidence ordering.

## The landscape of mechanisms

Three families were weighed; a fourth (live filesystem watchers) and inode identity were ruled out for the MVP targets (Linux + VS Code) — see the platform analysis in this folder's companion notes and [[Design-Research]] §4. The relevant families:

| Mechanism | Identifies the new path by | Notes |
| --- | --- | --- |
| Git history blob match (`git log --find-object`) — current | exact OID in committed history | misses uncommitted and edited renames |
| Working-tree content-hash scan (the deferred `tether reconcile` in [[Future-Work]]) | exact OID among current files | catches uncommitted pure renames; still blind to edits |
| Git's own rename detection (`git diff -M`, `diffcore-rename`) | **content similarity** | catches rename + edit; gives a confidence score |

Git's rename detector is uniquely able to follow a file that was renamed *and* edited, because it scores similarity rather than requiring byte-identity. The obstacle is *when* it runs.

### Why plain `git diff -M` is not enough on its own

Git's rename detector pairs a *deletion* with an *addition* inside a single diff. A bare `mv old new` (not staged) leaves git seeing `old` as deleted and `new` as an **untracked** file — and an untracked file is not an "addition" git will pair. Verified:

```
# after `mv old.py new.py`, NOT staged:
$ git status --porcelain=v2 --find-renames
1 .D N... … old.py        # deleted
? new.py                  # untracked — not paired
$ git diff -M --name-status
D	old.py                # no rename
```

Rename detection only engages once the change is **staged** (`git mv`, or `git add -A`) or **committed**:

```
# after staging the same rename:
$ git diff --cached -M --name-status
R100	old.py	new.py
# rename + a ~25% edit, staged:
R066	old.py	new.py      # similarity score 66%
```

So on its own, git rename detection is a stage/commit-boundary mechanism with an unstaged blind spot.

## Key finding: synthetic-diff rename detection

The blind spot exists only because the *deletion* side is missing from any diff git will run on an unstaged working tree. tether can supply it.

When a tether is created or refreshed, tether writes the Artifact's bytes into git's object store via `git hash-object -w` and records the OID as the Fingerprint. So tether holds:

- the **old path**, from the tether record, and
- the **old content as a real git blob**, the Fingerprint.

That is exactly the deletion git's rename detector needs. tether can build a synthetic "before" tree containing `{ old_path → fingerprint_blob }`, diff it against the current files, and let git's `diffcore-rename` score the old content against everything on disk — at [[DICTION#tether status|status]] time, with nothing staged.

### How it works (verified plumbing)

All steps run against throwaway index files via `GIT_INDEX_FILE`, so the user's real index and working tree are never modified. The index paths must **not already exist**: git reads `GIT_INDEX_FILE` as an existing index, so a `mktemp`-created 0-byte file fails with `index file smaller than expected`. Use a name-only `mktemp -u` (or a path inside a temp dir), and clean up the matching `.lock` afterward.

```bash
# Inputs: OLD_PATH (the BROKEN Artifact's recorded path)
#         FP       (its Fingerprint = the stored git blob OID)

# 0. Precondition: the fingerprint blob must still be in the object store. A rename + edit
#    needs git to *read* it to score similarity (see Limitations → GC race).
git cat-file -e "$FP^{blob}" || exit   # surface a GC'd fingerprint with a clear error

# 1. T_old — a tree containing only the old path at the fingerprinted content
TI_OLD=$(mktemp -u)                    # name only: the file must not exist yet
GIT_INDEX_FILE="$TI_OLD" git update-index --add --cacheinfo 100644,"$FP","$OLD_PATH"
TREE_OLD=$(GIT_INDEX_FILE="$TI_OLD" git write-tree)

# 2. T_new — current state, SEEDED from the real index. The copy reuses git's stat cache
#    (only genuinely modified files re-hash) AND carries every tracked file, including
#    committed-but-clean ones; `git add -A` then folds in working-tree changes
#    (modifications, new untracked files, deletions).
TI_NEW=$(mktemp -u)
cp "$(git rev-parse --git-path index)" "$TI_NEW"
GIT_INDEX_FILE="$TI_NEW" git add -A

# 3. Let git's rename detector pair the (now-deleted) old path against current files
GIT_INDEX_FILE="$TI_NEW" git diff-index -M --find-renames -z --name-status "$TREE_OLD"
# → among the rows:  R<score>\0<OLD_PATH>\0<new_path>
```

Seed `T_new` from the real index; do not bound it to `git status` candidates. The tempting shortcut — "a rename target can only be a new or changed path, so `T_new` only needs status-flagged files" — holds only relative to `HEAD` at the moment of the rename, not relative to the Fingerprint. Once a rename is **committed**, the working tree is clean and the target is flagged neither added, modified, nor untracked, so a status-bounded `T_new` misses it entirely. Seeding from the index closes that hole for free: the same `cp` that reuses the stat cache also carries the committed-renamed file. Verified against a committed rename on a clean working tree — a status-bounded `T_new` reports only the deletion, while a seeded `T_new` recovers `R100` for a pure rename and `R0xx` for a rename + edit.

### Empirical evidence

Run against a repo where `old.py` (~40 lines) is committed and `FP` is its blob OID, with two unrelated files present as decoys:

| Situation | Synthetic-diff result | Plain `git diff -M` |
| --- | --- | --- |
| `mv old.py new.py`, **unstaged** (new file untracked) | `R100  old.py  new.py` | nothing (only `D old.py`) |
| `mv` + ~25% edit, **unstaged** | `R066  old.py  new.py` | nothing |

The user's real index after both runs still reported the BROKEN state (`1 .D … old.py` / `? new.py`), confirming the synthetic diff is non-invasive.

## Coverage

Because tether supplies the "before" side, git's rename detection no longer needs the change staged or committed — it runs on the live, unstaged working tree. This makes the synthetic diff a **superset** of both exact-OID approaches:

| Rename scenario | Synthetic-diff | `find-object` (current) | Content-hash scan |
| --- | :---: | :---: | :---: |
| Unstaged rename, no edit | `R100` | ✗ | ✓ |
| Staged / committed rename | ✓ | ✓ | ✓ |
| **Rename + edit (any stage)** | **`R0xx`** | ✗ | ✗ |
| Heavy rewrite below threshold | degrades to add + delete | ✗ | ✗ |

- An exact content match surfaces as `R100`, so the synthetic diff *subsumes* `find-object` and the content-hash scan — those are the 100%-similarity special case.
- A renamed-and-edited file surfaces as `R0xx`, the case neither exact-OID approach can reach.
- It is indifferent to `git mv` vs. plain `mv`, staged or not; it only requires the file to exist somewhere on disk.
- Committed-rename coverage holds **only when `T_new` is seeded from the index** (or built from the full working tree). A `T_new` bounded to `git status` candidates is blind to committed renames — a committed rename leaves a clean tree with nothing flagged. See the seeding note under *How it works* above.

This keeps faith with the [[Tether-Design-MVP]] principle *"Federate, do not reimplement"* — tether borrows git's `diffcore-rename` similarity engine rather than writing its own heuristic.

## Limitations

> [!warning]+ Caveats to design around
> - **Sub-threshold rewrites.** A file edited past the similarity threshold (git default 50%) degrades to add + delete and is not matched. Inherent to similarity matching; the threshold is a tunable knob.
> - **GC race, edited case only.** An exact rename matches on OID without reading the blob, so it survives garbage collection. A rename + edit needs git to *read* the Fingerprint blob to compute similarity — if that blob was GC'd (uncommitted for git's grace period), similarity cannot be computed. Same exposure the ref-pinning item in [[Future-Work]] §"Storage and fingerprints" addresses.
> - **Ambiguity.** `diff-index -M` reports a single best match per deletion; surfacing "ambiguous — N near matches" needs an extra inspection pass.
> - **Cost.** Seeding `T_new` from the real index reuses git's stat cache, so only genuinely modified files are re-hashed — the build stays cheap regardless of repo size. The residual cost is git's similarity scoring; see *Rename limit* below.
> - **Rename limit.** `T_old` holds a single entry, so every file in `T_new` is an *addition* and git scores the one deletion against the whole candidate set. git's inexact (similarity) pass is gated by `diff.renameLimit` (default ~1000 files); above it only exact (`R100`) matching runs, and an edited rename silently degrades to add + delete. On a very large repo, raise `diff.renameLimit` high enough to cover the candidate set, or bound the set — at the cost of the committed-rename coverage that seeding buys.
> - **Copies are out of scope.** A copy leaves the old path in place, so the Artifact is never BROKEN. Do not enable `--find-copies`.

## Recommended direction

A single unified candidate-finder, replacing `find_paths_for_blob`'s exact-OID-only logic:

1. On a BROKEN Artifact, run the synthetic-diff — with `T_new` seeded from the real index — at `tether status` time (and therefore inside the Claude Code SessionStart / Stop hooks — see [[Claude-Code-Integration]]). Surface rename candidates **ranked by similarity score**.
2. Resolution stays the deliberate `tether update --a-path/--b-path` → `tether refresh`, unchanged. The score informs the human/agent; it does not assert alignment.
3. A later, separate step can auto-follow high-confidence matches (e.g. `R100` / exact) as a journaled, path-only mutation — never crossing into Refresh. This composes with the journal-and-undo and reconcile-on-status items already sequenced in [[Future-Work]].

This finding also refines the deferred `tether reconcile` design in [[Future-Work]]: the "scan the working tree to re-locate a moved Artifact" idea is better realized through git's rename engine (similarity) than through a custom exact-hash scan, since the former subsumes the latter and additionally follows edits.

[[DICTION]]'s definition of Rename detection currently names only the `find-object` query; if this direction is adopted, that entry and the [[Tether-Design-MVP]] §"How tether is built on top of git" rename paragraph update to describe the synthetic-diff mechanism.

## Open decisions

- **Default similarity threshold** for surfacing a candidate (git's default is 50%; lower catches more edited renames at the cost of more false candidates).
- **Confidence cutoff for silent auto-follow** vs. surface-as-candidate, once auto-follow is in scope.
- **Candidate-set size on large repos.** Seeding `T_new` from the real index is the baseline — cheap (stat-cache reuse) and it covers committed renames. Open: whether repos whose candidate set exceeds `diff.renameLimit` should raise the limit or fall back to a bounded set, the latter trading committed-rename coverage for speed.

## Related

- [[Tether-Design-MVP]] — §"How tether is built on top of git", §"Tether reports structural state; consumers interpret the change".
- [[Git-Integration]] — how tether rides git's read APIs.
- [[Future-Work]] — `tether reconcile`, `tether watch`, reconcile-on-status, journal-and-undo, ref-pinning.
- [[Design-Research]] — §4 file-watching analysis and the pre-MVP rename-detection survey.
- [[DICTION#Rename detection|Rename detection]], [[DICTION#BROKEN|BROKEN]], [[DICTION#Fingerprint|Fingerprint]].
