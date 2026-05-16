---
title: Drift cases
tags:
  - design
  - drift
type: design
status: active
---

This document enumerates the realistic ways content can move or change and how tether reports them. Tether does not implement its own similarity search, content-hash scan, or move-block detection — git's existing tools are the substrate, and tether is a thin client. The diff-first principle does the rest of the work.

## Region content changed in place

The locator still resolves; the region hash differs from the fingerprint (and normalization, if applicable, does not rescue equivalence); the tether is DRIFTED on that artifact. Tether retrieves the fingerprinted region bytes via `git cat-file blob <region_hash>` and produces a `git diff` against the current located region. The agent reads the diff and decides whether the relationship still holds.

## Region moved within the file

The locator may resolve to different content (the line range now contains something else) — that's reported as DRIFTED. To make the move visible, the status report also includes a whole-file diff with `git diff --color-moved=zebra`, which highlights blocks that have been relocated. The agent sees the original block as moved-from at one location and moved-to at another, and can run `tether update` to follow.

## File moved or renamed

The locator can't resolve at the recorded path; the tether is BROKEN on that artifact. Tether queries `git log --find-object=<file_blob_oid>` against the project's history. If git's rename detection identifies the new path, tether suggests `tether update --path <new>` in its status report. If no rename is found, the file is reported as gone and the user decides between `tether rm` and restoring from history.

## Region renamed (e.g., function rename)

The locator still resolves (the lines still exist); the region hash differs (because the first line changed). Tether reports DRIFTED with a diff showing the rename inline. The agent reads the diff, recognizes the rename, and updates the doc (or whichever artifact references the old name) accordingly.
