---
title: Design research
tags:
  - research
  - design
type: research
status: pre-mvp-research
---

> [!info]+ Pre-MVP exploration
> Early survey of comparable systems and design options; written before the MVP spec was committed. Some recommendations made it into MVP (per-tether JSON files under `.tether/tethers/`, UUIDv7 IDs, CLI + Python API split), others did not (free-form type strings — MVP uses a closed vocabulary; `watchdog`-based file watching — MVP has no watcher; markdown-frontmatter secondary surface — not in MVP; content-hash rolling rename detection — MVP uses git's `find-object`). "Already locked in" notes scattered through this doc reflect mid-exploration decisions, not all of which survived. The current design lives in [[Tether-Design-MVP]] and the deferred catalog in [[Future-Work]].

Research document for the tether tethering system. Covers four areas: similar systems, git-committable metadata storage, link type taxonomies, and file-watching strategies.

---

## 1. Similar / related systems

### PKM / note-linking ecosystem

**Obsidian.** Links are untyped `[[wikilink]]` or standard markdown links written *inline* in markdown text; the file itself is the authoritative record. Backlinks and the graph view are computed in memory from a metadata cache and are not persisted to disk in user-readable form. Wikilinks can omit the `.md` extension and work bidirectionally by virtue of the backlink index; there is no separate "bidirectional flag" concept ([Obsidian Forum - Internal Links and Backlinks](https://forum.obsidian.md/t/convert-wikilinks-to-markdown-links/48339), [DeepWiki - Internal Links and Backlinks](https://deepwiki.com/victor-software-house/obsidian-help/3.1-internal-links-and-backlinks)). Obsidian automatically rewrites wikilinks when a file is renamed *inside Obsidian*, but renames that happen outside the app (e.g., via git, VSCode, or CLI) break links and the user must either manually repair or re-open with Obsidian running. Links are not natively typed; typing comes from plugins (see section 3).

**Logseq.** Historically stored graphs as a directory of markdown/org files with a `logseq/` config subfolder, but the current "DB graph" format uses SQLite (DataScript persisted to SQLite) as the primary store with supplementary `logseq/config.edn` and `logseq/custom.css` files ([Logseq DeepWiki - Repository and Graph Management](https://deepwiki.com/logseq/logseq/4.3-repository-and-graph-management), [Logseq Discuss - DB FAQ](https://discuss.logseq.com/t/logseq-db-unofficial-faq/32508)). This means newer Logseq graphs are *not* directly git-reviewable the way pure markdown is. Links between blocks use UUIDs rather than paths, which solves rename-tracking but makes diffs opaque.

**Dendron.** Hierarchy is encoded *in the filename* via dot delimiters: `project1.designs.promotion.md` is a child of `project1.designs.md` ([Dendron Wiki - Hierarchies](https://wiki.dendron.so/notes/f3a41725-c5e5-4851-a6ed-5f541054d409/), [Johnny.Decimal Forum](https://forum.johnnydecimal.com/t/dendrons-hierarchical-note-filename-format/532)). Vaults are backed by git by design. Links are untyped `[[wikilinks]]`; the typed dimension comes from the schema system described in section 3. Renames happen via rename commands that rewrite affected filenames and inbound links atomically.

**Foam.** Pure markdown + wikilinks in VSCode; backlinks are computed in memory and shown in a panel. Has a proposed-but-not-implemented "materialized backlinks" feature to write backlink lists into the bottom of each markdown file ([Foam materialized-backlinks proposal](https://github.com/foambubble/foam/blob/main/docs/dev/proposals/materialized-backlinks.md)). As of the docs examined, Foam commits essentially nothing but the user's markdown and an optional `.foam/` config; no graph cache is checked in.

**Roam Research.** Hosted service with proprietary block-based storage; not directly comparable for git-committable design but influential as the origin of bidirectional-by-default thinking in modern PKM.

**SilverBullet.md.** Markdown is the source of truth, with tags and frontmatter adding typed attributes. Objects (pages, tasks, items) are indexed from markdown; the index can be flushed and rebuilt from source files at any time ([SilverBullet - Metadata](https://silverbullet.md/Metadata), [SilverBullet - Objects](https://silverbullet.md/Objects)). Git integration is provided via an auto-commit/auto-sync plug. Links become navigable both ways because the indexer reads all pages and materializes a link table in a transient index ([SilverBullet - Link](https://v2.silverbullet.md/Link)).

**org-roam.** Source of truth is org-mode plain-text files; a SQLite cache at `~/.emacs.d/org-roam.db` holds nodes, links, aliases, tags, refs, citations, seven tables total ([org-roam manual](https://www.orgroam.com/manual.html), [DeepWiki org-roam](https://deepwiki.com/org-roam/org-roam)). Links use Org's native `id:` links which reference stable node IDs rather than file paths, so file renames do not break links. The SQLite cache is explicitly not committed and is rebuilt on demand.

**Pattern across PKM tools:** the consensus is *markdown + wikilinks are the source of truth; indexes are ephemeral*. Typing is either absent or bolted on via plugins. Rename safety ranges from "fragile, relies on being open" (Obsidian) to "rock solid, uses stable IDs" (org-roam, Logseq DB).

### Software traceability (DOORS / Jama / OSLC)

**IBM DOORS Next.** Ships predefined link types per project template: `Tracked by`, `Validated by`, `Embeds`, `Constrains / Constrained By`, `Validated By / Validates`, plus user-defined ones like `Satisfy` ([Softacus - Link Types in DOORS Next](https://softacus.com/blog/basics-of-links-and-link-types-in-ibm-doors-next-generation)). Links are directional with distinct incoming and outgoing labels (for example, A "satisfies" B while B "is satisfied by" A). Custom types can be defined by project admins with URIs assigned.

**OSLC (Open Services for Lifecycle Collaboration).** An open spec for cross-tool links. Standardizes `Validated By` and similar as URI-identified link types so that artifacts in different tools can reference each other without data duplication ([OSLC - open-services.net](https://open-services.net/), [Jama - What is OSLC](https://www.jamasoftware.com/blog/oslc-what-is-it-and-what-are-its-challenges/)). Every link type has a URI; this is the pattern tether could draw from if it ever wanted a canonical vocabulary.

**Jama Connect.** Pre-configured schemas in Traceable MBSE govern which element types can link to which, and the system auto-picks the correct relationship name (e.g., `satisfies`, `validates`) based on the two artifact types being connected ([Jama - Traceable MBSE](https://www.jamasoftware.com/blog/jama-connect-for-traceable-mbse-the-chameleon/)).

**Academic traceability research.** Long history of *recovering* trace links via information retrieval (LSI, BM25, more recently LLMs) between documentation and code. Recent work explicitly enumerates relationship types like "describes configuration of" and "provides default value for" rather than plain binary links ([Evaluating LLMs for Doc-to-Code Traceability (arXiv 2506.16440)](https://arxiv.org/html/2506.16440v1), [Recovering Trace Links ICSE paper](https://dl.acm.org/doi/10.1145/3597503.3639130)). The canonical link-type list derived from this literature: `satisfies`, `verifies`, `derives-from`, `allocates`, `refines`, `trace` (generic catch-all) ([ReqView - Traceability Links](https://www.reqview.com/doc/requirements-traceability-links/)).

In traceability tooling, links are **typed and directional by default** and the UI always exposes both direction labels. This is a meaningful divergence from the PKM world.

### Code-doc sync (Doxygen, Sphinx autodoc, JSDoc, literate programming)

These systems do not store *explicit link records*. Instead, they derive the doc-to-code relationship from the *location of the docstring*: Sphinx `autodoc` introspects Python modules, Doxygen parses C++ comments, JSDoc parses JS comments, `sphinx-js` and `Breathe` bridge those into reStructuredText ([Sphinx autodoc docs](https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html), [Breathe](https://breathe.readthedocs.io/)). The link is implicit and 1:1: this docstring describes this function. There is no many-to-many, no directional typing, no "this test verifies that requirement" — those would need a separate system.

**Literate programming (Knuth's WEB; org-babel).** Uses a single source file that is *tangled* into code and *woven* into documentation ([Literate Programming - Wikipedia](https://en.wikipedia.org/wiki/Literate_programming), [Org-babel intro](https://orgmode.org/worg/org-contrib/babel/intro.html)). The "link" is physical co-location in the same source file with named code chunks. Not a model tether is likely to adopt, but interesting as a "links are eliminated by unifying the artifacts" counter-design.

### Monorepo dependency graphs (Bazel, Nx, Turborepo)

**Bazel.** Dependencies are stated explicitly in `BUILD`/`BUILD.bazel` files using `deps = [...]` lists on targets. Bazel caches the full dependency graph between invocations and reanalyzes only changed packages ([Bazel - Dependencies](https://bazel.build/concepts/dependencies), [Bazel - Review dependency graph](https://bazel.build/tutorials/cpp-dependency)). BUILD files are committed to git and are human-readable, which is the closest analogue to tether's "git-committable tether metadata" requirement.

**Nx.** The project graph is cached in `node_modules/.cache/nx/nxdeps.json` and is *not* committed — it is regenerated by static analysis of imports ([Nx - Mental Model](https://nx.dev/docs/concepts/mental-model), [Nx - Explore Graph](https://nx.dev/docs/features/explore-graph)). `nx.json` at the repo root is committed and holds cross-project task defaults and pipeline config.

**Turborepo.** `turbo.json` at the repo root is committed and defines the *task graph* via the `tasks` object, with `^` syntax meaning "run this in dependencies first" ([Turborepo - Package and Task Graph](https://turborepo.dev/docs/core-concepts/package-and-task-graph), [Turborepo - Configuring Tasks](https://turborepo.dev/docs/crafting-your-repository/configuring-tasks)). Package dependencies come from `package.json` files; Turborepo does not invent a separate dependency file.

**Takeaway for tether:** The monorepo world has converged on *a single committed JSON/JSON-like file at the repo root* for task/pipeline configuration (`turbo.json`, `nx.json`) plus *per-package files* for per-package specifics (`package.json`, `BUILD`). Both are human-reviewable in PRs. This is a strong precedent.

### Link checkers

**lychee** and **markdown-link-check** both walk markdown/HTML files and probe each URL. Neither natively handles renames — when a link breaks because its target was renamed, they report the break but leave the repair to the user or a separate tool ([lychee GitHub](https://github.com/lycheeverse/lychee), [lychee docs](https://lychee.cli.rs/)). Rename detection is out of their scope; they are verifiers, not link stores.

### obsidian-cli (and community variants)

As of February 2026, Obsidian ships an **official CLI** built into the app itself, with commands for daily notes, file I/O, search (with `format=json`), metadata inspection, and more ([Obsidian CLI](https://obsidian.md/cli), [Obsidian Help - CLI](https://help.obsidian.md/cli)). Key design notes:

- "Remote control" model: every operation goes through the running Obsidian app's API so link rewriting and indexing stay consistent ([DEV - Obsidian Official CLI](https://dev.to/shimo4228/obsidians-official-cli-is-here-no-more-hacking-your-vault-from-the-back-door-3123)).
- Parameters use `key=value` style, flags are bare words (no `--`), except `--copy` for clipboard.
- `format=json` produces structured output for scripts; interactive TUI mode with autocomplete and history for humans.
- Obsidian-internal bulk processing is slow at scale; community recommendation is "use the CLI for targeted ops, Python scripts for bulk" ([XDA - Python scripts for Obsidian](https://www.xda-developers.com/these-python-scripts-will-supercharge-your-obsidian-vault/)).

The **community `obsidian-cli` Python tool** ([jwhonce/obsidian-cli on PyPI](https://pypi.org/project/obsidian-cli/)) exposes a CLI *plus* an MCP server for AI assistants, which is a direct parallel to tether's "Python API for LLMs + CLI for humans" requirement. It reads and writes markdown files directly rather than via the app.

**Relevance to tether:** the pattern "operations are defined once in a core library and exposed through both a CLI and a Python/MCP surface, with JSON output whenever non-TTY" is already a well-trodden path.

---

## 2. Git-committable metadata storage (deep dive)

This is the section that most directly drives the MVP. Below are the five candidate storage shapes with concrete assessments.

### Option A: single JSON/YAML file at project root

```
project/
  tethers.json            # or tethers.yaml
```

- **Merge conflicts:** frequent. Any two branches that add a tether conflict on array tail or object ordering. YAML flow-style or sorted-key JSON mitigate this but do not eliminate it. Semantic merge tools for JSON help but are not universal.
- **Diff readability:** high if the file is pretty-printed and keys are sorted. A PR reviewer sees every change in one place.
- **Scalability:** a single file with thousands of tether records stays parseable (JSON parsers handle multi-MB easily) but individual editing becomes unwieldy and git line-based diffs get noisy when serialization is not stable.
- **Rename survival:** tethers reference `src` and `dst` by path; a rename has to rewrite every reference. Because all references are in one file, a single atomic edit fixes them all. Good.
- **Precedent:** Turborepo's `turbo.json`, Nx's `nx.json` (but they hold config, not a growing list). Closer parallel: `package-lock.json` which everyone hates for merge conflicts.

### Option B: directory of per-tether files

```
project/
  .tether/
    tethers/
      abc123.json
      def456.json
```

- **Merge conflicts:** rare. Two branches adding tethers almost never touch the same file. Editing the same tether on both branches still conflicts, but that is a semantically real conflict.
- **Diff readability:** each tether's lifecycle is visible as a single file's history (`git log .tether/tethers/abc123.json`). Excellent for PR review.
- **Scalability:** thousands of small files are fine on modern filesystems but slow some tools (git status gets chattier). Still acceptable into the low tens of thousands.
- **Rename survival:** a rename rewrites the `src` or `dst` field inside each affected tether file. The touched files are exactly the affected tethers, which is good locality.
- **File ID choice:** random UUID or content-hash of the tether fields. UUID is simpler; content hash risks changing on edit.
- **Precedent:** `.github/workflows/*.yml`, `k8s/manifests/*.yaml`. Dendron-style "one thing per file."

### Option C: sidecar per tethered file

```
project/
  src/
    foo.py
    foo.py.tether.json
  docs/
    bar.md
    bar.md.tether.json
```

- **Merge conflicts:** moderate. If two PRs add tethers involving `foo.py`, both modify `foo.py.tether.json`. Less bad than option A.
- **Diff readability:** local; reviewer sees tethers next to the file they concern.
- **Scalability:** one extra file per tethered file. Clutters listings but no global bottleneck.
- **Rename survival:** *poor*. Renaming `foo.py` to `qux.py` must also rename the sidecar, and every *other* sidecar that references `foo.py` must be rewritten. The sidecar is at the *wrong granularity* because tethers are n:m — each tether has two endpoints and can only live next to one of them. This means either each tether is duplicated in two sidecars (consistency nightmare) or the sidecar only records outgoing links (reverse lookup becomes a full scan).
- **Precedent:** `.xmp` files for photos, `.meta` files in Unity. Works where the relationship is 1:1 between asset and metadata, which is not tether's case.

### Option D: frontmatter embedded in files (markdown only)

```markdown
---
tethers:
  - to: src/foo.py
    type: describes
    bidirectional: true
---
```

- **Merge conflicts:** moderate.
- **Diff readability:** good for markdown reviewers, invisible if the reviewer doesn't scroll to the top.
- **Scalability:** fine.
- **Rename survival:** same problem as sidecars. If a target file is renamed, every frontmatter referencing it must be rewritten. Because frontmatter lives in the referencing file, this is at least not cross-file; but it also only works when *both endpoints are markdown*.
- **Hard blocker:** tether tethers both code and docs. Python/TypeScript/etc. do not have a standard frontmatter convention. This option cannot be the primary format; at best it's an additional surface layer for markdown files, where authors can optionally express tethers inline and the daemon syncs them to the canonical store.
- **Precedent:** Jekyll, Hugo, most static site generators; Dataview inline `[field:: value]` in Obsidian ([Dataview docs](https://blacksmithgu.github.io/obsidian-dataview/)); Dendron schemas; SilverBullet attributes ([SilverBullet - Attributes](https://v2.silverbullet.md/Attributes)).

### Option E: Dolt (git-for-SQLite)

Dolt is a SQL database with Git semantics: branch, merge, diff at the cell level, backed by Prolly Trees ([Dolt - Git for Data](https://docs.dolthub.com/introduction/getting-started/git-for-data), [DoltLite](https://www.dolthub.com/blog/2026-03-25-doltlite/)). It solves the "schema + diffable" tension: you have a real schema, primary keys are stable across renames, and cell-level diffs are meaningful for PR review.

- **Merge conflicts:** real 3-way cell-level merges, much better than JSON text merges.
- **Diff readability:** requires `dolt diff` rather than standard `git diff`; GitHub does not render this.
- **Scalability:** designed for datasets much larger than tether will ever produce.
- **Rename survival:** excellent with stable primary keys.
- **Reviewability in PRs:** **this is the killer problem.** GitHub/GitLab PR UIs cannot show Dolt diffs. Reviewers would have to clone and run `dolt diff` themselves. For a hobbyist-tool MVP with humans-review-in-PRs as a requirement, this disqualifies Dolt.
- **Operational weight:** requires Dolt as a runtime dependency, a much heavier ask than "reads a JSON file" for a Python project.

### Comparison table

| Option | Merge conflicts | PR diff review | Scalability (10k tethers) | Rename resilience | Code + docs | Setup cost |
|---|---|---|---|---|---|---|
| A. Single root file | High | Excellent (one place) | OK (large diffs) | Good (atomic edit) | Yes | Trivial |
| B. Per-tether files | Low | Excellent (per-file history) | Very good | Good | Yes | Trivial |
| C. Sidecar per file | Moderate | Local but scattered | Good | Poor (many refs) | Awkward | Trivial |
| D. Frontmatter | Moderate | Good for md only | Good | Poor (cross-file) | Markdown only | Trivial |
| E. Dolt | Excellent | Terrible (no GitHub render) | Excellent | Excellent | Yes | Heavy |

### What real tools commit

- **Foam:** user's markdown and an optional `.foam/` config. No graph cache, no link index, by design ([Foam GitHub](https://github.com/foambubble/foam)).
- **Dendron:** plain markdown with dot-delimited filenames plus optional `{name}.schema.yml` files in the vault ([Dendron Schemas](https://wiki.dendron.so/notes/c5e5adde-5459-409b-b34d-a0d75cbb1052/)). Git-friendly by design.
- **SilverBullet:** plain markdown with YAML frontmatter; index is transient and rebuilt from markdown ([SilverBullet - Objects](https://silverbullet.md/Objects)).
- **org-roam:** plain org files. SQLite cache explicitly not committed.
- **Obsidian:** markdown only (with wikilinks). `.obsidian/` config is per-repo choice.
- **Bazel:** `BUILD` files committed, everything else ephemeral.

The overwhelming consensus: **the source-of-truth is human-readable text files; derived indexes stay local.**

### Recommendation for tether (primary storage)

**Option B (directory of per-tether JSON files under `.tether/tethers/`) is the strongest fit** for this project's constraints:

- Minimizes merge conflicts in the expected "multiple contributors add tethers in parallel" workflow.
- Each tether has its own git history, making `git blame` and `git log` useful.
- Easy to review in PRs: a new tether is a new file; reviewers see one file per tether in the diff.
- Survives renames with a focused edit: one pass over the tether files that reference the renamed path.
- Natural home for `bidirectional: true` as a flag on a single JSON object (matches the locked-in design decision).
- Python `json.dump(sort_keys=True, indent=2)` gives stable serialization out of the box.

**Shape suggestion (illustrative, not prescriptive):**

```
.tether/
  config.json                    # global config (event filters, rename window, etc.)
  tethers/
    {id}.json                    # one tether per file
  renames.log.jsonl              # append-only rename history for audit (optional)
```

**Open design questions that remain:**
- Tether ID generation: UUIDv7 (time-ordered, sortable) vs content hash vs human-assigned slug?
- One file per tether vs one file per (src, dst) pair collapsing multiple typed relationships? Start with one file per tether, simpler.
- Allow/require a hand-written ID for human-created tethers, auto-generate for LLM-created? Worth user input.

Secondary surface: optionally support frontmatter on markdown files as a convenience for human authors, with the daemon syncing frontmatter entries into the canonical `.tether/tethers/` store on save. This matches the SilverBullet model of "markdown is the friendly surface; the index is derived" ([SilverBullet - Metadata](https://silverbullet.md/Metadata)).

---

## 3. Link type taxonomies

### Existing vocabularies

**Obsidian plugin conventions.** Core Obsidian has no typed links. Plugins have converged on two competing inline syntaxes:

- **Dataview inline fields**: `[key:: [[target]]]` or `key:: [[target]]` at the start of a line. Works because Dataview parses the entire vault and indexes these. No multi-word link types in line-leading form without brackets ([Dataview Inline Fields](https://blacksmithgu.github.io/obsidian-dataview/)).
- **Juggl list syntax**: `- linkType [[target]]` with the constraint that `linkType` must be a single word ([Juggl Link Types](https://juggl.io/link-types.html)).
- **Breadcrumbs plugin** recognizes Dataview-style typed links and builds hierarchy traversal from them.

Emerging convention in Obsidian world: typed links are *a key-value pair where the key is the type and the value is the wikilink target*. This maps cleanly to tether's `{type: "describes", src: ..., dst: ...}` model.

**Dendron schema system.** YAML files named `{name}.schema.yml` define which note names are valid children of which parents, using a tree of `{id, parent, children, namespace, pattern, template}` objects ([Dendron - Schemas](https://wiki.dendron.so/notes/c5e5adde-5459-409b-b34d-a0d75cbb1052/)). This types the *hierarchy*, not arbitrary links; it is closer to a directory-structure schema than to a link-type vocabulary. Not directly applicable to tether's directional typed links, but the YAML/hierarchical approach is a good model for "optional type system" positioning.

**Requirements traceability types.** The standard vocabulary, drawn from SysML, IBM DOORS, Jama, and ReqView:

- `satisfies` / `is satisfied by` — design/implementation satisfies requirement
- `verifies` / `is verified by` — test verifies requirement
- `validates` / `is validated by` — test validates need (distinct from verifies in some tools)
- `derives-from` / `derives` — one requirement derived from another
- `refines` / `is refined by` — detail elaboration
- `allocates` / `is allocated to` — flow-down to product structure
- `constrains` / `is constrained by`
- `trace` — generic catch-all

([ReqView - Traceability Links](https://www.reqview.com/doc/requirements-traceability-links/), [Softacus - DOORS Link Types](https://softacus.com/blog/basics-of-links-and-link-types-in-ibm-doors-next-generation)). Every typed link has an explicit forward-label and reverse-label — consistent with tether's directional design.

**OSLC link types.** URI-identified link types (every type is a URL) for cross-tool linking ([open-services.net](https://open-services.net/)). tether probably does not need URIs in MVP, but it is worth leaving room to later add a `uri` or `namespace` field so teams can namespace their link vocabulary.

**Semantic web / SKOS / Dublin Core.** SKOS defines `skos:broader`, `skos:narrower`, `skos:related`, plus mapping relations `skos:exactMatch`, `skos:closeMatch`, `skos:narrowMatch`, `skos:broaderMatch`, `skos:relatedMatch` ([SKOS Core Guide](https://www.w3.org/2004/02/skos/core/guide/2004-10-22.html)). Dublin Core Terms adds `dc:relation`, `dc:source`, `dc:references`, `dc:isReferencedBy`, `dc:requires`, `dc:isRequiredBy`, `dc:replaces`, `dc:isReplacedBy` ([DCMI Metadata Basics](https://www.dublincore.org/resources/metadata-basics/)). These are very generic but establish that "directional relations with paired forward/reverse labels" is a decades-old pattern, not a new invention.

### Is there a canonical "doc-to-code" vocabulary?

**No, there is not.** The academic traceability literature proposes specific relationship types ("describes configuration of", "provides default value for") but there is no broadly adopted standard ([arXiv 2506.16440](https://arxiv.org/html/2506.16440v1)). Requirements-side standards (satisfies/verifies) assume requirements documents; doc-side standards (Dublin Core) are too generic. This is genuinely open territory and tether is free to propose something.

### Suggested starter vocabulary for tether

Keep the type field a free-form string (as already decided), but ship with recommended conventions. Below is a starter set chosen for the doc-and-code scope, blending traceability and PKM traditions. Lowercase-kebab-case for easy typing.

**Primary types (doc and code):**
- `describes` — doc describes code (markdown notes, conceptual docs explaining a module)
- `specifies` — doc states contract/requirement that code must meet
- `implements` — code implements what a doc specifies
- `tests` — code is a test for another file (test-to-code, not test-to-spec)
- `verifies` — test verifies a doc-stated requirement
- `documents-api-of` — doc is the reference docs for the code
- `example-of` — one file is an illustrative example of what another defines
- `depends-on` — file imports, extends, or is logically required by another
- `supersedes` — this file obsoletes another (for tracking historical replacement)

**Generic:**
- `related` — a generic catch-all with no direction semantics implied (use sparingly)
- `see-also` — reference for humans, weak semantics

**Meta types (about the tethering itself):**
- `tracks-rename-of` — system-generated, marks a tether updated after a rename

**Conventions to document:**
- Type is a string; lowercase-kebab-case recommended.
- For bidirectional links with a clear asymmetric label, pick the direction that reads naturally forward (e.g., `implements` with `bidirectional: true` reads "A implements B, B is implemented by A").
- For strictly symmetric relations, use `related` or `see-also`.
- Reserve a `x-` prefix for user-defined types to reduce risk of future collision with built-in vocabulary expansion.

---

## 4. `watchdog` vs inotify (deep dive)

### Python `watchdog`

Cross-platform wrapper that selects the best backend per OS at runtime ([watchdog on PyPI](https://pypi.org/project/watchdog/), [watchdog on GitHub](https://github.com/gorakhargosh/watchdog)):

- **Linux:** `inotify` via `InotifyObserver`
- **macOS:** `FSEvents` preferred, falls back to `kqueue`, then to polling
- **BSD:** `kqueue`
- **Windows:** `ReadDirectoryChangesW`
- **Last resort on all platforms:** `PollingObserver`

Watchdog is mature: 6.0 released November 2024, 155 contributors, 7k+ stars. Supports Python 3.9+. Apache 2.0 licensed.

**Known caveats:**
- **kqueue uses one file descriptor per watched file/dir.** Official documentation explicitly warns "kqueue is not a very scalable way to monitor a deeply nested directory of files and directories with a large number of files" ([watchdog kqueue source](https://github.com/gorakhargosh/watchdog/blob/master/src/watchdog/observers/kqueue.py)).
- **Polling fallback is slow:** it snapshots directory trees periodically. Acceptable only for small trees or when nothing else works.
- **Event coalescing:** rapid-fire modifications can produce one event or many depending on backend. tether's "noisy by design" MVP is fine with this; a future debouncing layer belongs in the core, not in the watcher.
- **Recursive watching on Linux still consumes one inotify watch per directory**, inheriting inotify's `max_user_watches` constraint.

**API quality:** synchronous observer/handler pattern (`Observer().schedule(handler, path, recursive=True)`). No built-in async interface. Reasonable for a daemon built around a thread or event loop bridge.

### Linux inotify directly

**Limits ([watchexec inotify limits](https://watchexec.github.io/docs/inotify-limits.html), [JetBrains - Inotify Watches Limit](https://intellij-support.jetbrains.com/hc/en-us/articles/15268113529362-Inotify-Watches-Limit-Linux)):**

- `fs.inotify.max_user_watches`: default 8192 on most distros, often raised to 65536 or higher by IDE installers. *Per user, shared across all processes.*
- `fs.inotify.max_user_instances`: default 128.
- `fs.inotify.max_queued_events`: default 16384.
- Memory: ~540 bytes per watch on 32-bit, ~1080 bytes on 64-bit, unswappable kernel memory.
- **Recursive watching is not native.** Linux inotify watches one directory; recursion means one watch per subdirectory, traversed and set up manually.

**Practical implication for tether:** a project with 5,000 directories (e.g., `node_modules` included) hits the default limit. Either exclude noisy directories (`.git`, `node_modules`, `__pycache__`, `.venv`, `dist`, `build`) or document how to raise `max_user_watches`. Both watchdog and direct inotify have the same constraint here.

### Python inotify libraries

| Library | Async support | Maintenance (as of 2026) | API quality notes |
|---|---|---|---|
| `inotify_simple` | No (subclasses `FileIO`, blocking) | Maintained but less active | Close to raw syscalls; simple for sync code |
| `pyinotify` | No; assumes UTF-8 filesystem encoding | Largely unmaintained | Avoid for new code |
| `asyncinotify` | Yes, also optional sync iteration | Actively maintained (4.4.4 released 2026-04-13); supports Python 3.6-3.14 | Clean API, `pathlib` + `IntFlag`, highly recommended by comparisons |
| `aionotify` (rbarrois) | Yes (asyncio) | Less active | Alternative if asyncinotify doesn't fit |
| `minotaur` | Yes | Small/obscure | Mentioned in search, not widely adopted |

([asyncinotify on PyPI](https://pypi.org/project/asyncinotify/), [asyncinotify docs](https://asyncinotify.readthedocs.io/)). The general community verdict is that **asyncinotify is the strongest pure-Linux option** and `watchdog` is the strongest cross-platform option.

### How real-world tools handle this at scale

- **VSCode:** uses `@parcel/watcher` (C++ native) for recursive, Node.js `fs.watch` for non-recursive, both in a separate utility process to isolate crashes. Known instability led them to disable event correlation for TypeScript extension ([VSCode File Watcher Internals](https://github.com/microsoft/vscode/wiki/File-Watcher-Internals)). Uses `files.watcherExclude` to keep inotify usage bounded.
- **tsc `--watch`:** configurable via `watchOptions` in `tsconfig.json`. Default uses FSEvents/ReadDirectoryChangesW; fallbacks include `fixedPollingInterval`, `priorityPollingInterval`, `dynamicPriorityPolling` ([TypeScript - Configuring Watch](https://www.typescriptlang.org/docs/handbook/configuring-watch.html)). On Linux, recursive directory watching is faked by creating per-subdir watchers.
- **webpack dev server:** uses `chokidar` (Node.js library that wraps native events with polling fallback and heavy event coalescing). chokidar is the de facto reference for robust cross-platform file watching in the Node.js ecosystem.
- **entr:** minimal, feeds it a list of files via `find ... | entr cmd`. Uses `kqueue` on BSD/macOS, inotify on Linux.
- **reflex:** Go-based, uses the platform-appropriate mechanism via `fsnotify`.

**Pattern:** everyone recursive-watches by walking directories manually and attaching one watch per directory. Everyone bounds the watch set with excludes. Nobody relies purely on polling.

### Concrete recommendation for tether

**Start with `watchdog`, plan to swap the Linux observer if needed.**

Rationale, in the order it matters:

1. **Cross-platform without effort.** tether's eventual VSCode extension will need to work on Windows and macOS anyway. Writing against `watchdog`'s event interface today saves building platform dispatch later.
2. **Mature, actively maintained, Python-native.** No C extension compile surprises on unusual platforms. Apache 2.0.
3. **Performance sufficient for MVP.** For a typical Python project of a few hundred to a few thousand directories, watchdog + inotify handles events with no issues. The real scaling question is "can you exclude `.git`, `node_modules`, etc." — an orthogonal concern tether needs to solve regardless of backend.
4. **Swap path exists.** If Linux performance becomes a bottleneck later, a custom observer class wrapping `asyncinotify` can replace `InotifyObserver` while keeping the rest of the code untouched. This is a small, bounded rewrite.
5. **Avoid async premature commitment.** The MVP is a daemon that reacts to events and runs event handlers. A synchronous observer thread with a work queue is simpler than mixing `asyncio` with file watching. `asyncinotify`'s benefits (async native) shine in async-first codebases; for tether, watchdog is the straighter path.

**Defaults to ship from day one:**

- Hard-coded exclude patterns for `.git/`, `node_modules/`, `__pycache__/`, `.venv/`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`, `dist/`, `build/`, `target/`, `.gradle/`, anything in `.gitignore` optionally.
- User-configurable exclude list in `.tether/config.json`.
- A clear error message with remediation when inotify limits are hit: "Your system's `fs.inotify.max_user_watches` (8192) was exhausted. Raise it with `sudo sysctl fs.inotify.max_user_watches=524288` or exclude large directories."
- Log the number of active watches at startup for debuggability.

**What not to do:**

- Do not start with polling. Too slow, noisy, and the signals tether cares about (exact-moment modification) are time-sensitive enough that 5-second poll intervals hurt UX.
- Do not use `pyinotify`. Unmaintained and has encoding pitfalls.
- Do not build on `kqueue` directly as a future "scale up" path. Its file-descriptor model scales worse than inotify on Linux.

---

## Recommendations (summary)

| Area               | Pick                                                                                                              | Because                                                                                                                                                                           |
| ------------------ | ----------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Storage layout     | **Option B: per-tether JSON files under `.tether/tethers/`**                                                      | Minimal merge conflicts, excellent PR diff story, clean rename handling, aligns with precedent (k8s manifests, GitHub Actions, Dendron per-file schemas)                          |
| Secondary surface  | **Optional markdown frontmatter as convenience; daemon syncs to canonical store**                                 | Matches SilverBullet pattern of "human-friendly surface; derived canonical index", lets markdown authors express tethers inline                                                   |
| Link types         | **Free-form string (already locked in) + shipped starter vocabulary**                                             | Keeps flexibility; the starter list (`describes`, `specifies`, `implements`, `tests`, `verifies`, `documents-api-of`, `example-of`, `depends-on`, `related`) gives users a runway |
| File watching      | **`watchdog`** (Python, cross-platform) with shipped exclude defaults and a clear inotify-limit error message     | Mature, cross-platform, Python-native, swap path to `asyncinotify` remains open if Linux performance demands it                                                                   |
| CLI / Python split | **One core library; thin CLI + thin Python API on top; JSON output when non-TTY or `--json`** (already locked in) | Mirrors the official Obsidian CLI and the `obsidian-cli` Python community tool — a well-trodden pattern                                                                           |
| Rename detection   | **Path + content-hash on delete+create within a time window** (already locked in)                                 | Matches git's own approach (rolling hash, 50% similarity threshold, configurable); operationally well understood                                                                  |

### Cross-cutting observations

- **The source-of-truth-is-markdown convention in PKM is a green light for JSON-on-disk being readable.** If JSON is the canonical store, do not fight it: emit pretty-printed, sorted-key JSON, one tether per file, and let git do its job. All comparable tools that chose committed text stores went the same way.
- **Typed links are an abandoned feature in most PKM tools and a default in traceability tools.** tether sits at the intersection and the traceability world has the better-developed vocabulary — worth borrowing the forward/reverse label pattern even though tether chose free-form strings.
- **watchdog is boring but correct for this use case.** The exciting options (asyncinotify, direct kqueue, native parcel-watcher bindings) solve problems tether does not yet have. Revisit only when real performance data demands it.
- **The `bidirectional: true` flag decision is well-supported by prior art.** Obsidian's "backlinks are always computed" and Dublin Core's paired forward/reverse labels both land on "one link, two views of it" rather than "two link records." The flag model is simpler to diff and simpler to merge.

### What remains uncertain

- **Tether ID scheme.** UUIDv7 vs content-hash vs slug — each has real tradeoffs for human-editability and rename resilience. Worth an explicit design decision before implementation.
- **Rename detection window.** "Time window" is locked in but the actual duration (1s, 5s, 30s?) and whether it's configurable aren't. Git uses no time window at commit time because it has a full snapshot. A daemon does not; tuning this will matter.
- **Event coalescing.** "Byte-level diff, noisy by design for MVP" is locked in, but downstream subscribers will want debouncing. Worth planning the hook point now to avoid a disruptive change later.
- **Markdown frontmatter as secondary surface.** Recommended above but not locked in — worth deciding whether that is MVP or deferred.

---

## Sources

- [Obsidian Forum - Convert WikiLinks to Markdown Links](https://forum.obsidian.md/t/convert-wikilinks-to-markdown-links/48339)
- [Obsidian DeepWiki - Internal Links and Backlinks](https://deepwiki.com/victor-software-house/obsidian-help/3.1-internal-links-and-backlinks)
- [Obsidian CLI](https://obsidian.md/cli)
- [Obsidian Help - CLI](https://help.obsidian.md/cli)
- [DEV - Obsidian Official CLI](https://dev.to/shimo4228/obsidians-official-cli-is-here-no-more-hacking-your-vault-from-the-back-door-3123)
- [obsidian-cli PyPI (jwhonce)](https://pypi.org/project/obsidian-cli/)
- [obsidian-vault-cli (rjzxui)](https://github.com/rjzxui/obsidian-vault-cli)
- [XDA - Python scripts for Obsidian](https://www.xda-developers.com/these-python-scripts-will-supercharge-your-obsidian-vault/)
- [Logseq DeepWiki - Repository and Graph Management](https://deepwiki.com/logseq/logseq/4.3-repository-and-graph-management)
- [Logseq DB Unofficial FAQ](https://discuss.logseq.com/t/logseq-db-unofficial-faq/32508)
- [Dendron - Schemas](https://wiki.dendron.so/notes/c5e5adde-5459-409b-b34d-a0d75cbb1052/)
- [Dendron - Hierarchies](https://wiki.dendron.so/notes/f3a41725-c5e5-4851-a6ed-5f541054d409/)
- [Dendron - Concepts](https://wiki.dendron.so/notes/c6fd6bc4-7f75-4cbb-8f34-f7b99bfe2d50/)
- [Johnny.Decimal Forum - Dendron Filename Format](https://forum.johnnydecimal.com/t/dendrons-hierarchical-note-filename-format/532)
- [Foam - Materialized Backlinks Proposal](https://github.com/foambubble/foam/blob/main/docs/dev/proposals/materialized-backlinks.md)
- [Foam GitHub](https://github.com/foambubble/foam)
- [SilverBullet GitHub](https://github.com/silverbulletmd/silverbullet)
- [SilverBullet - Metadata](https://silverbullet.md/Metadata)
- [SilverBullet - Objects](https://silverbullet.md/Objects)
- [SilverBullet - Attributes](https://v2.silverbullet.md/Attributes)
- [SilverBullet - Link](https://v2.silverbullet.md/Link)
- [org-roam Manual](https://www.orgroam.com/manual.html)
- [org-roam DeepWiki](https://deepwiki.com/org-roam/org-roam)
- [Softacus - DOORS Link Types](https://softacus.com/blog/basics-of-links-and-link-types-in-ibm-doors-next-generation)
- [SodiusWillert - DOORS Next Traceability](https://www.sodiuswillert.com/en/blog/how-to-set-up-create-and-use-traceability-links-in-ibm-doors-next)
- [Open Services for Lifecycle Collaboration](https://open-services.net/)
- [Jama - What is OSLC](https://www.jamasoftware.com/blog/oslc-what-is-it-and-what-are-its-challenges/)
- [Jama - Traceable MBSE](https://www.jamasoftware.com/blog/jama-connect-for-traceable-mbse-the-chameleon/)
- [ReqView - Traceability Links](https://www.reqview.com/doc/requirements-traceability-links/)
- [Evaluating LLMs for Doc-to-Code Traceability (arXiv 2506.16440)](https://arxiv.org/html/2506.16440v1)
- [ICSE - Recovering Trace Links Between Software Documentation And Code](https://dl.acm.org/doi/10.1145/3597503.3639130)
- [Sphinx autodoc](https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html)
- [Breathe docs](https://breathe.readthedocs.io/)
- [Literate Programming Wikipedia](https://en.wikipedia.org/wiki/Literate_programming)
- [Org-babel Introduction](https://orgmode.org/worg/org-contrib/babel/intro.html)
- [Bazel - Dependencies](https://bazel.build/concepts/dependencies)
- [Bazel - Review dependency graph](https://bazel.build/tutorials/cpp-dependency)
- [Nx - Mental Model](https://nx.dev/docs/concepts/mental-model)
- [Nx - Explore Graph](https://nx.dev/docs/features/explore-graph)
- [Turborepo - Package and Task Graph](https://turborepo.dev/docs/core-concepts/package-and-task-graph)
- [Turborepo - Configuring Tasks](https://turborepo.dev/docs/crafting-your-repository/configuring-tasks)
- [lychee GitHub](https://github.com/lycheeverse/lychee)
- [lychee docs](https://lychee.cli.rs/)
- [Dolt - Git for Data](https://docs.dolthub.com/introduction/getting-started/git-for-data)
- [DoltLite announcement](https://www.dolthub.com/blog/2026-03-25-doltlite/)
- [Dolt vs SQLite Diff](https://www.dolthub.com/blog/2022-06-03-dolt-diff-vs-sqlite-diff/)
- [Obsidian Dataview](https://blacksmithgu.github.io/obsidian-dataview/)
- [Juggl - Link Types](https://juggl.io/link-types.html)
- [SKOS Core Guide](https://www.w3.org/2004/02/skos/core/guide/2004-10-22.html)
- [DCMI Metadata Basics](https://www.dublincore.org/resources/metadata-basics/)
- [watchdog on PyPI](https://pypi.org/project/watchdog/)
- [watchdog on GitHub](https://github.com/gorakhargosh/watchdog)
- [watchdog kqueue source](https://github.com/gorakhargosh/watchdog/blob/master/src/watchdog/observers/kqueue.py)
- [asyncinotify on PyPI](https://pypi.org/project/asyncinotify/)
- [asyncinotify docs](https://asyncinotify.readthedocs.io/)
- [watchexec - Linux inotify limits](https://watchexec.github.io/docs/inotify-limits.html)
- [JetBrains - Inotify Watches Limit](https://intellij-support.jetbrains.com/hc/en-us/articles/15268113529362-Inotify-Watches-Limit-Linux)
- [VSCode File Watcher Internals](https://github.com/microsoft/vscode/wiki/File-Watcher-Internals)
- [TypeScript - Configuring Watch](https://www.typescriptlang.org/docs/handbook/configuring-watch.html)
- [entr](https://eradman.com/entrproject/)
- [reflex GitHub](https://github.com/cespare/reflex)
- [Git Rename Detection algorithm explainer](https://www.tutorialpedia.org/blog/how-does-git-detect-similar-files-for-its-rename-detection/)
