FRAGMENT = """# tether

This project uses **tether** to track relationships between files. A tether is a record that links two artifacts (a doc and the code it describes, a test and the code it exercises, etc.) and remembers each file's content at the moment the relationship was asserted. When either file drifts from the recorded fingerprint, the tether surfaces it on `tether status` and at session boundaries.

A tether has no direction and no type — it is a declaration of connection between two files. The rich semantics live entirely in the description.

## When to create tethers

Create tethers freely. Whenever you author or modify two files that are intentionally coupled — a doc and the code it describes, a test and its target, two related implementation files — record the relationship with `tether add`. Tethers cost nothing on disk and pay off as the codebase changes.

`--description` is **required** on every tether. Write a sentence that captures *why* the relationship exists; that prose is what a future reader (human or model) reads first.

## Tether records and access

Everything under `.tether/` is tether-owned and read-only to you. This includes tether records at `.tether/tethers/<uuid>.json`, this fragment at `.tether/tether.md`, and any other state tether writes there. Direct edits via `Edit`, `Write`, `MultiEdit`, or `NotebookEdit` on anything under `.tether/` are blocked by `.claude/settings.json`. Modify tether state only through the `tether` CLI.

You may freely *read* anything under `.tether/` — records are pretty-printed JSON.

## State model

Each artifact of a tether is in one of three states:

- **HEALTHY** — the file matches its recorded fingerprint.
- **DRIFTED** — the file exists but its content no longer matches the fingerprint.
- **BROKEN** — the file is not present at the recorded path.

The aggregate state of a tether is derived:

- both artifacts HEALTHY → **HEALTHY**
- one artifact HEALTHY, one DRIFTED → **WEAKENED**
- both artifacts DRIFTED → **DRIFTED**
- any artifact BROKEN → **BROKEN**

## Resolution

- **HEALTHY** — no action.
- **WEAKENED / DRIFTED** — read the drifted file(s) and decide:
  - If both artifacts should still be aligned and you can edit them safely, bring the lagging artifact(s) into agreement and run `tether refresh <uuid>` to re-fingerprint. *Do not refresh* until alignment is real — refresh erases the drift signal.
  - **Before refresh, re-check the description.** Refresh ratifies file content, not the description text — if your coordinated edit has put the description out of sync with the new shape of the relationship (e.g. it enumerates items that have changed, or claims behavior that no longer holds), run `tether update <uuid> --description "..."` first. A stale description survives refresh.
  - If the resolution is a judgment call (e.g. the description claims coverage that may no longer apply, or aligning would remove information a human just added), surface the choice to the user with the options as you see them and end the turn awaiting direction. Don't guess.
- **BROKEN** — the file was renamed or removed. To follow a rename: `tether update --a-path <new>` or `tether update --b-path <new>` (structural-only, no fingerprint change), then `tether refresh <uuid>` once the new path matches the intended content. If the file is truly gone, `tether rm <uuid>`.

## When to run `tether status`

Run `tether status` as a *diagnostic*, not a verification step:

- **Use it** when investigating a Stop block (`tether status <uuid>` for a diff on one tether), or when you suspect drift in a file you haven't touched in this session.
- **Don't use it** to pre-check before ending the turn — the Stop hook does this for you. If anything is drifted it will block and tell you what; if not it stays silent.
- **Don't use it** after `tether refresh` — refresh asserts alignment by construction, so a follow-up status call is wasted work.

## Automatic tether context on Read

When you read a tethered file, tether injects a `<tether-context>` block alongside the file content. Each `<tether>` element carries:

- `aggregate` — the tether's overall state.
- `<self path state />` — your side's per-tether state (the file you just read; per-side state can differ across tethers because each tether records its own fingerprint).
- `<peer path state />` — the other artifact's path and per-tether state.
- `<description>` — the project-specific reason the relationship exists. Treat it as authoritative for how a coordinated edit should look.

If the aggregate is **WEAKENED** or **DRIFTED**, plan coordinated edits per the description before ending the turn. If **BROKEN**, the peer file is missing — use `tether update --a-path/--b-path` to follow a rename, or `tether rm` to retire the record.

The per-side states in `<tether-context>` are current at the moment of the Read; you do not need to run `tether status` to verify them.

## Key commands

> **Invocation:** Use whichever form matches your project: bare `tether`, `uv run tether`, `poetry run tether`, `conda run -n <env> tether`, `.venv/bin/tether`, or `${CLAUDE_PROJECT_DIR}/.venv/bin/tether`. These forms are pre-approved in `.claude/settings.json`. The examples below use bare `tether` for brevity; substitute your project's prefix.

- `tether status` — show all tethers, severity-ordered.
- `tether status <uuid>` — show one tether with a unified diff for any DRIFTED artifact.
- `tether refs <path>` — list tethers referencing a path. Rarely needed during normal work since context is auto-injected on Read; useful for debugging or for inspecting what the agent would see (`--xml`).
- `tether add <a> <b> --description "..."` — create a tether. `--description` is required.
- `tether refresh <uuid>` — re-fingerprint both artifacts; the explicit assertion that they are aligned.
- `tether update <uuid> [--a-path <p>] [--b-path <p>] [--description "..."]` — structural change, no fingerprint touch.
- `tether mv <old> <new>` — bulk path rewrite across every tether referencing `<old>`.
- `tether rm <uuid>` — delete a tether record.
"""
