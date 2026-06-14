# tether

This project uses **tether** to track relationships between content in a project. A tether is a record that semantically links two artifacts — two files whose content must stay aligned, where a change to one would require a change to the other to keep the project correct — via a textual description. The artifacts themselves are represented by a hash (i.e. an OID) and a file path.

A tether has no direction and no type — it is a declaration of relation between two files. The relationship can be *anything* whose drift would matter; tether does not constrain it to a fixed set of kinds. The rich semantics live entirely in the description.

## When to create tethers

Create tethers freely. Whenever two files are intentionally coupled — a change to one demands a change to the other to keep the project correct — record the relationship with `tether add`. The coupling takes many forms; do not stop at the obvious doc↔code and test↔code pairs. A non-exhaustive sampling:

- a doc, comment, or spec and the code it describes
- a test and the code it exercises
- an interface, protocol, or base class and each implementation that must satisfy it
- a producer and consumer of a serialized format (a serializer and its deserializer; a migration and the model or schema it migrates)
- a registry, dispatch table, or `match`/`switch` and the set of variants it must enumerate
- a generated or derived artifact and its source (fixtures, golden files, generated code and its generator or spec)
- the same constant, route, error code, or version string duplicated in two places that must move together
- a contract mirrored across a boundary (a backend handler and its client stub; a model and its typed schema)
- an example or usage snippet and the API it demonstrates

The test is always the same: **if a change to one file would silently leave the other wrong, it is a candidate** — whatever its surface form.

`--description` is a **required** flag of the `tether add` command. A **description** is required for every tether and should describe the relationship of the artifacts; that prose is what a future reader (human, LLM, etc.) uses.

## Tether records and access

Everything under `.tether/` is tether-owned and read-only to you. Direct edits via `Edit`, `Write`, `MultiEdit`, or `NotebookEdit` on anything under `.tether/` are blocked. Interact with tethers only through the `tether` CLI.

## Tether record shape

Each tether is one JSON file at `.tether/tethers/<id>.json`. Pretty-printed, keys sorted alphabetically. Example:

```json
{
  "a": {
    "fingerprint": "7ba020583495e9a2e4c2acf6c6015e2623c2c29f",
    "path": "src/calculator.py"
  },
  "b": {
    "fingerprint": "14e65bbd591b80100ccb72bf3e3e531d0d2c2429",
    "path": "tests/test_calculator.py"
  },
  "created_at": "2026-05-25T03:34:55Z",
  "description": "Tests exercise every operation in calculator.OPERATIONS plus the ZeroDivisionError path. Any added/removed/renamed operation needs a matching test update.",
  "id": "019e5d33-2cc6-7601-9a6f-52226e8494e8",
  "refreshed_at": "2026-05-25T03:34:55Z",
  "schema_version": 1
}
```

| Field | Type | Meaning |
|---|---|---|
| `id` | UUIDv7 string | The tether's stable identifier (also the filename). Use this as `<uuid>` in CLI commands. |
| `schema_version` | integer | Record schema version. Current is `1`. |
| `a`, `b` | object | The two ends of the tether. Labels are stable (whichever was passed first to `tether add` becomes `a`) but carry no direction — neither end is privileged. |
| `a.path`, `b.path` | string | Project-relative POSIX path to the artifact file. |
| `a.fingerprint`, `b.fingerprint` | string | Git blob OID of the file's content at fingerprint time. Drift detection compares this against the file's current OID. |
| `description` | string | Required free-form prose explaining *why* this relationship exists. The data model itself is untyped — the project-specific semantics live here. |
| `created_at` | ISO 8601 UTC | When the tether was first added. |
| `refreshed_at` | ISO 8601 UTC | When the tether was last refreshed (re-fingerprinted). Equal to `created_at` on a freshly added tether. |

## State model

Each artifact of a tether is in one of three states:

- **HEALTHY** — the file path exists and its content matches its recorded fingerprint.
- **DRIFTED** — the file exists but its content no longer matches the fingerprint.
- **BROKEN** — the file is not present at the recorded path.

The aggregate state of a tether is the most severe of its two artifact states (HEALTHY < DRIFTED < BROKEN):

- both artifacts HEALTHY → **HEALTHY**
- one or both artifacts DRIFTED with neither BROKEN → **DRIFTED**
- either artifact BROKEN → **BROKEN**

A **DRIFTED** aggregate alone does not indicate whether one side or both sides have drifted.

## Resolution

- **HEALTHY** — no action.
- **DRIFTED** — read the drifted file(s) and the description, then pick the path that fits:
  - **Align the file(s) to the description.** The description still captures the relationship correctly. Edit one or both files to bring their content back into agreement with what the description claims. *Reverting unintentional drift* (abandoned edit, accidental save) is the trivial case — if the restored bytes match the fingerprint exactly, the tether becomes HEALTHY without a refresh.
  - **Align the description to the file(s).** The files have legitimately moved past what the description says — new behavior, restructured items, changed scope. Run `tether update <uuid> --description "..."` to record what the relationship now means.
  - **Align both** — when the code change is real *and* its paired doc is also stale. Update the description first to capture the new shape, then bring the paired file into agreement with the updated description.
  - **Retire** (`tether rm <uuid>`) when the files no longer have a meaningful relationship — one repurposed, doc rewritten for an unrelated topic.
  - **Restructure** (`tether rm <uuid>` + `tether add`) when the relationship's shape has changed — code split into two files, docs merged, scope spans different artifacts than the tether records.

  After aligning, run `tether refresh <uuid>` to re-fingerprint both artifacts — the explicit assertion that they are now aligned. *Do not refresh until alignment is real* — refresh erases the drift signal.
- **BROKEN** — the file was renamed or removed. Run `tether status <uuid>` to see the rename candidate (the most content-similar file in the working tree, if any). To follow the rename: `tether update --a-path <new>` or `tether update --b-path <new>` (structural-only, no fingerprint change), then `tether refresh <uuid>` once the new path matches the intended content. If the file is truly gone, `tether rm <uuid>`.

## When to run `tether status`

Run `tether status` as a *diagnostic*, not a verification step:

- **Use it** when investigating a Stop block (`tether status <uuid>` for a diff on one tether), or when you suspect drift in a file you haven't touched in this session.
- **Don't use it** to pre-check before ending the turn — the Stop hook does this for you. If anything is drifted it will block and tell you what; if not it stays silent.
- **Don't use it** after `tether refresh` — refresh asserts alignment by construction, so a follow-up status call is wasted work.

## Automatic tether context on Read

When you read a tethered file, tether injects a JSON block alongside the file content with the same shape as `tether refs <path>`. Top-level fields:

- `queried_path` — the file you just read. Use it to identify which of `a`/`b` is your side; the other is the peer.
- `summary` — counts by state across the listed tethers.
- `tethers` — severity-ordered list. Each entry carries:
  - `state` — the tether's aggregate state.
  - `a`, `b` — the two artifacts. Stable labels (whichever was passed first to `tether add` is `a`); neither end is privileged. Each carries `path`, `fingerprint`, and `state`.
  - `description` — the project-specific reason the relationship exists. Treat it as authoritative for how a coordinated edit should look.
- `errors` — always empty in this context (corrupt-record errors are reported by SessionStart and Stop, not on every Read).

If the aggregate `state` is **DRIFTED**, plan coordinated edits per the description before ending the turn. If **BROKEN**, the peer file is missing — rename candidates are not included in this context, so run `tether status <uuid>` to see them, then use `tether update --a-path/--b-path` to follow the rename, or `tether rm` to retire the record.

The per-side `state` values are current at the moment of the Read; you do not need to run `tether status` to verify them.

## Key commands

> **Invocation:** Use whichever form matches your project: bare `tether`, `uv run tether`, `poetry run tether`, `conda run -n <env> tether`, `.venv/bin/tether`, or `${CLAUDE_PROJECT_DIR}/.venv/bin/tether`. These forms are pre-approved in `.claude/settings.json`. The examples below use bare `tether` for brevity; substitute your project's prefix.

- `tether status` — show all tethers, severity-ordered.
- `tether status <uuid>` — show one tether with a unified diff for any DRIFTED artifact, and rename candidates for any BROKEN artifact.
- `tether show` — list every tether with its description, regardless of state (including the HEALTHY ones `tether status` collapses into a count). Use for **orientation**: the whole relationship graph and the *why* behind each link, when onboarding to a project or planning a change that spans several files. Not a per-turn check and not a drift diagnostic — use `tether status` for drift and `tether refs <path>` for what touches a specific file.
- `tether refs <path>` — list tethers referencing a path. Rarely needed during normal work since context is auto-injected on Read.
- `tether coverage [--list-untethered-files] [--list-tethered-files]` — report what fraction of git-tracked files participate in a tether; the flags append the corresponding file lists. Structural-only. Use when surveying what still lacks tethers (e.g. during project onboarding), not as a per-turn check — many files legitimately have no drift-sensitive partner.
- `tether add <a> <b> --description "..."` — create a tether. `--description` is required.
- `tether refresh <uuid>` — re-fingerprint both artifacts; the explicit assertion that they are aligned.
- `tether update <uuid> [--a-path <p>] [--b-path <p>] [--description "..."]` — structural change, no fingerprint touch.
- `tether mv <old> <new>` — bulk path rewrite across every tether referencing `<old>`.
- `tether rm <uuid>` — delete a tether record.
