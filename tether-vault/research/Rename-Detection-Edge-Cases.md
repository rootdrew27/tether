---
title: Rename detection edge cases
tags:
  - research
  - git
  - rename
  - edge-cases
type: research
status: active
---

Companion to [[Rename-Detection-Research]]. That note frames the synthetic-diff rename-detection mechanism — building a throwaway `{old_path → fingerprint_blob}` tree and letting git's own `diffcore-rename` engine score candidates from the live working tree. This note catalogs the outlier and edge-case behaviors that mechanism has to contend with: what breaks, what silently degrades, what holds together but in subtle ways. Items below mix empirically verified behavior (marked **verified**) with reasoned-through scenarios (marked **reasoned**). The summary lists every item; the detailed sections that follow expand each.

## Summary

- **GC'd or unreadable [[DICTION#Fingerprint|fingerprint]] blob** — `diff-index` aborts mid-operation with `fatal: unable to read <oid>`; one bad [[DICTION#Tether|tether]] would crash the whole [[DICTION#tether status|status]] report without defensive handling. **Verified.**
- **Ambiguity concealed by default `-M`** — when multiple working-tree files share the BROKEN content, the default pass reports one as rename and the rest as silent additions. **Verified.**
- **Gitignored rename targets disappear** — `T_new` built via `git add -A` respects `.gitignore`, so renames into ignored paths are invisible. **Verified.**
- **`diff.renameLimit` silently degrades** — git's default ~1000-pair cap silently disables similarity matching above the limit. **Reasoned.**
- **Submodules are invisible** — `git add -A` does not traverse submodule content; renames inside a submodule are unseen. Same blind spot the current `find-object` already has. **Reasoned.**
- **False-positive auto-follow at low similarity** — a coincidental moderate-similarity match could rewrite an [[DICTION#Artifact|Artifact]] path to an unrelated file. **Reasoned.**
- **Coincidental content duplication** — an unrelated file that happens to share content with the BROKEN Artifact is indistinguishable from a rename target. **Reasoned.**
- **Repeated rename + edit decays similarity** — cumulative edits eventually drop the score below threshold and the candidate vanishes. **Reasoned.**
- **Mid-edit save races** — transient duplicate or absent states during VS Code atomic saves; resolves on the next status call. **Reasoned.**
- **Commit reached without resolving BROKEN** — rename + edit + commit lands without updating the [[DICTION#Tether record|tether record]]; detection still works but the audit trail diverges and similarity decays with each subsequent commit. **Reasoned.**
- **Footnotes** — executable mode and symlinks, Git-LFS pointers, partial clones, sparse checkout, `diff.renames=false` override, bare repos / mid-rebase / detached HEAD.

## Hard failures the implementation must handle

### GC'd or unreadable fingerprint blob

> [!warning]+ One bad tether could crash every status call
> Defensive handling is mandatory, not optional. The status report must skip-and-report (consistent with [[Claude-Code-Integration]] §"Partial-failure handling"), never abort.

Two distinct failure modes, both verified:

```
# Invalid OID is caught early:
$ git update-index --add --cacheinfo 100644,0000000000000000000000000000000000000001,old.py
error: invalid object 100644 0000000000000000000000000000000000000001 for 'old.py'
$ git write-tree
fatal: git-write-tree: error building trees   # rc=128

# Real-but-pruned blob (simulating GC) gets past update-index and write-tree,
# then dies inside diff-index:
$ GIT_INDEX_FILE=$TI2 git diff-index -M --find-renames --name-status $TREE
fatal: unable to read 90e0787aba641e0bcc6d94c7264bd8c9464540fb   # rc=128
```

The second failure is the dangerous one: the diff aborts after the rename pairing has already started, so a single missing blob would surface as an exception inside `tether status`. The implementation must pre-check blob presence with `git cat-file -e <oid>^{blob}` (the existing `blob_exists` helper in `git.py`) and capture `diff-index` exit and stderr as a backstop.

This sharpens the priority of the ref-pinning item in [[Future-Work]] §"Storage and fingerprints". Without ref-pinning, every tether whose blob is unreachable for >2 weeks loses similarity-based detection entirely — even exact (`R100`) matches, because the diff itself fails before pairing.

## Silent gaps the spec needs to decide about

### Ambiguity concealed by default `-M`

When three working-tree files all share the BROKEN content, the default `-M` pass reports only one of them:

```
R100  old.py  copy1.py
A     copy2.py
A     copy3.py
```

The other two appear as plain additions, so a naive consumer of the diff would never see they are equally valid rename candidates. `--find-copies` reveals them all (`C100 / C100 / R100`), but it is documented as expensive and is not appropriate as the per-call default.

Cheap workaround that needs no extra git invocation: include `--raw` in the synthetic-diff pass so each row carries the destination OID, then post-filter the `A` rows whose OID equals the fingerprint OID. Equal-OID additions are exact duplicates and surface as multi-candidate ambiguity:

> Best match `new.py` (R100). Equal-content also at `copy1.py`, `copy2.py` — ambiguous, choose explicitly.

For `R<100` (similarity) ambiguity the surface is harder to compute cheaply; reasonable v1 stance is to surface only the top match plus a flag, behind an opt-in `--all-candidates` for diagnostic runs.

### Gitignored rename targets disappear

Verified — moving `old.py` into a gitignored `tmp/`:

```
# default T_new (git add -A, respects .gitignore):
A     .gitignore
D     old.py                       # rename invisible

# T_new built with `git add -A -f`:
A     .gitignore
R100  old.py  tmp/old.py
```

This is a design fork, not a bug. Respecting `.gitignore` keeps `T_new` small and excludes the usual high-noise paths (`node_modules`, `dist`, build trees). Force-including catches the rename-into-ignored case but inflates the candidate set dramatically.

Recommended posture: **respect `.gitignore` by default.** Moving source into an ignored path is almost always a user mistake, and *not* surfacing it is arguably the correct signal. Offer `tether status --include-ignored` as an opt-in diagnostic; when it finds a candidate that the default pass did not, emit a high-signal warning ("did you mean to move source into a build dir?"). The current MVP `find-object` already has the equivalent blind spot — ignored paths are not in git history either.

### `diff.renameLimit` silently degrades on huge change sets

Git's default rename limit is ~1000 sources × destinations; over that, rename detection is silently skipped and the diff falls back to add/delete. `T_new` bounded to `git status` candidates keeps tether well under in practice, but two safeguards still warrant code:

- Pass `-c diff.renameLimit=0` to the synthetic-diff so behavior is independent of user gitconfig.
- Capture `diff-index` stderr and scan for the `inexact rename detection was skipped due to too many files` warning, so degraded results are reported as such instead of silently looking like "no rename candidate."

### Submodules are invisible

`git add -A` from the parent does not traverse submodule contents, so renames inside a submodule are not in `T_new`. This is the same blind spot the current `find-object` has — `git log --all` does not cross submodule boundaries. Document the limitation; no MVP fix.

## Behavioral edges

### False-positive auto-follow at low similarity

If the silent-auto-follow threshold is set too low, a coincidental ~50% match could rewrite an Artifact path to an unrelated file. The damage is bounded: the tether's recorded OID no longer matches the new file, so the aggregate state goes [[DICTION#DRIFTED|DRIFTED]] rather than silently HEALTHY, and the journal-and-undo item in [[Future-Work]] §"Background automation" provides reversal. But it is still a wrong arrow in the relationship graph until corrected.

Implication: silent auto-follow stays gated at `R100` / exact OID. Lower-similarity matches surface as ranked candidates for the human or [[DICTION#Coding agent|Coding agent]] to confirm, never auto-applied.

### Coincidental content duplication

A user creates a *new* file with content identical to a long-deleted BROKEN Artifact — copy-paste from elsewhere, generated boilerplate, an empty file — and the synthetic-diff cheerfully proposes it as a rename target. Inherent to any content-based detection.

Tether's two-step manual `update` → `refresh` flow guards naturally against silent damage. For auto-follow this argues for a confidence threshold *plus* a presence check: only auto-follow when the old path existed in HEAD's history (already an item in [[Future-Work]] §"Refined BROKEN diagnostics"). Belt and suspenders.

### Repeated rename + edit decays similarity

`old.py` → `mid.py` (small edit) → `new.py` (more edits). By the time tether observes BROKEN, cumulative similarity may have dropped below threshold. Detection falls back to add/delete; no candidate. Inherent limitation of any similarity approach. The "Commit reached without resolving BROKEN" item below describes the related multi-commit decay path.

### Mid-edit save races

VS Code's atomic save briefly creates a new file and removes the old; precisely during that window a `tether status` could observe a duplicate or transient absence. The synthetic diff is non-invasive and re-runs cheaply, so the next status call resolves the picture correctly. Worth noting in the spec, no fix needed.

## Trajectory issues

### Commit reached without resolving BROKEN

The scenario:

1. The user or [[DICTION#Coding agent|Coding agent]] renames `auth.py` → `authentication.py` and edits it.
2. `tether status` would report BROKEN with a candidate (the synthetic-diff finds `R<score>  auth.py  authentication.py`).
3. But nobody ran status — the [[Claude-Code-Integration#Stop hook|Stop hook]] did not fire, the agent ignored its output, or the work happened entirely in a terminal session.
4. `git add -A && git commit`. The tether record is unchanged in that commit: it still names `auth.py` and the old fingerprint.

Detection still works after the commit. The file is at the new path on disk; the synthetic-diff still pairs it on the next status call. So there is no permanent damage. But three real consequences are worth naming.

**The commit's audit trail is misleading.** The commit changed `auth.py` → `authentication.py` and the documentation, but the tether record committed alongside it still says `auth.py`. `git log` on the tether file shows no movement on a commit that semantically should have moved the tether's path. This breaks the [[Tether-Design-MVP]] §Boundaries promise — by analogy with the fingerprint invariant *"fingerprint changed in this commit ↔ files fingerprinted to that OID also changed in this commit"*, the parallel *"path changed in the working tree ↔ path changed in the tether record"* is violated. The PR review surface that the [[Git-Integration]] doc relies on becomes incoherent: a reviewer scanning the commit cannot correlate the rename with a corresponding tether update.

**Drift signal degrades over distance.** Each subsequent edit-without-resolving lowers the similarity score against the original fingerprint. Several commits later the score may fall below threshold and the rename candidate vanishes; the tether becomes silently unrecoverable except by manual archaeology (`git log --follow` against the new path, cross-referencing against the stored fingerprint). What was a high-confidence `R100` at commit 1 may be an undetectable add/delete at commit 5.

**GC race for the fingerprint.** If the original `auth.py` content was never committed at the old path (the tether was created against uncommitted content) and the file is then renamed + edited + committed, the fingerprint blob becomes unreachable from any ref. Combined with the GC failure described above under "Hard failures," the blob can be pruned after git's grace period and similarity detection dies — even though the file is right there at the new path. The detection that works *today* may not work in three weeks.

**Implications for the plan.** Three things follow:

- The **pre-commit hook** sketched in [[Rename-Detection-Research]] §"Recommended direction" is the natural place to close this. Run the synthetic-diff against the staged change set; for each tether whose old path appears as a rename source at high confidence, either auto-rewrite the tether record so the path-follow lands in the same commit, or refuse the commit with a clear message. Without the pre-commit hook, the Stop hook is the only safety net — and the Stop hook only fires inside Claude Code sessions, so terminal-driven commits bypass it entirely.
- The **reconcile-on-status** item in [[Future-Work]] §"Background automation" needs to differentiate two diagnostic states: *"BROKEN, candidate exists"* and *"BROKEN, candidate exists, and the rename has already been committed."* The latter calls for a more urgent prompt — the commit is now historical, and every subsequent commit further degrades the signal.
- The **fingerprint ref-pinning** item rises from "diff-inspection hardening" to "operational dependency" for any project with long-lived feature branches that rename + commit without resolving.

## Footnotes

Minor edges that the spec should acknowledge but that do not change the design:

- **Executable mode and symlinks.** The synthetic tree uses mode `100644` regardless of the file's real mode; git rename similarity ignores mode, so this does not affect pairing. Symlinks are stored as mode `120000` with the link target string as content — renames of symlinks work, but a tethered symlink fingerprints the *target string*, not the pointed-to bytes.
- **Git-LFS.** The fingerprint OID is the LFS pointer file's OID, not the large object's OID. Rename detection runs at the pointer level (which is what tether records and tracks anyway). Same characteristic the current MVP has.
- **Partial clone (`blob:none`).** The fingerprint blob may be fetched on demand inside `diff-index`, producing a network call mid-status. Worth noting for offline use.
- **Sparse checkout.** A "renamed" file may legitimately not be materialized on disk. Tether's path-based BROKEN check already has this exposure; the synthetic diff does not worsen it.
- **`diff.renames=false`** in user gitconfig is **overridden** by an explicit `--find-renames` flag (verified: `R100` despite the config). Tether passes the flag explicitly, so behavior is robust to user gitconfig.
- **Bare repos / mid-rebase / detached HEAD.** The synthetic diff does not depend on `HEAD`; it runs against synthesized trees against a throwaway index. Mid-rebase state in the user's real index does not leak in. Bare repos cannot host a working tree and are already refused by `tether init`.

## Implications for the plan

Consolidating across all items above, the synthetic-diff design needs five additions and elevates two existing [[Future-Work]] items:

1. **Failure-mode contract.** Pre-check blob existence; treat both "OID invalid" and "blob unreadable mid-diff" as recoverable per-tether errors that flow into the partial-failure surface in [[Tether-Design-MVP]] §"Validation invariants" and [[Claude-Code-Integration]] §"Partial-failure handling" — never abort the whole status report.
2. **Ambiguity surface.** Default `-M` pass plus equal-OID post-filter from `--raw` output so `R100` ambiguity is reported as a multi-candidate set without an extra git call. `R<100` ambiguity behind `--all-candidates`.
3. **Gitignore policy.** Default respect; `--include-ignored` opt-in for diagnostic runs. Warning surface when a candidate appears only under `--include-ignored`.
4. **`diff.renameLimit` neutralization.** Pass `-c diff.renameLimit=0`; scan stderr for the rename-limit warning and surface degraded detection explicitly.
5. **Pre-commit hook.** `tether init --with-git-hooks` runs the synthetic-diff against the staged change set; high-confidence rename sources for BROKEN tethers either auto-rewrite the record in-commit or refuse the commit. Closes the "Commit reached without resolving BROKEN" trajectory.

Elevated items:

- **Ref-pinning** ([[Future-Work]] §"Storage and fingerprints") moves from "optional hardening for diff inspection" to **load-bearing for similarity detection on long-lived branches.** Every tether whose blob is unreachable for >2 weeks loses detection entirely.
- **Journal-and-undo** ([[Future-Work]] §"Background automation") stays the prerequisite for any auto-follow, since false positives (#6) and coincidental duplication (#7) are inherent and reversibility is the only acceptable safety net.

## Related

- [[Rename-Detection-Research]] — the synthetic-diff mechanism this note's edges are about.
- [[Tether-Design-MVP]] — §Boundaries audit-trail invariant, §"Partial-failure handling".
- [[Git-Integration]] — how tether rides git's read APIs and how the PR review surface depends on commit-level coherence.
- [[Future-Work]] — `tether reconcile`, ref-pinning, journal-and-undo, refined BROKEN diagnostics, reconcile-on-status, pre-commit hook (`tether init --with-git-hooks`).
- [[Claude-Code-Integration]] — Stop hook, partial-failure handling.
- [[DICTION]] — [[DICTION#BROKEN|BROKEN]], [[DICTION#Fingerprint|Fingerprint]], [[DICTION#Refresh|Refresh]], [[DICTION#Artifact|Artifact]], [[DICTION#Rename detection|Rename detection]].
