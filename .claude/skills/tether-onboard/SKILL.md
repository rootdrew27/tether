---
name: tether-onboard
description: Survey this project and create an initial tether graph — tethers
  with quality descriptions for every relationship whose drift would matter.
  For projects newly initialized with tether.
disable-model-invocation: true
---

# Onboard: create this project's initial tether graph

Survey this project and create a tether for every relationship whose drift would matter — pairs of files where a change to one side that isn't reflected in the other leaves the project subtly wrong. Work autonomously: survey, judge, create, measure, and report at the end. Do not pause to ask for approval on individual tethers.

> **Invocation:** the examples below use bare `tether`; substitute the form that works in this project (`uv run tether`, `poetry run tether`, `.venv/bin/tether`, etc.). All forms are pre-approved.

Two rules override everything else:

- **The description is the deliverable.** A tether's value is its description — the prose a future reader (human or agent) uses to know what must stay aligned. A pair without a good description is not worth tethering.
- **Precision over recall.** A tether whose drift wouldn't matter is noise that trains everyone to ignore real drift signals. When unsure whether a relationship is drift-sensitive, skip it and record why in the final report.

## Prefer regions to whole files

A tether end can target a **region** of a file — a Python symbol (function, class, or method) or a markdown section — instead of the whole file, by appending `::selector` to the path. A region tether drifts only when *that region's* content changes, so it is a sharper, lower-noise signal than a whole-file tether. **Default to the tightest region that captures the coupling**; fall back to a whole-file end only when a region does not fit.

- **Python** (`.py`): a dotted symbol path — `src/calc.py::Calculator.multiply` (a method), `src/calc.py::Calculator` (the class), `src/calc.py::parse` (a top-level function). Only `def`/`class`/method definitions resolve; module-level constants, dicts, and dispatch tables are **not** region-addressable — tether their file.
- **Markdown** (`.md`): a slash-separated, top-anchored heading path — `README.md::Install/Requirements` is the `Requirements` subsection under a top-level `Install` heading. Include the document-title heading if the file has one (`README.md::tether/Install`).
- **Whole file**: use when the coupling spans the whole file (a small single-purpose module, a fixture), the coupled thing is not a single symbol or section, or the file is neither `.py` nor `.md` (no other language has a locator yet).

Either or both ends of a tether may be a region. A renamed symbol or heading currently breaks its region tether with no rename candidate, so favor regions whose identity is stable.

During onboarding, only run `tether coverage`, `tether show`, `tether refs`, and `tether add`. Never run `tether refresh` (every tether you create is freshly fingerprinted; there is nothing to refresh) and never run `tether rm`.

## Step 0 — Orient

Run:

```bash
tether coverage --list-untethered-files --list-tethered-files
```

The untethered list is your work queue. The tethered list is what previous runs (or the team) already covered — **never create a tether that duplicates an existing one.** If a candidate pair involves an already-tethered file, run `tether refs <path>` first and only add if the new relationship is genuinely distinct from what's recorded.

## Step 1 — Survey

Group the untethered files by top-level directory (`src/`, `docs/`, `tests/`, etc.; root-level files form one group).

**Small projects** (≲40 untethered files): survey inline — read what you need and move to Step 2.

**Larger projects:** dispatch one subagent per subsystem, in parallel, using read-only exploration. Give each subagent:

1. Its subsystem's untethered file list (and the project's full file list for cross-references).
2. The candidate patterns below.
3. The **Prefer regions** rule above, so each end is proposed at the tightest grain.
4. This required return format — candidates only, never file contents:

   ```
   CANDIDATE
   a: <project-relative path, with ::selector when only a region is coupled>
   b: <project-relative path, with ::selector when only a region is coupled>
   draft-description: <1–3 sentences: why these must stay aligned>
   confidence: high | medium | low
   evidence: <one line: what in the files ties them together>
   ```

   Put the region in the path with `::selector` when only part of a file is coupled (see **Prefer regions**); give the bare path when the whole file is the unit. Plus a `NO-PARTNER` list: subsystem files with no apparent drift-sensitive partner, each with a one-phrase reason.

Candidate patterns — **seeds, not a taxonomy.** The real test is the Step 2 judge question: *would a change to one side silently leave the other wrong?* Any pair that passes qualifies, even if it matches none of the patterns below. Look actively past the obvious doc↔code and test↔code pairs — most projects have far more relationships than those two kinds. Most of these couple a *part* of each file — a function, a class, a section — so name the region per **Prefer regions** above whenever you can, not the whole file.

- **Doc ↔ code** — a doc that names, specifies, or walks through a source file's behavior (README sections, usage guides, design notes, API docs).
- **Test ↔ implementation** — a test file and its subject (`tests/test_foo.py` ↔ `foo.py` and naming-convention variants).
- **Schema ↔ consumer** — a schema/contract file (JSON Schema, proto, SQL DDL, OpenAPI) and code that reads, validates, or mirrors it.
- **Config ↔ reader** — a config file and the module that parses or depends on its keys.
- **Interface ↔ implementations** — an interface, protocol, ABC, or base class and each implementation that must satisfy it (every implementation must change when the contract does).
- **Producer ↔ consumer of a format** — a serializer and its deserializer, a writer and its reader, a migration and the model or schema it migrates.
- **Registry ↔ enumerated set** — a dispatch table, registry, or `match`/`switch` and the set of variants (enum members, plugins, subclasses) it must enumerate exhaustively.
- **Derived ↔ source** — a generated or derived artifact and its source (golden files, fixtures, snapshots, generated code ↔ its generator or spec).
- **Duplicated contract** — the same constants, routes, error codes, or version strings defined in two places that must move together.
- **Cross-boundary mirror** — one contract reflected on two sides (backend handler ↔ client stub, Python model ↔ TypeScript type).
- **Example ↔ API** — a usage snippet or example and the API surface it demonstrates.
- **Parallel implementations** — two code paths that must stay behaviorally identical (two backends of one interface, a fast path and a reference path).

## Step 2 — Judge

For each candidate (across all subsystems — cross-subsystem pairs surface here), decide: **would drift between these two files actually matter?** Drop candidates that fail that test, whatever their surface similarity. Read the files yourself when the draft evidence isn't conclusive — you are the judge; the heuristics only nominate.

For each accepted pair, finalize the description against this bar:

- Name both sides' roles (what each file is, in this relationship).
- State *what must stay aligned* — concretely enough that a future agent reading only the description knows what to check.
- Mention the trigger if it's not obvious (e.g. "any added/removed subcommand needs a matching usage example").

Then pick the **grain** for each end — the tightest region that captures the coupling, else the whole file (see **Prefer regions**). A proposed selector is only a nominee; you confirm it at create time, since `tether add` resolves and fingerprints each region as it runs and fails loudly when a selector matches no unique symbol or section.

Good (doc ↔ code): `"usage.md documents the CLI surface defined in cli.py (add/sub/mul/div); changes to argparse subcommands or arg types must be reflected in the usage examples."`
Good (registry ↔ enumerated set): `"handlers.py's DISPATCH dict must list one entry per EventType member in events.py; adding or renaming an EventType requires a matching DISPATCH entry, or the event routes nowhere."`
Bad: `"These files are related."` / `"Doc for cli.py."`

## Step 3 — Create

One command per accepted pair. Put each end at the grain chosen in Step 2 — a `::selector` suffix for a region, a bare path for a whole file:

```bash
tether add <a>[::selector] <b>[::selector] --description "<finalized description>"
```

For example:

```bash
tether add src/calc.py::Calculator.multiply tests/test_calc.py::test_multiply --description "..."
tether add docs/usage.md::Commands src/cli.py::main --description "..."
tether add pyproject.toml src/pkg/__init__.py --description "..."   # whole-file: neither end is a single symbol
```

If a selector fails to resolve (no such symbol/section, or an ambiguous name), the `tether add` command errors — tighten or correct the selector, or fall back to the whole file, and re-run.

## Step 4 — Measure and iterate

Re-run `tether coverage --list-untethered-files`. Sweep the remaining untethered files once more for anything the per-subsystem survey missed (especially cross-subsystem pairs). Coverage is a progress signal, **not a target** — many files (lockfiles, CI config, assets, one-off scripts) legitimately have no drift-sensitive partner. Stop when the remaining untethered files all have a reason to stay untethered, not when coverage hits a number.

## Step 5 — Report

End with a summary to the user:

1. **Tethers created** — each pair with its description.
2. **Coverage** — before → after (from Step 0 and Step 4 runs).
3. **Deliberately untethered** — the remaining files, grouped, each group with a one-line reason (so misses are scannable).
4. **Uncertain candidates** — pairs you considered and skipped on the precision rule, so a human can promote any you under-called.
