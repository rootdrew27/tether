FRAGMENT = """# tether

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

A tether end is usually a whole file, but it can also target a **region** — a Python symbol (function, class, or method) or a markdown section — by appending `::selector` to the path: `src/calc.py::Calculator.multiply` for a symbol, `README.md::Install/Requirements` for a markdown heading path. A region tether drifts only when *that region's* content changes; edits elsewhere in the file leave it HEALTHY. Reach for a region when only part of a file is coupled to the peer (one function and its test, one doc section and the code it describes). Either or both ends of a tether may be a region.

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
| `schema_version` | integer | Record schema version. `1` for a whole-file tether; `2` when either artifact targets a region (carries a `locator`). |
| `a`, `b` | object | The two ends of the tether. Labels are stable (whichever was passed first to `tether add` becomes `a`) but carry no direction — neither end is privileged. |
| `a.path`, `b.path` | string | Project-relative POSIX path to the artifact file. |
| `a.fingerprint`, `b.fingerprint` | string or object | For a whole-file artifact, the git blob OID of the file's content at fingerprint time. For a region artifact, an object `{"file_blob_oid": ..., "region_hash": ...}` — `file_blob_oid` is the whole file's OID (used for rename detection), `region_hash` is the drift signal compared against the region's current content. |
| `a.locator`, `b.locator` | object | Present only on a region artifact: `{"kind": "symbol", "lang": "python", "selector": "Calculator.multiply"}` or `{"kind": "heading", "lang": "markdown", "selector": "Install/Requirements"}`. Omitted entirely on a whole-file artifact. |
| `description` | string | Required free-form prose explaining *why* this relationship exists. The data model itself is untyped — the project-specific semantics live here. |
| `created_at` | ISO 8601 UTC | When the tether was first added. |
| `refreshed_at` | ISO 8601 UTC | When the tether was last refreshed (re-fingerprinted). Equal to `created_at` on a freshly added tether. |

A region artifact replaces the string fingerprint with the object form and adds a `locator`. Only the `a` side is shown; the `b` side could be a whole file or another region:

```json
{
  "a": {
    "fingerprint": {
      "file_blob_oid": "7ba020583495e9a2e4c2acf6c6015e2623c2c29f",
      "region_hash": "9d2e0c1b5f8a3e7c4b6d0a2f1e8c5b3a7d9f0e1c"
    },
    "locator": { "kind": "symbol", "lang": "python", "selector": "Calculator.multiply" },
    "path": "src/calculator.py"
  }
}
```

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

For a **region** artifact (one with a locator), the states are scoped to the selected region, not the whole file:

- **DRIFTED** — the region still resolves but its own content changed. Edits elsewhere in the file leave the region HEALTHY.
- **BROKEN** — the file is missing at the recorded path, *or* the locator can no longer resolve the region in it (the symbol or heading was renamed or removed, or the file no longer parses). Region-rename suggestions are not yet emitted, so a BROKEN region carries no rename candidate.

## Resolution

- **HEALTHY** — no action.
- **DRIFTED** — read the drifted file(s) and the description, then pick the path that fits:
  - **Align the file(s) to the description.** The description still captures the relationship correctly. Edit one or both files to bring their content back into agreement with what the description claims. *Reverting unintentional drift* (abandoned edit, accidental save) is the trivial case — if the restored bytes match the fingerprint exactly, the tether becomes HEALTHY without a refresh.
  - **Align the description to the file(s).** The files have legitimately moved past what the description says — new behavior, restructured items, changed scope. Run `tether update <uuid> --description "..."` to record what the relationship now means.
  - **Align both** — when the code change is real *and* its paired doc is also stale. Update the description first to capture the new shape, then bring the paired file into agreement with the updated description.
  - **Retire** (`tether rm <uuid>`) when the files no longer have a meaningful relationship — one repurposed, doc rewritten for an unrelated topic.
  - **Restructure** (`tether rm <uuid>` + `tether add`) when the relationship's shape has changed — code split into two files, docs merged, scope spans different artifacts than the tether records.

  After aligning, run `tether refresh <uuid>` to re-fingerprint both artifacts — the explicit assertion that they are now aligned. *Do not refresh until alignment is real* — refresh erases the drift signal.
- **BROKEN** — the file was renamed or removed. Run `tether status <uuid>` to see the rename candidate (the most content-similar file in the working tree, if any). To follow the rename: `tether update --a-path <new>` or `tether update --b-path <new>` (structural-only, no fingerprint change), then `tether refresh <uuid>` once the new path matches the intended content. If the file is truly gone, `tether rm <uuid>`. For a **region** that broke because its symbol or heading was renamed within a still-present file, repoint the selector instead: `tether update --a-selector <new>` (or `--b-selector`), then `tether refresh <uuid>`.

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
- `tether add <a> <b> --description "..."` — create a tether. `--description` is required. Each of `<a>`/`<b>` may carry a `::selector` suffix to tether a region instead of the whole file (e.g. `src/calc.py::Calculator.multiply` or `README.md::Install/Requirements`).
- `tether refresh <uuid>` — re-fingerprint both artifacts; the explicit assertion that they are aligned.
- `tether update <uuid> [--a-path <p>] [--b-path <p>] [--a-selector <s>] [--b-selector <s>] [--description "..."]` — structural change, no fingerprint touch. `--a-selector`/`--b-selector` repoint a region's symbol.
- `tether mv <old> <new>` — bulk path rewrite across every tether referencing `<old>`.
- `tether rm <uuid>` — delete a tether record.
"""
