# Competitor Landscape

The tools closest to tether's niche — declared, machine-checkable file relationships with drift detection — surveyed as of June 2026. None combines all of tether's properties (symmetric file pairs, content fingerprints, a required description, refresh as an explicit assertion, agent-loop surfacing), but each occupies an adjacent position. Details below come from web research; star counts and version numbers are point-in-time.

## Fiberplane Drift

**The closest shipped analog.** An open-source CLI "linter for documentation rot." `drift link docs/auth.md src/auth/provider.ts#AuthConfig` inserts an anchor into the markdown file's YAML frontmatter; `drift check` flags staleness in CI. Each anchor records a `sig` — a normalized AST fingerprint computed with tree-sitter (node kinds + token text, whitespace/position stripped) for TypeScript, Python, Rust, Go, Zig, and Java — plus optional provenance (`@<git-sha>` of the commit that last addressed the anchor). Ships a Claude Code agent skill so agents re-stamp anchors as they change code; a CI gate blocks merges on stale docs. Launched ~June 2026, actively developed.

**Delta vs tether:** directionally the same idea (fingerprint at link time, deterministic compare, deliberate re-stamp), but asymmetric (the doc anchors the code; the code side carries nothing), anchors live inside the doc's frontmatter rather than in standalone committed records, AST fingerprints instead of git blob OIDs (syntax-aware but parser-bound), symbol granularity, no required "why" description, and no rename-detection story.

- Repo: <https://github.com/fiberplane/drift>
- Announcement: <https://fiberplane.com/blog/drift-documentation-linter/>

## VeriContext

**The closest mechanism match, at micro scale.** "Deterministic, hash-based verification for docs that reference code. Fail-closed. Zero fuzzy matching." Embeds truncated SHA-256 hashes of file/line-range content into inline doc citations (`[[vctx:src/cli.ts#L1-L10@a1b2c3d4]]`). CLI plus an MCP server aimed explicitly at AI agents (Claude Code, Cursor, Codex); `verify` exits non-zero on any mismatch. Tiny and very new (npm, ~7 stars, ~11 commits, Feb 2026), but it independently validates the thesis of hash-pinned references for agent context.

**Delta vs tether:** asymmetric (doc cites code), hashes live inline in the doc body rather than as link records, no refresh-as-assertion (stale citations are manually regenerated via `cite`), no descriptions, no rename detection, no state model beyond pass/fail.

- Repo: <https://github.com/amsminn/vericontext>
- Announcement: <https://community.openai.com/t/show-preventing-doc-drift-in-agentic-coding-workflows/1375031>

## spec-kit-sync

**The LLM-judgment approach to the same problem.** A community extension to GitHub Spec Kit (~20 stars, MIT) that detects drift between specs and implementation and routes each finding to one of four resolutions: backfill, align, supersede, or human review. Spec Kit's own `/speckit.analyze` only checks consistency *among spec artifacts* (spec.md vs plan.md vs tasks.md); spec-kit-sync extends the check to spec↔code.

**Delta vs tether:** no declared links and no fingerprints — drift is re-derived by asking the model on every run, so detection is probabilistic, recall-limited, and has no durable per-relationship state, no audit trail, and no assertion act. Its existence is demand evidence: Spec Kit users want spec↔code drift detection badly enough to bolt it on.

- Repo: <https://github.com/bgervin/spec-kit-sync>
- Spec Kit (host project): <https://github.com/github/spec-kit>

## LINT.IfChange / ThenChange ("IfThisThenThat")

**The battle-tested ancestor, stateless by design.** Google's comment-annotation convention: wrap a region in `// LINT.IfChange` … `// LINT.ThenChange(path#label)`, and a presubmit check warns (in Gerrit) when a change touches the guarded region but not the named target. Chromium's tree reportedly carries 1,100+ directives; Fuchsia runs an equivalent presubmit.

The mechanism is **diff-scoped, not content-hashed**: the check only asks "did the other file also appear in this same diff?" There is no persistent state, so any touch of the target satisfies the check (rubber-stamp-by-touch), drift introduced across separate commits is invisible, and there is no `status` outside a pending diff. Documented pain points: rename + edit in one commit defeats it, stale `ThenChange` paths rot silently, and directives are bypassable warnings.

Open-source reimplementations (all small, all diff-based):

- [simonepri/ifttt-lint](https://github.com/simonepri/ifttt-lint) — Rust; labels, 44+ comment styles, reverse-lookup for stale references.
- [slnc/ifchange](https://github.com/slnc/ifchange) — Rust; shipped on crates.io/npm/PyPI with GitHub Actions and pre-commit integrations; notably publishes recommended practices for AI coding agents.
- [ebrevdo/ifttt-lint](https://github.com/ebrevdo/ifttt-lint) — TypeScript; the older reimplementation.

**Delta vs tether:** declared links at finer (region) granularity and proven at monorepo scale, but no fingerprints, no cross-commit drift detection, no descriptions, no symmetric state model, and links live as comments inside source files rather than as reviewable records.

- ChromiumOS guide: <https://www.chromium.org/chromium-os/developer-library/guides/development/keep-files-in-sync/>
- Fuchsia presubmit checks: <https://fuchsia.dev/fuchsia-src/development/source_code/presubmit_checks>

## Summary

| | Declared link | Content fingerprint | Symmetric | Required "why" | Re-assert act | Agent integration | Rename handling |
|---|---|---|---|---|---|---|---|
| Fiberplane Drift | ✓ | ✓ (AST sig) | ✗ (doc→code) | ✗ | ✓ (re-stamp) | ✓ (CC skill, CI) | ✗ |
| VeriContext | ✓ | ✓ (SHA-256 inline) | ✗ (doc→code) | ✗ | ✗ (regenerate) | ✓ (MCP) | ✗ |
| spec-kit-sync | ✗ (inferred per run) | ✗ | ✗ (spec→code) | ✗ | ✗ | ✓ (Spec Kit workflow) | ✗ |
| LINT.IfChange | ✓ (in-source comments) | ✗ (diff-scoped) | ~ (can be mutual) | ✗ | ✗ (touch suffices) | ~ (presubmit; one clone targets agents) | ✗ |
| **tether** | ✓ (committed JSON) | ✓ (git blob OID) | ✓ | ✓ | ✓ (`tether refresh`) | ✓ (hooks + fragment) | ✓ (git similarity) |

Watch list: Fiberplane Drift is the competitor to track — same thesis, shipped first, agent-skill distribution, a company behind it. LINT.IfChange's clones turning toward agent workflows suggest the stateless approach will also contest the niche.
