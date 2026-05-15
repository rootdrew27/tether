---
title: Drift normalization
tags:
  - design
  - normalization
type: design
status: active
---

This document specifies the comparison-time normalizer that tether applies when raw region hashes disagree. The high-level rationale lives in [[Tether-Design-MVP]] under §"Equivalence and drift normalization"; this doc covers the algorithm, the pipeline, configuration, and v1's deliberate non-goals.

## Flow

The locator always resolves on raw on-disk bytes; line numbers and offsets refer to actual file content. Normalization only runs after raw hashes already disagree:

1. The locator resolves on raw on-disk bytes.
2. Tether computes the current region's hash and compares it to the fingerprinted region hash.
3. If they match, the artifact is HEALTHY.
4. If they don't match, tether fetches the fingerprinted bytes from git's object store via `git cat-file blob`, runs both sides through the normalizer, and compares normalized hashes.
5. If normalized hashes match, the artifact is HEALTHY. `tether status` notes that only encoding-level changes were detected and still surfaces the raw diff — the drift signal is preserved at the diff level, only the state value is rescued.
6. If normalized hashes also disagree, the artifact is DRIFTED and the raw diff is reported as before.

## Pipeline (v1, language-agnostic)

Applied identically to both sides of the comparison:

1. **Binary guard.** If either side fails UTF-8 decode, normalization is skipped; the artifact is DRIFTED.
2. **Decode and strip BOM.** UTF-8 with and without BOM compare equal.
3. **Line endings.** CRLF and lone CR fold to LF.
4. **Trailing whitespace.** Stripped per line.
5. **EOF newline.** Trailing blank lines are collapsed; exactly one terminating LF, unless the region was extracted mid-line.
6. **Leading-tab expansion.** Each leading `\t` becomes N spaces; tabstop is configurable (default 8) and `.editorconfig` is honored when present. Internal whitespace is left untouched.

The pipeline is **per-region and locator-agnostic**: it is applied to whatever bytes the locator extracted, regardless of how the locator identified them. A `WholeFile` artifact normalizes the whole file; a `LineRange` artifact normalizes the extracted line range; a future AST-aware locator will normalize the bytes it identifies. Adding a new locator type does not require teaching the normalizer anything.

## Deliberate non-goals (v1)

The pipeline is conservative. It catches the encoding-level changes that produce false drift in practice — formatter passes, editor settings, line-ending mismatches — without crossing into territory that requires a parser to be safe. Two cases v1 explicitly does *not* normalize, even though they are often "just whitespace":

- **Indent-width changes** (2-space ↔ 4-space). Catching these requires detecting the file's indent unit, which is a language-aware heuristic. v1 leaves them as DRIFTED.
- **Internal whitespace** (`a+b` ↔ `a + b`). Collapsing internal whitespace silently breaks string-literal semantics (`"hello  world"` is not `"hello world"`); doing this safely requires lexing the file. v1 leaves them as DRIFTED.

Both belong on the language-aware tier; see *Looking forward* in [[Tether-Design-MVP]].

## Configuration

MVP uses a fixed tabstop of 8 (compiled-in default). Per-project and per-file configurability are deferred to v1.5; see [[Future-Work]] §"Normalizer extensions" for the planned surface:

- `normalize.tabstop` (integer, default 8) in `.tether/config.json` — width to expand each leading `\t` to.
- `.editorconfig` (when present at the file's path) — honored for `tab_width` and `indent_style` / `indent_size`. Per-file overrides take precedence over the project-level tabstop.

Both arrive together because the renderer in `.tether/config.json` is the natural place to opt into `.editorconfig` discovery (and to disable it for projects where it would produce surprising results).
