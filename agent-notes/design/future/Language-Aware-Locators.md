# Language-Aware Locators (tree-sitter section tethers)

**Status:** Implemented for Python symbols and markdown headings, on branch `worktree-section-locators` (unmerged — held until the design proves out in dogfooding). The vertical slice (locator schema, tree-sitter substrate, symbol + heading resolution through `add` / `status` / `refresh` / `update`), the presentation surfaces, and the agent fragment are all live. Remaining future work: region-rename *suggestions*, ref-pinning the synthetic region blobs, per-run tree caching, and breadth to further languages. See [Status of the staged plan](#status-of-the-staged-plan).

**Goal:** Extend a tether endpoint from "the whole file at this path" to "a *region* of this file" — a markdown section, a Python function or class — selected by a language-aware parser, and fingerprinted at region granularity. One parser substrate (tree-sitter) covers markdown, Python, and every future language behind a single interface.

## Design lineage

This realizes deferred work that the data model was built for from day one — not a new direction:

- [Future-Work.md §"Locator extensions"](../Future-Work.md) — "the data model is *designed* to take a `locator` field additively (WholeFile = locator absent)… adding sub-file locator types is a strictly local extension," and §"Language-aware locators" names "AST queries via tree-sitter."
- [Tether-Design-MVP.md §"Looking forward: language-aware extensions"](../Tether-Design-MVP.md) — nominates **AST-aware locators** on a tree-sitter substrate as the v2 direction.
- [DICTION-Future.md](DICTION-Future.md) — defines `Locator`, the `{file blob OID, region hash}` fingerprint pair, and folds an unresolvable locator into `BROKEN`.

**Supersedes** the original two-parser sketch (`mq` for markdown + a separate Python parser). A single tree-sitter substrate is the convergence point both the design docs and the closest competitor already pick — see below.

## Substrate decision: tree-sitter, unified

The competitor to beat — **Fiberplane Drift** — already does symbol-granularity drift via tree-sitter across TS/Python/Rust/Go/Java ([Competitor-Landscape.md](../../research/Competitor-Landscape.md)). tree-sitter is one grammar interface that yields byte-accurate spans for *every* supported language, so markdown and Python are two grammars behind the same code path rather than two bespoke integrations.

[tether/locators.py](../../../tether/locators.py) is the only module that imports tree-sitter: it owns the language registry, a parser cache, and the selector → node → bytes resolution. Adding a language is local to that module plus the extension map in [cli.py](../../../tether/cli.py).

### Verified facts (June 2026)

PyPI, current versions, all `requires-python >= 3.10` (project floor is 3.11 — fine):

| Package | Version | Role |
| --- | --- | --- |
| `tree-sitter` | 0.25.2 | The binding (Language, Parser, Query, QueryCursor, Node) |
| `tree-sitter-python` | 0.25.0 | Python grammar |
| `tree-sitter-markdown` | 0.5.1 | Markdown grammar (split block + inline) |
| `tree-sitter-language-pack` | 1.8.1 | ~165 grammars in one dependency (alternative to per-language deps, deferred) |

### API shape (0.25)

```python
import tree_sitter_python as tspython
from tree_sitter import Language, Parser

PY = Language(tspython.language())
parser = Parser(PY)
tree = parser.parse(source_bytes)                 # bytes in, tree out
node = ...                                         # located by walking named children
region = source_bytes[node.start_byte:node.end_byte]   # byte-exact span
```

`node.start_byte`/`end_byte` are the region bytes; `start_point`/`end_point` are (row, col). The implementation resolves by walking named children rather than via `Query`/`QueryCursor`, so it sidesteps the 0.25-era query-API surface entirely. **ABI note:** tree-sitter and the grammars are pinned, and ABI compatibility is treated as a tested invariant.

**Markdown nesting is level-derived, not section-node-derived.** tree-sitter-markdown is two grammars (block + inline). The block grammar yields `atx_heading` / `setext_heading` / `section` / `inline` nodes. It does *not* reliably wrap **setext** headings in nested `section` nodes (an atx or setext heading following a setext `===` heading lands as a flat sibling, not a nested child), so the resolver cannot trust `section` nesting. Instead it derives the hierarchy directly from heading **levels**: a heading's section ends at the next heading of equal-or-higher level, and its parent is the nearest preceding heading of strictly lower level. This handles atx and setext uniformly and produces byte-identical spans to the section-node approach for pure-atx documents. See `_resolve_heading` in [locators.py](../../../tether/locators.py).

## Data model

`Artifact` carries `path` + `fingerprint` + an optional `locator` ([tether/model.py](../../../tether/model.py)), a frozen `msgspec.Struct`:

- **`locator` is optional.** Absent ⇒ WholeFile ⇒ today's behavior, byte-for-byte. Present ⇒ a region. No migration: every pre-locator record stays valid and parser-free.
- **The fingerprint is a pair *only when a locator is present*** (`RegionFingerprint`):
  - `file_blob_oid` — whole-file git blob OID, exactly as today. Keeps file-level rename detection working unchanged; `Artifact.file_oid` returns it for both shapes so the rename detector treats whole-file and region artifacts identically.
  - `region_hash` — git blob OID of the located region's bytes (storage below).
- **WholeFile keeps its single-OID path.** Locator-absent ⇒ one `fingerprint` string, the existing code path untouched. Locator-present ⇒ the pair. The whole-file case is a branch, not a rewrite.
- **`schema_version`:** records carrying a locator are written as `2`; whole-file records stay `1`, and `validate` accepts both (`SUPPORTED_SCHEMA_VERSIONS = {1, 2}`). A locator requires version 2 (a version-1 record with a locator is rejected). `Artifact` is declared `omit_defaults=True` so a whole-file record serializes byte-for-byte as today — no stray `"locator": null`.

The `locator` struct is a flat triple:

```jsonc
"locator": { "kind": "symbol",  "lang": "python",   "selector": "Calculator.multiply" }
"locator": { "kind": "heading", "lang": "markdown", "selector": "Installation/Requirements" }
```

`lang` is explicit (not inferred from extension at check time — a renamed `.txt` must not silently change parsing; extension → language inference happens only at `add` time, in the CLI). `kind` selects the resolution strategy; `selector` is the human-authored address (next section).

**Supported pairings are a `(kind, lang)` set, not two independent axes.** `model.py` declares `SUPPORTED_LOCATORS = {("symbol", "python"), ("heading", "markdown")}`; `validate()` rejects any other pairing (e.g. `heading`/`python`) loudly at load time rather than letting it resolve to BROKEN. The model and the locator engine ([locators.py](../../../tether/locators.py)) must enumerate exactly the same set — a coupling recorded as a tether.

## Selector grammar — the crux of stability

Line ranges were deferred precisely because line numbers are brittle. The value of a parser-based locator is a selector that names a region **by what it is**, so it survives edits elsewhere and even intra-file moves. The implemented surface:

- **Python — dotted symbol path.** `alpha` (module-level function), `Calculator` (class), `Calculator.multiply` (method), `C.method.nested` (nested function). Resolved by walking `function_definition`/`class_definition` nodes whose `name` matches, descending the dotted path to disambiguate nesting. A `decorated_definition` is unwrapped for name matching and re-wrapped for the span, so a tethered function includes its `@decorator` lines.
- **Markdown — heading path.** `Installation/Requirements` = the `Requirements` section nested beneath `Installation`. The path is **anchored**: each segment names a heading whose parent is the previous segment, the first segment a top-level heading — so a sole document-title `# H1` is part of the path (`tether/Install`, not bare `Install`). Slash-joined; duplicate sibling titles raise `AmbiguousLocatorError`.

**Not built (future):** a raw tree-sitter query string as a power-user escape hatch, and a `kind: "lines"` fallback for non-parseable files. Both were contemplated; neither ships. Bare line ranges remain rejected as a primary surface.

### CLI surface

Path-fragment syntax, delimiter `::` (chosen over `#`/`§`: `#` collides with shell comments and markdown heading anchors):

```
tether add 'src/calc.py::Calculator.multiply' 'docs/calc.md::Usage/Multiply' \
  --description "Doc example must match the method's signature and return shape."
```

- `add` parses a `::selector` suffix on each end; absent ⇒ whole file.
- `update` takes `--a-selector`/`--b-selector` to retarget an existing region without re-fingerprinting. It cannot *add* a locator to a whole-file artifact (there is no locator to retarget) — that is a `rm` + `add`.
- `refs` tolerates a `::selector` suffix but matches by file path only; the selector is ignored (refs is path-scoped).

No new CLI *subcommand*, so `claude_code/settings.py` `ALLOW_SUBCOMMANDS` is unchanged.

## Fingerprint storage: where `region_hash` lives

**Option A — synthetic git blob — is what ships.** The region bytes are written into git's object store via `git hash-object -w --stdin` (`hash_object_write_bytes` in [git.py](../../../tether/git.py)); `region_hash` *is* a blob OID. This keeps the whole diff story for free: `git cat-file -p <region_hash>` retrieves the fingerprinted region, and a `git diff --no-index` of the fingerprinted region against the freshly extracted region produces the unified diff `tether status` ships (`_region_diff` in [status.py](../../../tether/status.py)).

**Known, accepted cost:** these blobs never correspond to a real file, so they are unreachable the moment they are written and subject to git's gc grace period. **Ref-pinning is *not* yet implemented** — it remains the planned hardening ([Future-Work §"Ref-pinning for fingerprint bytes"](../Future-Work.md), `refs/tether/<uuid>-{a,b}`). Region locators make ref-pinning more load-bearing than it was for whole-file tethers (a whole-file fingerprint OID usually matches a real committed blob; a region blob never does), so it is the highest-value follow-up. Until then, `status`/diff degrade gracefully: a gc'd region blob yields a bracketed "(likely git-gc'd)" note rather than a crash.

The rejected alternative — **Option B**, a plain `sha256` content hash with no git object — stays rejected: it loses git's free diff, forcing tether to store and diff the old region bytes itself.

## State model

Scoped to the selected region, not the whole file:

- **HEALTHY** — the locator resolves and `region_hash` matches (or normalization rescues equivalence). Edits elsewhere in the file leave the region HEALTHY.
- **DRIFTED** — the locator resolves but the region's own content changed. `git diff` of fingerprinted-region vs current-region (Option A makes this free).
- **BROKEN** — the file is absent at the recorded path, **or** the locator no longer resolves the region (symbol/heading renamed or removed, selector ambiguous, or the file no longer parses such that the region resolves). All of these collapse to a single `BROKEN` with no distinguishing reason field: `_check_region` catches any `LocatorError` and returns `BROKEN`, never silently falling through to HEALTHY or DRIFTED ([status.py](../../../tether/status.py)). [DICTION-Future](DICTION-Future.md) folds the unresolved case into `BROKEN`; the richer "reason field" once contemplated is not built — region-rename *suggestion* (below) is the diagnostic that would replace it.

## Region rename — the hard problem (still open)

File renames ride git's blob-OID similarity. That is **file-level and does not reach inside a file.** A region artifact's `file_blob_oid` feeds the same file-rename detector as a whole-file artifact, so *moving the whole file* still surfaces a rename candidate. But rename a function or a heading *within* a present file and the selector unresolves → `BROKEN` with **no** candidate: `check_all` only attaches rename candidates when the file itself is missing, and an in-file symbol move leaves the path present.

- **Recovery today:** unresolved ⇒ `BROKEN`; the user repoints with `tether update --a-selector <new>` (or `--b-selector`), then `tether refresh`.
- **Future — best-effort region-rename suggestion.** Among same-kind nodes still present in the file, score each node's body against the fingerprinted region bytes (held via the Option-A synthetic blob) by token/line similarity; surface the best match as a candidate, the direct region-level analog of the file-rename candidate in `check_artifact`. **Not built** — this is the top diagnostic gap, stated explicitly so it is a known limitation, not a silent one.
- **Why deferring this is acceptable for now.** The actor that renames a tethered symbol or heading — a coding agent, or a user editing through one — already holds the context to understand the resulting `BROKEN`: tether injects the region's tether (path, peer, and description) into the agent's context when it *reads* the file (the PreToolUse Read hook), before it decides to rename. So an in-file rename that unresolves is explained at the moment it happens; the in-the-loop editor knows which relationship it just broke and repoints the selector with `tether update --a-selector/--b-selector`. The gap this leaves — a later reviewer or reader who did not make the edit, and the absence of any pointer to the region's *new* location — is precisely what the best-effort suggestion above closes when we return to it.

This differs from [Drift-Cases.md §"Region renamed"](Drift-Cases.md), which presumed a line-range locator stays *resolved* through a rename (reporting `DRIFTED` with an inline diff). A *named* selector unresolves instead — arguably worse default UX, which is exactly why the suggestion mechanism matters.

## Region & normalization semantics

The region hash is stable only because "the region bytes" is defined precisely, per kind:

- **Python symbol:** `node.start_byte .. node.end_byte` — the `def`/`class` line (decorators included) through the last body byte. **No dedent:** a method keeps its indentation under its class, and re-indentation counts as real drift. Leading-tab/trailing-ws/line-ending/BOM/EOF-newline normalization still applies (below).
- **Markdown section:** the heading line through the byte before the next heading of equal-or-higher level (nested subsections included), with the span boundaries derived from heading **levels**, not from `section` nodes (see the substrate section). A sole top-level `# H1` therefore spans the whole document.

[normalize.py](../../../tether/normalize.py) runs **on the extracted region bytes**, after extraction, before hashing — the same passes as for whole files (UTF-8 guard, BOM, line endings, trailing ws, EOF-newline, leading-tab expansion). The normalizer itself is unchanged.

## Parser failure & dependency posture — no silent fallback

tree-sitter + grammars are a hard runtime dependency **for locator-bearing tethers only**; WholeFile tethers stay parser-free. Per the project's no-silent-fallback rule, locator failure never degrades a region tether to whole-file or to HEALTHY — any `LocatorError` (unresolved, ambiguous, or a kind/lang the engine cannot parse) surfaces as `BROKEN` at check time and is raised at `add` time when the region is first fingerprinted.

The finer-grained signals the design once contemplated are **folded into the single `LocatorError → BROKEN` path** rather than split out: there is no separate "unparseable file" state distinct from "selector unresolved," and no "grammar not installed" branch (the python and markdown grammars ship as pinned dependencies, so absence cannot arise for the supported pairings). Splitting these out is only worthwhile once breadth (untrusted/optional grammars) lands.

**Performance:** `status` on whole-file tethers is pure git (`hash-object` + `cat-file`). Region checks parse each locator-bearing file. The `Parser`/`Language` objects are cached (`lru_cache` in [locators.py](../../../tether/locators.py)), but the parsed *tree* is **not** cached across artifacts within a single `status` run — two region tethers on the same file parse it twice. Per-run tree caching keyed by path is the obvious optimization if region tethers proliferate or hook-driven per-Read/per-Stop latency becomes a concern; it is not yet built.

## Code map

Where the feature lives, grounded in the current source:

| Area | File | Role |
| --- | --- | --- |
| Model | [tether/model.py](../../../tether/model.py) | `Locator`, `RegionFingerprint`, optional `locator` on `Artifact`, `file_oid`, `SUPPORTED_LOCATORS`, `schema_version` {1,2}, `validate()` |
| Parsing | [tether/locators.py](../../../tether/locators.py) | Language registry, parser cache, `extract_region` + symbol/heading resolution |
| Git | [tether/git.py](../../../tether/git.py) | `hash_object_write_bytes` / `hash_object_bytes` (synthetic region blob + compare); `cat_blob` for region diffs; `find_renames` (file-level, shared) |
| Drift | [tether/status.py](../../../tether/status.py) | `check_artifact` branches on locator presence; resolve→normalize→hash→compare; unresolved ⇒ BROKEN; region-scoped diff |
| Normalizer | [tether/normalize.py](../../../tether/normalize.py) | Unchanged (operates on the extracted bytes) |
| CLI | [tether/cli.py](../../../tether/cli.py) | `_split_selector` / `_make_locator`; `add` parses `path::selector`; `update --a-selector/--b-selector`; extension→lang map |
| Output | [tether/output.py](../../../tether/output.py), [render.py](../../../tether/render.py), [pretty.py](../../../tether/pretty.py) | Surface locator + region state and region-scoped diffs |
| Agent surface | `tether/claude_code/fragment.py` (the `.tether/tether.md` fragment) + PreToolUse Read-injection | Explain locators / region states to the coding agent |
| Tests | `tests/test_locators.py`, `test_model.py`, `test_status.py`, `test_cli.py` | Resolution, round-trip, state classification, CLI lifecycle |

## Resolved decisions

1. **Selector surface** — symbolic (`Class.method`, `Section/Sub`) is the only surface; a raw tree-sitter query is a deferred escape hatch.
2. **`region_hash` storage** — synthetic git blob (Option A), keeping `git diff` for free. Ref-pinning to handle the GC race is **deferred**, not in this work's scope; the unreachable-blob race is an accepted interim limitation.
3. **Unresolved region** — reuse `BROKEN`, with no reason field; region-rename suggestion (a fast-follow) is the planned richer diagnostic.
4. **Python region indentation** — no dedent; re-indentation counts as real drift. Standard normalization still applies to the extracted bytes.
5. **Markdown nesting** — derived from heading levels, not `section` nodes, so setext and atx are handled uniformly.
6. **Supported pairings** — a `(kind, lang)` set in `model.py`, enforced by `validate()`; crossed pairings fail loud.
7. **Grammar dependency** — explicit per-language deps (`tree-sitter`, `tree-sitter-python`, `tree-sitter-markdown`), pinned.
8. **Fragment delimiter** — `::`.

## Status of the staged plan

1. **Design signed off.** ✅
2. **Vertical slice, Python only** — locator schema + tree-sitter substrate + symbol locator through `add` / `status` / `refresh` / `update`. ✅
3. **Markdown heading locator** — level-based resolution (the `section`-node assumption was tested and rejected for setext). ✅
4. **Region-rename suggestion + richer unresolved diagnostics.** ⬜ Not started — the top follow-up.
5. **Presentation** (output/render/pretty) + agent fragment + Read-injection schema. ✅
6. **Breadth** via `tree-sitter-language-pack` once the two-grammar shape is proven. ⬜ Deferred.

Also outstanding and not on the original staged list: **ref-pinning** the synthetic region blobs (decision 2), and **per-run tree caching** (the performance note above).
