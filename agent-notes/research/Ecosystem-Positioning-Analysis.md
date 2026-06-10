# Ecosystem Positioning Analysis

A critical analysis of tether's possibilities, combining a review of the project's internal design docs with a four-track web survey of the surrounding ecosystem (doc–code sync tools, traceability/change-coupling systems, the AI-agent context ecosystem, and drift-detection paradigms). Survey conducted June 2026; the full source-cited research reports are appended.

---

## TL;DR

Tether occupies a genuinely empty square: **declared + content-fingerprinted + agent-checkable file relationships**. Nothing else combines all three — 30 years of requirements-traceability tooling has the first two but predates agents; the entire 2025–26 wave of AI doc-sync tools has the third but runs on LLM guesswork instead of deterministic state. The premise is newly validated by research (stale agent context measurably *harms* task success; cross-artifact consistency is the quantified frontier weakness of coding agents). But the square is empty partly for a reason — declared-link systems have a documented, repeated death spiral ("maintenance is where traceability dies") — and the window is closing: at least four independent entrants (Fiberplane Drift, VeriContext, spec-kit-sync, agent-oriented IfChange linters) shipped into adjacent positions in the six months before this survey. Tether's realistic ceiling is well-adopted open-source infrastructure, not a standalone product; its realistic floor is the CODEOWNERS path — installed, drifted, ignored, uninstalled. Which way it goes depends almost entirely on two actionable things: **proving uplift in the Margin eval with a design that can actually discriminate**, and **defeating the rubber-stamp refresh** — which, uniquely, tether's own audit trail makes measurable.

---

## 1. What tether is, reduced to its irreducible claim

Strip away the CLI and the hooks and tether makes one claim: *intent about relationships between artifacts should be recorded as data, anchored to content identity, and re-asserted explicitly when content moves.* Everything else — git blob OIDs, symmetric a/b ends, the required description, refresh-as-assertion, hook injection — is a delivery mechanism for that claim.

This matters because the claim has been made before, repeatedly, and the delivery mechanism is where every prior attempt lived or died.

## 2. The ecosystem map: who is near, and the empty square

The survey converged on a clean three-legged test. Across ~40 tools and research systems:

| | Declared | Fingerprinted | In the agent loop |
|---|---|---|---|
| doorstop / DOORS / Jama (suspect links) | ✓ | ✓ (item text hashes) | ✗ |
| Swimm Auto-sync (pre-pivot) | ✓ | ✓ (snippet-level) | ✗ |
| Google `LINT.IfChange` + OSS clones | ✓ | ✗ (stateless diff-match) | partially |
| Fiberplane Drift (launched ~June 2026) | ✓ | ✓ (AST sig in doc frontmatter) | ✓ (Claude Code skill, CI gate) |
| VeriContext (Feb 2026, ~7 stars) | ✓ | ✓ (inline SHA-256 citations) | ✓ (MCP) |
| Kiro hooks / Mintlify Workflows / DeepDocs / spec-kit-sync | ✗ | ✗ | ✓ (LLM re-judges the diff) |
| CodeScene change coupling / code-graph MCP servers | ✗ (inferred) | n/a | ✓ |
| **tether** | ✓ | ✓ (git blob OID) | ✓ (session-boundary hooks) |

Three findings deserve emphasis:

**The state machine is validated prior art, not invention.** Doorstop stores a hash of the linked item; a mismatch makes the link "suspect"; `doorstop clear` is a deliberate human act that absolves it. That is HEALTHY/DRIFTED/refresh almost exactly, in production in safety-critical industries for a decade. Doorstop's users are even asking for tether's generalization — doorstop issue #564 requests hash-based suspicion for *external file references*. The bet is not on an unproven loop; it is on a new substrate (git plumbing, arbitrary file pairs) and a new consumer (the agent).

**Several pieces of tether are individually unreplicated anywhere.** No surveyed tool has: symmetric links (everything else is doc→code or parent→child); a *required* recorded why; refresh as an attributable assertion that travels in the same commit as the change it ratifies; BROKEN-state rename candidates via git's similarity engine; or relationship state injected at session boundaries rather than at PR/CI time. The git-blob-OID choice — free storage, free diffs, free rename detection, free audit trail — is unreplicated and is a genuine architectural edge over Fiberplane's parser-bound AST signatures and VeriContext's inline hash strings.

**But tether is no longer first.** Fiberplane Drift launched in roughly June 2026 with the same thesis ("agents accelerate doc rot; agents need a deterministic check, not another model opinion"), AST fingerprints at symbol granularity, a Claude Code skill, and a company behind it. It is asymmetric, description-less, and pollutes the doc's frontmatter — tether's shape is better on several axes — but it is *shipped*. Convergent evolution is the strongest possible validation of the niche and the strongest possible argument for urgency.

## 3. Why the square was empty — and why the economics just flipped

The pre-agent verdict on declared links is unambiguous and should be treated as the null hypothesis: **declared metadata decays**. The traceability literature names it ("traceability decay"); Jama's own marketing admits "maintenance is where traceability dies"; CODEOWNERS is the mass-market natural experiment in repo-resident path metadata rotting immediately. Declared links survived only where regulation forced someone to pay the maintenance cost.

Tether's core bet is that coding agents flip this economics three ways at once:

1. **Authoring cost → near zero.** The agent writes the tether (and the description doubles as captured intent) as a side effect of doing the work. The onboard skill industrializes this for existing repos.
2. **Consumption → guaranteed.** The classic reason links rot is that nothing reads them. Tether's links are read every session start, every turn end, every Read of a tethered file. The survey's clearest survival lesson — *links survive when something downstream consumes them* (Pact contracts, build graphs, lockfiles) — is the most defensible part of tether's design.
3. **Adjudication → cheap.** Whole-file fingerprints are perfect-recall, low-precision drift detectors. Pre-LLM, that noise was fatal. With an LLM in the loop, the description converts noise into judgment: the agent reads the diff against "changes to argparse subcommands must be reflected in the usage examples" and decides whether this drift *matters*. Deterministic trigger + described intent + model adjudication is a hybrid neither the pure-AST camp (no why) nor the pure-LLM camp (no ground truth, recall-limited, expensive) can replicate.

This is a coherent, defensible thesis. It is also, today, **entirely unproven** — the evidence base is six transcripts of a three-file calculator where the prompt explicitly told the agent to update both files.

External tailwinds are real and recent: the Feb 2026 arXiv study (2601.20404) finding stale AGENTS.md files *reduce* success rates while raising cost >20% ("agents diligently follow instructions that reference folder structures that no longer exist") is near-direct empirical support for "pinned, verifiable context beats unverified context." SWE-EVO (multi-file long-horizon tasks: 25% vs 73% on SWE-bench Verified) and TEBench (test-suite co-evolution) quantify exactly the failure tether targets. DORA 2025 lists strong version-control practice and quality internal docs as the capabilities that determine whether AI amplifies or degrades a team.

## 4. The five hard problems

### 4.1 Rubber-stamp refresh — the central threat

Every assertion-based system in the survey decays the same way: jest's "snapshot fatigue" (blindly `-u` everything), lockfile delete-and-regenerate, `doorstop clear all`, terraform plan rubber-stamping. Tether's design already has the right instincts (per-link refresh, no `--all`, refusal on BROKEN, the assertion travels in the PR). **Never ship `tether refresh --all`.**

But the agent era adds a sharper version: the Stop hook *blocks the turn* on drift, and the cheapest action that clears the block is `tether refresh`. This is an incentive gradient toward exactly the failure mode that killed snapshot testing — for an agent, the friction that keeps a human honest rounds to zero, and signal integrity rests entirely on the model's adherence to the fragment's "do not refresh until alignment is real." That is probabilistic adherence guarding a deterministic system. Worse, refresh asserts *semantic* alignment, which tether cannot verify even in principle — it can detect change, never alignment. The audit-trail defense ("a reviewer can challenge a refresh with no corresponding content change") catches the lazy case, not the wrong case, and only when there is a reviewer.

The opportunity the survey surfaced: **tether is the only system surveyed whose own data makes rubber-stamping measurable.** A refresh commit in which the record's fingerprints changed but only one artifact changed since the previous refresh is mechanically detectable from `git log`. A `tether audit` command — flagging one-sided refreshes, refreshes within seconds of a Stop block, refreshes with no description update across major drift — would turn the biggest threat into a differentiating feature, and would give the eval a metric no competitor can compute.

### 4.2 Whole-file granularity noise

A tether on a 2,000-line module drifts on every edit, relevant or not. The live-traceability deployment literature is blunt: noisy links get abandoned. The normalization pipeline addresses encoding noise; it does nothing for semantic noise ("the diff is real but irrelevant to this relationship"). The description+LLM adjudication recovers precision *per event*, but each adjudication costs context and attention — on a real repo with 200 tethers and an active team, session-start hooks listing 30 DRIFTED tethers is the trust-erosion scenario. LineRange is brittle (the design doc knows this); AST locators are where Fiberplane already is. The pragmatic middle for the wedge use cases: markdown-section locators for the doc side and symbol locators for the code side, deferred until a real repo demonstrates the noise rate. Measure the noise rate before building the fix.

### 4.3 Graph decay and the description-rot irony

The tether graph is a second codebase. Descriptions are prose claims about content and are themselves unfingerprinted on a semantic level — tether cannot tell when a description has rotted. The onboard skill could mint 150 tethers in an afternoon; nothing in the current design curates them afterward except agent diligence. The plan's "precision over recall" stance is correct and should be defended aggressively — coverage is the metric most likely to be Goodharted (by the onboarding agent itself, since it reads coverage as a progress signal). The dogfooding TODO ("use tether to develop tether") is the single most informative experiment available, because graph decay only shows up with time, and only this repo has time on it.

### 4.4 The context-cost burden of proof

The integration injects: a ~1,800-token fragment every session, refs-JSON on every Read of a tethered file, plus hook output. The AGENTS.md study shows injected context can *lower* success while raising cost. Tether must clear the bar of net-positive, not merely "agent responds correctly to drift." The Margin harness is the right instrument, but the smoke-eval design cannot discriminate yet: swe-minimal repos carry no tethers, so the treatment arm tests only that hooks fire and the fragment doesn't hurt. The discriminating eval needs (a) seeded tether graphs, (b) tasks where cross-file consistency is required but **unprompted** — case-01's prompt told the agent to update both files, which even a control arm largely does on a three-file project, (c) multi-session sequences where drift originates outside the agent's memory, and (d) rubber-stamp rate as a tracked metric. TEBench (test co-evolution) and SWE-EVO are the external benchmarks worth targeting; "tether arm closes X% of the SWE-EVO consistency gap" is the sentence that would make this project legible to everyone.

### 4.5 Platform absorption and "good-enough" inference

Two ways the niche evaporates. First, harness vendors absorb it: Anthropic adds linked-files metadata to the CLAUDE.md spec, or Cursor's glob rules grow fingerprints — the idea is small enough to clone in a sprint once demonstrated (mitigation: little beyond moving fast and being the reference implementation; being git-native and harness-agnostic is the durable position, single-harness Claude-Code-only is the fragile one). Second, models just get good enough at within-session consistency that the in-session value shrinks — tether's irreducible value then concentrates on **cross-session, cross-actor drift** (a teammate edited the doc last week; the agent has no memory of it), which no amount of model improvement reaches without persistent state. That is a real moat, but a narrower pitch than "agents keep your docs in sync."

On the business shape: Swimm raised $33M on this exact problem and pivoted to COBOL modernization; Optic was acquired and archived; driftctl is in maintenance mode. Drift detection survives as an *embedded workflow primitive* (terraform plan, lockfiles, oasdiff), not a standalone product. Tether already has the surviving shape — small OSS CLI, committed state, rides existing rails — and Beads (18k stars, git-resident JSON + CLI + agent-first) proves that exact category shape can win adoption fast in 2026. The realistic ambition spectrum runs from "respected niche OSS" to "the standard primitive that harness vendors adopt," not VC-scale product.

## 5. Realistic futures, ranked

**1. The agent consistency guardrail (the current path) — most probable success mode.** Tether as the thing you `init` alongside Claude Code so cross-file intent survives sessions. Needs: eval-proven uplift, one-command install, plugin-marketplace distribution. The convergent entrants confirm demand; tether's design is the most complete in the field.

**2. The CLAUDE.md/AGENTS.md staleness checker — the sharpest unclaimed wedge.** The ecosystem standardized on unanchored prose context files (AGENTS.md in the Linux Foundation, 60k+ repos); research shows stale ones actively mislead; the state of the art for keeping them honest is "quarterly skim." Nothing validates context files against code. A tether between a CLAUDE.md section and the module it describes is a specific, painful, marketable problem — and a better headline than generic doc drift. Blocker: the project-wide-files question Future-Work flags, plus section-level locators.

**3. The PR-review / CI surface.** A GitHub Action: comment drifted tethers on PRs, flag one-sided refreshes (the audit primitive), gate optionally. This is where every surviving drift system lives, it gives links a second guaranteed consumer, and it makes tether useful to teams whose agents are *not* Claude Code. Cheap to build on the existing JSON.

**4. Substrate for spec-driven development.** Spec Kit's `/speckit.analyze` stops at spec-artifact consistency; spec-kit-sync re-derives drift by LLM each run; the SDD survey (arXiv 2602.00180) names "specification rot" unsolved; Tessl retreated from spec-as-source entirely. A fingerprinted link store is the durable layer all of them lack. Partnership/integration-shaped rather than something to build alone.

**5. Traceability-lite for regulated software.** Doorstop's users literally requested tether's mechanism. The money is real (it's where Swimm fled), the ceremony tolerance is high, but it drags the project toward compliance features and away from agents. Note it; don't chase it.

**6. The long shot: the relationship corpus.** If tethers accumulate across many repos, the description corpus — human/agent-stated intent about what must co-change and why, validated by fingerprints — is data nothing else generates. Useful for training co-change reasoning, repo onboarding, impact analysis. Not a plan, but a reason the description field's quality bar matters beyond any single repo.

**The failure scenario, stated plainly:** tether ships, the onboard skill mints a graph, real-repo noise makes session-start output long, agents start reflexively refreshing to clear Stop blocks, the signal stops meaning anything, status shows 40 DRIFTED forever, uninstall. Every element of that chain has historical precedent. Every element is also addressable — which is why the audit primitive and the noise-rate measurement matter more than feature breadth right now.

## 6. Recommended next moves, in order

1. **Make the eval discriminating** (seeded graphs, unprompted-consistency tasks, multi-session drift, control arm) and add **rubber-stamp rate** as a first-class metric. Until this exists, every other investment is faith-based.
2. **Build `tether audit`** (one-sided-refresh detection from the existing audit trail). It defends the core trust model and is a feature no adjacent tool can copy without adopting the whole architecture.
3. **Dogfood on this repo** — the vault TODO already says so; graph-decay data only comes from time.
4. **Decide the project-wide-files question** in service of the CLAUDE.md-staleness wedge.
5. **Go public sooner than feels comfortable.** Fiberplane Drift is shipping into the same square with a worse design and better distribution. The name has real liabilities (tether-cli.com is an existing git-backed dev CLI, npm `tether` is a positioning library with millions of downloads, and the USDT stablecoin owns the search term) — worth a deliberate decision before the README is the brand.

The one-line verdict: tether's design is the most complete expression of a primitive whose time has plausibly arrived, validated from five independent directions — and it is currently an unproven, unshipped tool whose central failure mode (assertion decay) has killed every one of its ancestors. The difference between those two sentences is the eval and the audit trail. Both are within reach.

---
---

# Appendix A — Research report: documentation–code synchronization landscape

Methodology note: page fetches were unavailable to the research agent (search-snippet sourced). Funding figures, dates, and mechanisms are cited; GitHub star counts were omitted rather than guessed.

## A.1 Tool-by-tool rundown

### Declared doc–code coupling with drift detection (tether's nearest neighbors)

#### Swimm (swimm.io)
- **What it was:** "Continuous documentation" platform. Docs written in a `sw.md` Markdown variant containing live code snippets, tokens, and paths coupled to the repo. A patented **Auto-sync** algorithm validated docs in CI (via a GitHub App) on every PR — auto-fixing trivial snippet changes and flagging significant ones for human review ([GitHub app](https://swimm.io/blog/keeping-internal-docs-up-to-date-always-with-the-swimm-github-app), [snippet-coupled editor](https://swimm.io/blog/advanced-documentation-editor-how-to-create-code-coupled-docs-in-seconds)). Granularity: **snippet/token level**, not file level.
- **Adoption/funding:** Founded 2019, Tel Aviv. $27.6M Series A (Nov 2021) led by Insight Partners, total **$33.3M** ([TechCrunch](https://techcrunch.com/2021/11/08/swimm-nabs-27-6m-series-a-to-include-up-to-date-documentation-in-every-release/)).
- **Status in 2026 — pivoted.** Swimm now markets itself as an **"Application Understanding Platform"** for AI-assisted **legacy/mainframe modernization** (COBOL, PL/I, CICS, Assembler) ([Swimm 2.0](https://swimm.io/blog/swimm-2-0-the-understanding-platform-for-ai-modernization)). The doc-coupling tech persists as substrate, but selling drift-proof documentation to dev teams is no longer the business.
- **vs. tether:** Swimm coupled *rendered snippets inside docs* to code at token granularity, with automatic CI patching (the system asserts alignment). Tether is symmetric file-level declared links, deterministic blob-OID comparison, and **human/agent re-assertion** with no auto-rewrite. Swimm's pivot is the strongest single data point that snippet-coupled docs-as-product was commercially hard.

#### Fiberplane Drift (github.com/fiberplane/drift) — closest direct analog
- **What it does:** Open-source CLI "linter for documentation rot." `drift link docs/auth.md src/auth/provider.ts#AuthConfig` inserts an **anchor** into the markdown file's YAML frontmatter; `drift check` flags staleness in CI ([blog](https://fiberplane.com/blog/drift-documentation-linter/), [repo](https://github.com/fiberplane/drift)).
- **Mechanism:** each anchor records a `sig` — a **normalized AST fingerprint** computed with tree-sitter (TypeScript, Python, Rust, Go, Zig, Java) — plus optional **provenance** (`@<git-sha>` of the commit that last addressed the anchor). Ships a Claude Code **agent skill** so agents re-stamp anchors as they change code; CI gate blocks merges on stale docs.
- **Granularity:** file or **symbol** (`path#Symbol`).
- **Status:** launched ~June 2026, open source, actively developed. Fiberplane built Drift explicitly because *agents* accelerate doc rot.
- **vs. tether:** Directionally identical idea. Differences: **asymmetric** (doc anchors code), anchors live **inside the doc's frontmatter** rather than separate committed records, AST fingerprint rather than git blob OID (syntax-aware but parser-dependent), **no required "why" description**, no rename-detection story.

#### Doorstop (github.com/doorstop-dev/doorstop) — the conceptual ancestor
- Requirements management in version control; each requirement is a YAML file; items link to other items. When a linked item's content changes, its **fingerprint (SHA-256 content hash) no longer matches the hash recorded in the link**, and validation reports a **"suspect link"**; a human runs `doorstop clear` to re-stamp ([validation docs](https://doorstop.readthedocs.io/en/latest/cli/validation.html)). Open feature discussion about extending hash-based "needs review" to **external file references** — essentially tether's exact mechanism ([issue #564](https://github.com/doorstop-dev/doorstop/issues/564), [issue #577](https://github.com/doorstop-dev/doorstop/issues/577)).
- Mature, maintained OSS; niche (safety/regulated-industry requirements traceability).

#### drift (driftdev.sh / github.com/dadbodgeoff/drift)
- TypeScript-compiler-API-based CLI: 15 drift-detection rules, validates `@example` blocks, "coverage ratchet," GitHub Action. Symbol-level, **inferred** (no declared links), TS-only. Repositioning toward "Codebase intelligence for AI / MCP server." Solo-developer scale.

#### Small/experimental kin
- **drift-vscode** ([pallaprolus/drift-vscode](https://github.com/pallaprolus/drift-vscode)) — AST-analysis VS Code extension; hobby-scale.
- **DocSync** — generates docs from code symbols, git hooks flag stale signatures; hobby-scale.
- **Documentation Drift Detector** Claude Code skill ([mcpmarket.com](https://mcpmarket.com/tools/skills/documentation-drift-detector)) — evidence the pattern is being commoditized into agent skills.

### Embed-and-verify generators (deterministic, content-inclusion only)

| Tool | Mechanism | CI mode | Status |
|---|---|---|---|
| **embedme** ([zakhenry/embedme](https://github.com/zakhenry/embedme)) | comments pull file contents into fenced blocks | `--verify` | alive, low-activity |
| **embedmd** ([campoy/embedmd](https://github.com/campoy/embedmd)) | same in Go | diff-on-regenerate | dormant |
| **cog/cogapp** ([docs](https://cog.readthedocs.io/)) | inline Python generators regenerate regions | `--check` | actively maintained |
| **mdsh** ([zimbatm/mdsh](https://github.com/zimbatm/mdsh)) | markdown preprocessor executes blocks | `--frozen` | alive |

These guarantee only embedded snippets; auto-fix rather than assert; the prose around the snippet can rot freely. Complements, not competitors.

### Doctest-style executable documentation

Python doctest, rustdoc doc-tests (default-on under `cargo test`), mdbook test, ExUnit.DocTest, Go testable examples, **Doc Detective** ([doc-detective.com](https://doc-detective.com/), executes documented procedures against the real product; "Docs as Tests" strategy). Verifies behavior, not relationship; covers only runnable content; nothing for design docs, ADRs, narrative architecture docs — exactly the artifacts tether targets. Rust doc-tests succeeded because they're **default-on with zero declaration cost**.

### Freshness metadata and staleness linters

- **Google g3doc freshness metadata** (`reviewed: '2019-02-27'` + owner; tooling emails owners after N months) — the canonical "human re-assertion on a timer," time-based not content-based ([SWE book ch. 10](https://abseil.io/resources/swe-book/html/ch10.html)).
- **giantswarm/frontmatter-validator** — gates Hugo docs on `last_review_date`.
- **docvet** — Python docstring vetting incl. staleness checks via git diff/blame.
- **Dosu** ([dosu.dev](https://dosu.dev/)) — CI **documentation freshness score** (0–100 per PR): git age delta, **symbol-level drift** (do mentioned functions still exist with same signatures), link validity, plus a Claude-based semantic layer ([blog](https://dosu.dev/blog/score-documentation-freshness-in-ci)).
- **No mainstream SSG plugin does content-drift detection.** Vale is style-only.
- **Hyperlint** — AI reviewer for docs PRs.

### AI documentation platforms (2025–2026 wave)

- **Mintlify Workflows** (2026): autonomous documentation agent — recurring tasks watch repos, read merged-PR diffs, detect drift, open doc PRs; runs Claude Opus 4.6 on OpenCode + Daytona sandboxes ([Docs on autopilot](https://www.mintlify.com/blog/docs-on-autopilot)).
- **DeepDocs** ([deepdocs.dev](https://deepdocs.dev/)): GitHub-native; listens to commits, opens surgical doc-update PRs; "Deep Scan" repo-wide stale-doc detection.
- **GitHub "Continuous AI"** ([githubnext.com/projects/continuous-ai](https://githubnext.com/projects/continuous-ai/)) — named category; Agentic Workflows ship documentation-maintenance workflows.
- The AI wave is **inference + auto-remediation**: an LLM guesses which docs a diff affects and rewrites them. No declared links, no deterministic ground truth, no human assertion. Tether is the opposite trust model.

### Adjacent: API-spec drift, academia

- **Optic** — **dead**: acquired by Atlassian (Apr 2024), repo archived **Jan 12, 2026**; community migrated to **oasdiff** ([writeup](https://dev.to/flarecanary/optic-is-dead-what-now-for-api-drift-detection-2kb8)).
- **Academic (2025–2026):** code-comment inconsistency detection is an active LLM research area — CCISolver ([arXiv:2506.20558](https://arxiv.org/abs/2506.20558)), DocPrism ([arXiv:2511.00215](https://arxiv.org/pdf/2511.00215)).

## A.2 Cross-cutting observations

1. **Two paradigms, one fault line: declared vs. inferred links.** Inference scales with zero authoring cost but has no ground truth and no record of intent; declaration carries authoring/maintenance cost but produces auditable, gateable facts. Fiberplane Drift (June 2026) is a deliberate swing *back* to declaration — because agents need a deterministic CI gate, not another model opinion.
2. **The 2024→2026 re-energizer is coding agents, in both directions** — agents make drift worse and remediation cheap; every new entrant frames doc-sync as part of the agent loop.
3. **Business-model evidence is sobering for standalone doc-sync.** Swimm pivoted; Optic was archived; surviving pure plays are near-zero-maintenance OSS utilities or ecosystem-default mechanisms.
4. **Zero-declaration-cost mechanisms win adoption** (rustdoc tests, Go examples). Every tool requiring a separate authoring act fights an adoption gradient — agent-authored links change the economics.
5. **"Freshness" and "drift" are distinct signals**: time-based review metadata answers "has a human looked recently"; content-based fingerprints answer "did the other end change since the last assertion"; behavioral testing answers "do documented claims still execute." Only the content-based family captures *relationship* drift, and it is by far the least populated.
6. **Practitioner sentiment confirms the problem but defaults to process, not tooling** ([Ask HN, May 2024](https://news.ycombinator.com/item?id=40317113)). Nobody names a dominant tool — there isn't one.

## A.3 Gaps none of these tools fill

1. **Symmetric, artifact-agnostic links** — every surveyed tool is directional; none can express doc↔doc, test↔doc, config↔config, code↔code.
2. **A required, recorded *why*** — the "intent payload" an agent needs to decide whether drift matters exists nowhere else.
3. **Re-assertion as a first-class, attributable act** — the AI wave actively erodes this; auto-PR tools make "alignment" an unattributed model output.
4. **Rename-resilient links** — no counterpart to BROKEN + git rename detection.
5. **In-session agent integration** — nobody else surfaces relationship drift *inside the working session*.
6. **Deterministic detection without auto-rewrite** — the middle position between byte-auto-fix and LLM-rewrite is essentially unoccupied.

**Competitive watch-list:** Fiberplane Drift, Mintlify Workflows, Dosu.

---

# Appendix B — Research report: traceability, change-coupling, and "touch X, update Y" tooling

## B.1 Item-by-item rundown

### Requirements traceability tools

#### Doorstop — the closest single piece of prior art
- Git-native requirements management; items are YAML files; a link is stored on the child as `parent UID + fingerprint of the parent when last reviewed` (SHA-256 of item content, URL-safe Base64). Validation reports a **"suspect link"** on fingerprint mismatch; `doorstop clear` re-stamps; a separate `reviewed:` fingerprint flags unreviewed self-changes ([item reference](https://doorstop.readthedocs.io/en/v2.1.2/reference/item/), [validation](https://doorstop.readthedocs.io/en/latest/cli/validation.html)).
- Active (v3.0.x 2025; v3.1 Jan 2026). Used by Codethink's Trustable Software Framework, referenced by RTEMS.
- **Differences from tether:** hashes the requirement *item's text*, not arbitrary file blobs; hierarchical/directional; requirements ceremony; tool-internal SHA-256 (no git plumbing leverage); not agent-oriented.

#### Trustable Software Framework / trudag (Codethink)
- Assurance-argument DAGs; "stamps items by adding a node attribute that is the hash of the item's text" ([docs](https://codethinklabs.gitlab.io/trustable/trustable/trudag/using-doorstop.html)). A second live, safety-industry user of hash-stamped suspect links in git.

#### IBM DOORS / DOORS Next
- Links marked **suspect** when the linked object changes; "link validity" valid/invalid/suspect states; database-backed, not git-native; change-event-driven, not content-fingerprint ([IBM docs](https://www.ibm.com/docs/en/engineering-lifecycle-management-suite/doors/9.7.2?topic=data-suspect-links-changed-objects)).

#### Jama Connect
- Suspect links fire when admin-configured fields of upstream items change. Jama's own marketing: "More columns mean more maintenance, and maintenance is where traceability dies" ([traceability matrix guide](https://www.jamasoftware.com/requirements-management-guide/requirements-traceability/traceability-matrix/)).

#### ReqView
- Requirements as human-readable JSON in git/SVN; per-link-type suspect flags; project-level "Clear All Suspect Flags" ([change management](https://www.reqview.com/doc/change-management/)). Closest commercial tool to "suspect links as committed JSON," but requirement granularity, app-internal logic.

#### Sphinx-Needs
- Typed links inside Sphinx docs; **lacks** fingerprint-based suspect links — users are asking for them ([discussion #1352](https://github.com/useblocks/sphinx-needs/discussions/1352)).

#### StrictDoc
- Plain-text requirements; experimental req-to-source traceability via tree-sitter; no per-link content fingerprint surfaced.

#### OpenFastTrace
- Spec items `type~name~revision` embedded in comments; suspicion via a **manually bumped revision integer** — the anti-pattern (forgetting silently preserves a stale link) ([user guide](https://github.com/itsallcode/openfasttrace/blob/develop/doc/user_guide.md)).

#### Academic: traceability link recovery (TLR) — LLM-era revival is real
- TraceLLM (Requirements Engineering, 2026, [arXiv 2602.01253](https://arxiv.org/html/2602.01253v1)); RAG-based TLR at REFSQ 2025 (~99% validation / 85.5% recovery on automotive requirements); LLM doc-to-code traceability ([arXiv 2506.16440](https://arxiv.org/html/2506.16440v1)). LLM error patterns (phantom links, naming bias) mean recovered links still need review — positioning *recovery* as complementary to tether's *declaration*.
- **ReqToCode** ([arXiv 2603.13999](https://arxiv.org/html/2603.13999)): requirement references as code dependencies so "traceability violations are build failures." The compiler as drift detector vs. tether's git as drift detector; only works for code that can reference a generated artifact.

### Change coupling / co-change analysis (the inferred counterpart)

#### CodeScene
- **Change coupling** inferred from commit history; hotspot maps; "sum of coupling" prioritization ([docs](https://docs.enterprise.codescene.io/versions/3.4.0/guides/technical/temporal-coupling.html)). 2026 positioning: CodeHealth MCP server feeding deterministic metrics to coding agents ([codescene-mcp-server](https://github.com/codescene-oss/codescene-mcp-server)).
- **Relationship to tether:** exact mirror image — infers "what has co-changed"; tether declares "what must co-change." They compose: inferred coupling is a candidate-generation source for declared tethers.

#### code-maat / "Your Code as a Crime Scene" (Tornhill)
- The methodological root; logical coupling = hidden implicit dependency.

#### Evolution Radar
- Academic visualization (2006–2009); dead as a tool; canonical citation that co-change "reveals dependencies not revealed by analyzing the source code only."

### "Reminder" tooling

#### Danger (danger.js / danger-rb)
- Dangerfile rules in CI: "if `lib/` changed and CHANGELOG.md didn't, warn." Open issue #431 asks for first-class "if this file, then that" primitives ([issue](https://github.com/danger/danger-js/issues/431)). Rules are imperative code, not data; no fingerprints — sees only "changed in this PR," not "drifted since last asserted alignment"; fires at PR time (late).

#### Sourcegraph codenotify
- `CODENOTIFY` files map globs → subscribers; notification without blocking ([repo](https://github.com/sourcegraph/codenotify)). Links files to *people*, not files to files.

#### GitHub CODEOWNERS
- The most widely deployed example of declared path-metadata-in-repo decaying: stale immediately, departed users silently bypass, reviewer overload ([Laura Tacho](https://lauratacho.com/blog/should-we-use-codeowners)).

#### changesets bot
- "You touched X, you owe artifact Y" — succeeds because Y is cheap, templated, and consumed automatically by the release pipeline.

#### Google presubmit culture
- Presubmits include "test files included with corresponding code files"; institutionalized touch-X⇒also-Y at change time; bespoke and not portable ([SWE book ch. 20](https://abseil.io/resources/swe-book/html/ch20.html)).

#### Bazel / monorepo build-graph adjacency
- `rdeps()` impact queries — the *structural* substitute for declared links; doc↔code and config↔config are invisible to the build graph, exactly tether's domain.

### Lint-level approaches

- **keep-sorted** (Google) — tiny declared intra-file invariants enforced mechanically.
- **Golden-file / approval tests** — the golden file is a fingerprint, re-approval is the refresh; approval mode requires explicit human inspection.
- **Pact** — a contract is a *machine-checkable tether with executable semantics*, but only where the relationship is an API. 2026 guides cite AI-generated code changing endpoints "faster than review processes can catch" as a driver.
- **Swimm Auto-sync** — fingerprint-based suspect-link detection productized for doc↔code, with automated re-alignment instead of asserted re-alignment.

### Git-native metadata layers

- **git notes** — commit-granular metadata; substrate, not competitor.
- **git-annex metadata** — content-addressed metadata on file keys, for large-file organization.
- **gitattributes** — declarative per-path metadata precedent; describes a single path, never a pair.
- **Beads (Steve Yegge, 2025–26)** — git-backed issue tracker *for AI agents*: JSONL records in `.beads/`, dependency edges, 18k+ stars ([repo](https://github.com/steveyegge/beads)). The most successful recent proof that **committed JSON metadata + CLI + agent-first design** is a viable category; validates tether's architectural choices.
- **Fingerprint inventory across the survey:** doorstop (SHA-256 item text), trudag (hash stamps), Swimm (snippet verification), ReqView/Jama/DOORS (change-event, not hash), OpenFastTrace (manual revision ints), golden tests (committed bytes). **None uses git blob OIDs; none fingerprints arbitrary whole files pair-wise.**

### Name collisions for "tether"

- **npm `tether`:** element-positioning library (ex-Bootstrap 4 dependency), millions of legacy downloads; `react-tether`, `@types/tether`; tetherjs.dev.
- **PyPI:** `tether` apparently unclaimed by a major project; `tether-agent`, `tether-price` etc. exist.
- **tether-cli.com:** an existing developer CLI named tether — syncs dotfiles/packages via a private git repo. The most direct collision: a git-backed dev CLI with the same name.
- **Tether/USDT:** the stablecoin dominates search and holds the `tetherto` GitHub org.
- Net: usable as a binary name; hard to search for; real go-to-market liability.

## B.2 Cross-cutting lessons

**a.** Every mature declared-link system converged on the same three primitives tether has (declare → detect → human clears/re-asserts). The loop is validated; its failure modes are well documented.

**b.** **The decay problem is the central failure mode**: "traceability decay" ([Mäder & Gotel](https://pmc.ncbi.nlm.nih.gov/articles/PMC3587459/)); "maintenance is where traceability dies" (Jama); "stale links are actively harmful when they mislead" (ReqToCode); CODEOWNERS as natural experiment.

**c.** What separates survivors from rotters:
1. **Detection automatic; only clearing manual.** (OpenFastTrace's manual bump is the anti-pattern; tether's blob-OID compare is on the right side.)
2. **The check sits in the path of the change.** (Presubmits/Danger/changesets work; RTM spreadsheets rot. Tether's mid-turn hook is the strongest version surveyed — earlier than presubmit.)
3. **Clearing cost ≈ change cost.** (`tether refresh` is cheap; the risk shifts to *reflexive* refreshing — the suspect-link equivalent of snapshot `-u`.)
4. **False positives kill trust fastest.** (Normalization is the right instinct; noisy links get abandoned, [arXiv 2306.10972](https://arxiv.org/html/2306.10972).)
5. **Links survive when something downstream consumes them.** (Pact gates deploys; build graphs fail builds; RTMs rot because nothing executes them. Tether's consumer being the agent itself, every turn, is a genuinely new answer.)

**d.** The 2025–26 inflection: AI agents both cause and consume drift checks; the market converges on tether's premise mostly via *inference*, not declared fingerprinted links.

## B.3 Gaps none of these fill

1. Symmetric, file-pair-granular, repo-resident declared links with content fingerprints (git-blob-OID choice unreplicated).
2. The mandatory "why" — readable by an agent deciding whether drift matters.
3. Drift surfaced inside the agent's working turn.
4. Refresh as a first-class, attributable assertion traveling with the change it ratifies.
5. Domain-agnostic coverage (migration↔model, IaC↔runbook, prompt↔eval, schema↔fixture).
6. **Honest non-gaps:** link-creation effort (no recovery/suggestion assist yet — the obvious roadmap item and competitor leapfrog vector); binary-only tethers vs N-ary invariants; the reflexive-refresh failure mode unsolved by design; the contested name.

---

# Appendix C — Research report: AI agent context, memory, and spec ecosystem

## C.1 Item-by-item

### Spec-driven development (SDD)

- **GitHub Spec Kit** ([repo](https://github.com/github/spec-kit)): most adopted SDD toolkit 2026; `/speckit.analyze` checks consistency *among spec artifacts only*, pre-implementation, by LLM judgment. Community extension **spec-kit-sync** ([repo](https://github.com/bgervin/spec-kit-sync), ~20 stars) does LLM-judged spec↔code drift with four resolutions — proves demand; mechanism is "ask the model," not fingerprints.
- **AWS Kiro** ([kiro.dev](https://kiro.dev/)): agentic IDE; specs as unit of work; steering files always loaded; **agent hooks** fire on IDE events to "update tests, synchronize documentation" ([hooks](https://kiro.dev/blog/automate-your-development-workflow-with-agent-hooks/)). Marketing claims hooks keep specs fresh; mechanism is event-triggered agent prompting — probabilistic, IDE-bound, no per-relationship records or drift status. Closest product analog to tether's hook story.
- **Tessl** ([tessl.io](https://tessl.io/)): $125M Series A; spec-as-source Framework promised "drift eliminated by design"; **by mid-2026 repositioned as an "Agent Enablement Platform" — a package manager for agent skills** (3,000+ skills; Snyk partnership). The most radical alignment-by-construction bet retreated to context distribution. Strong signal that full spec-as-source was too heavy.
- **OpenSpec (Fission-AI)** ([repo](https://github.com/Fission-AI/OpenSpec)): 52k stars; drift handled by *workflow discipline*; no checking that code matches specs.
- **Academic frame:** "Spec-Driven Development: From Code to Contract" ([arXiv 2602.00180](https://arxiv.org/html/2602.00180v1)) taxonomizes spec-first (drift ignored) / spec-anchored (tests enforce) / spec-as-source (regenerate); names "specification rot" an open problem with no technical mechanism proposed.

### Agent memory / context conventions

- **AGENTS.md** settled as the standard: donated to the Linux Foundation's Agentic AI Foundation Dec 2025; 60,000+ repos; read by 20+ agents ([agents.md](https://agents.md/)).
- **Claude Code:** CLAUDE.md + auto memory + "Auto Dream" background consolidation. Staleness handled by **LLM curation of the memory itself** — nothing checks memory claims against code; official advice remains "skim and delete after refactors."
- **Codex:** AGENTS.md + background memories consolidated from idle sessions.
- **Cursor:** `.cursor/rules/*.mdc`; glob-attached rules are a weak one-directional relationship declaration (rule→file-pattern, no fingerprint, no drift state). Cursor **removed** its Memories feature in v2.1.x in favor of explicit Rules — a retreat from ungrounded auto-memory.
- **Validation of context files:** cclint and AgentLint exist but are *structural* linters. **No tool found that anchors context-file claims to code content and detects when the code moves.** The state of the art for CLAUDE.md staleness is "quarterly skim."

### Codebase knowledge graphs for agents

All major entrants are **inferred**, none declared: GitNexus (28k stars, MCP knowledge-graph engine), codegraph (tree-sitter → SQLite), Codebase-Memory (arXiv 2603.27277), Aider repo map (tree-sitter + ranked graph, ephemeral), Repomix (~22k stars, no relationships), Graphiti/Zep (bi-temporal KG for conversational memory — edge validity intervals are the nearest conceptual cousin to fingerprint-validated links, but facts are extracted, never verified against file content), Sourcegraph Amp (AGENTS.md-based), CodeSee (acquired by GitKraken 2024, dead as standalone). Explicit human-declared relationships: essentially absent from the category; the one fingerprinted-declared-link system anywhere is Doorstop (pre-agent, requirements-only).

### Agent-era consistency checking

- **Mintlify Workflows/Autopilot**, **Doctective**, **Red Hat code-diff→docs-PR**, **Dosu freshness scoring**: all infer impact from diffs by LLM; no declared links.
- "Context rot" is named, measured (Chroma's 18-model study), and treated as a primary production blocker.
- **Evals (the strongest demand evidence):**
  - **SWE-EVO** ([arXiv 2512.18470](https://arxiv.org/abs/2512.18470)): release-note-derived tasks averaging 21 files; frontier agent stacks score ~25% vs 72.8% on SWE-bench Verified — long-horizon multi-file coordination is the open gap.
  - **TEBench** ([arXiv 2605.06125](https://arxiv.org/html/2605.06125v1)): benchmarks whether agents keep test suites co-evolving with production code — cross-artifact consistency measured directly.
  - **SlopCodeBench**, **EvoClaw**, "Asymmetric Goal Drift in Coding Agents" (ICLR 2026 workshop).

### Hooks ecosystem

Claude Code hooks are a mature "deterministic control layer" (12–13 lifecycle events). Established SessionStart patterns: project state, prior-session progress, TODO surfacing. Dominant PostToolUse pattern: lint/type-check feedback. **No established "drift-surfacing" hook category found.** Tether's SessionStart + Stop drift injection is a novel use of well-worn rails.

## C.2 Cross-cutting trends, mid-2026

1. Static context standardized (AGENTS.md); everything *live* — memory, graphs, drift — remains fragmented.
2. Memory went agent-authored and LLM-curated; staleness handled by more LLM judgment, never verification against code. Cursor killing Memories is a counter-signal: ungrounded auto-memory produced enough garbage that a major vendor retreated.
3. The SDD wave crested into pragmatism: spec-as-source pivoted away; workflow-discipline tools won adoption; spec↔code drift handled by regeneration promises, tests, or LLM re-analysis — never content fingerprints.
4. **Inference everywhere, declaration nowhere.**
5. Consistency enforcement converging on "agent reads the diff and guesses" — probabilistic, recall-limited, mostly PR-time/async.
6. The failure tether targets is now quantified (SWE-EVO gap; TEBench).

## C.3 Where a tether-like primitive slots in

**No one is doing "declared, fingerprinted, agent-checkable file relationships."** Why the square is empty: (a) pre-agent, declared links were pure maintenance tax confined to regulated industries; (b) the agent era's first instincts were inference (zero user effort) and LLM diff-judgment (zero schema), which ship demos faster; (c) the demand signal is recent — the quantifying evals are Dec 2025–May 2026 papers. Two genuine risks: LLM diff-judgment may be "good enough" for the docs use case; the declaration burden could recur — though agents authoring tethers (with the description doubling as intent capture) inverts the economics in a way no prior era could.

**Complements, not collisions:** under the context-file layer (nothing validates CLAUDE.md/AGENTS.md against code); under SDD tools (the durable substrate they lack); beside inferred graphs (graphs answer "what calls what"; tether answers "what was *meant* to stay aligned and is it"); on standard hook rails.

**Redundant as:** a docs-publishing pipeline (Mintlify), a spec workflow (Spec Kit/OpenSpec), a code graph (GitNexus et al.).

---

# Appendix D — Research report: drift-detection paradigms and direct-competitor hunt

## D.1 Direct competitor hunt

**No tool found that matches tether's exact shape** — symmetric declared file-pair link, committed per-end content fingerprint, required description, explicit refresh-as-assertion reviewable in the same PR. The space is occupied at the edges by three families:

### The IfChange/ThenChange family (closest prior art, ~50% overlap)

**Google/Chromium `LINT.IfChange` / `LINT.ThenChange`:** wrap a region in comment directives; if a CL modifies the guarded region but not the named target, the presubmit warns in Gerrit ([ChromiumOS guide](https://www.chromium.org/chromium-os/developer-library/guides/development/keep-files-in-sync/); [Fuchsia presubmits](https://fuchsia.dev/fuchsia-src/development/source_code/presubmit_checks)). Chromium reportedly carries 1,100+ directives.
- **Mechanism is diff-scoped, NOT content-hashed**: asks only "did the other file also appear in this diff?" No persistent state; any touch of the target satisfies the check (rubber-stamp-by-touch); drift across two commits is invisible; no `status` outside a pending diff.
- **Documented pain points:** rename+edit in one commit defeats it; directive-line changes don't trigger; stale ThenChange paths rot; warnings bypassable.
- **OSS reimplementations** (all diff-based, none fingerprint-based): [simonepri/ifttt-lint](https://github.com/simonepri/ifttt-lint) (Rust, active June 2026), [slnc/ifchange](https://github.com/slnc/ifchange) (Rust, ships on crates/npm/PyPI, **publishes recommended practices for AI coding agents**), [ebrevdo/ifttt-lint](https://github.com/ebrevdo/ifttt-lint) (TS).
- **Meta/Buck2:** no public equivalent found.

### Hash/fingerprint-based tools (mechanism match, different shape)

- **VeriContext** ([amsminn/vericontext](https://github.com/amsminn/vericontext), npm, ~7 stars, Feb 2026) — closest mechanism match. "Deterministic, hash-based verification for docs that reference code. Fail-closed." Truncated SHA-256 hashes of file/line-range content embedded in doc citations (`[[vctx:src/cli.ts#L1-L10@a1b2c3d4]]`); CLI + MCP server for agents; `verify` exits non-zero on mismatch. Asymmetric, inline hashes, no refresh ceremony, no descriptions, no rename detection. ~60% overlap; tiny and new; validates the thesis and competes for the agent-hook niche.
- **Doorstop** — see Appendix B; the most tether-like state model in existence, scoped to requirements items.
- **Cog** — checksum in generated-block end markers; refuses to overwrite hand edits; one-directional micro-version for generated regions.

### Commercial / LLM-based doc-drift products

- **Swimm** (pivoted to legacy-code understanding), **DeepDocs** (LLM-judged auto-PR), GitHub topic `documentation-drift` (three tiny 2026 projects, all LLM-heuristic). The niche exists but is unclaimed by anything deterministic.
- **Academic prior art:** Zimmermann et al. (ROSE, ICSE 2004/TSE 2005) — co-change mining warns about incomplete changes (~70% top-3 hit rate). Inference-based.

**Differentiators tether uniquely combines:** symmetric two-ended links; fingerprints as committed JSON records (no source pollution, links visible in PR diffs); git-blob-OID fingerprints with normalization; required why; refresh as first-class audited assertion; BROKEN + rename candidates; agent-first hooks.

## D.2 Paradigm lessons table

| Domain / Tool | Mechanism | Documented failure mode (esp. rubber-stamping) | Lesson for tether |
|---|---|---|---|
| Terraform `plan` | diff desired vs recorded vs actual state | plan-review rubber-stamping endemic; review fatigue on large plans | keep per-link diffs small and meaningful; summary counts invite rubber-stamping |
| driftctl | standalone scanner, cloud vs state | **dead** — Snyk acquisition, maintenance mode since 2023 | standalone drift *detectors* died; detection survives embedded in workflow platforms |
| Spacelift drift detection | scheduled compare + optional reconciliation runs | auto-reconciliation can silently revert intentional changes; mitigated by routing through normal approval | refresh respecting normal review flow mirrors the surviving design |
| Atlas schema drift | versioned diff; drift blocks migration | declarative mode silently absorbs drift; renames inexpressible | block-on-drift precedented; renames are the universal weak spot — tether's rename candidates are a real differentiator |
| Pact | committed contract artifacts verified in CI | contracts rot without active management; dual-maintenance fragmentation | a second relationship artifact rots unless verification is unavoidable; per-link ownership must be obvious |
| Optic | API-spec diffing in CI | **dead** — acquired, archived Jan 2026; oasdiff absorbed the niche | simple OSS CLI + CI action outlived the venture-backed platform |
| Lockfiles | committed fingerprint of resolved state; explicit update; diff travels in the PR | delete-and-regenerate on conflict; nobody reviews 5,000-line diffs | closest UX analogy to refresh; tether records are reviewable in a way lockfiles never were — keep them that way |
| Jest snapshots | recorded golden output; `-u` re-records | **"snapshot fatigue"** — blind updates make tests useless | **the central threat.** Per-link refresh + required description + on-record asserter is the counter-design. Never ship `refresh --all` |
| Doorstop suspect links | SHA-256 stamp; `clear` re-stamps as review act | `doorstop clear all` is the documented bulk path — same blanket-absolve hazard | direct precedent that fingerprint+suspect+deliberate clear works; bulk-clear is where discipline leaks |
| Cog checksums | checksum in end-marker; refuses regeneration over hand edits | devs delete the checksum comment to bypass | inline markers are deletable; out-of-band committed records are more tamper-evident |

## D.3 Ecosystem fit / demand signals (2025–2026)

- **"On the Impact of AGENTS.md Files on the Efficiency of AI Coding Agents"** ([arXiv 2601.20404](https://arxiv.org/abs/2601.20404), Feb 2026): context files **reduced task success while increasing inference cost >20%**, with staleness a key mechanism — near-direct empirical support for tether's premise.
- Doc-drift-in-agentic-workflows is generating Show-posts and micro-tools (VeriContext, AgentLint, the `documentation-drift` topic); "context rot" is an established term; GitHub Next lists continuous documentation as a first-class Agentic Workflows use case.
- **Stack Overflow 2025:** 84% AI adoption, trust at all-time low; #1 frustration "AI solutions that are almost right." Tools that make agent claims *checkable* sit in this gap.
- **DORA 2025:** AI amplifies existing team quality; success capabilities include strong version control and quality internal docs — tether is an instrument for both.
- **Counter-signals:** Optic dead, Swimm pivoted. Drift detection thrives as an **embedded workflow primitive**, not a standalone product. Tether's git-native CLI + agent hooks shape matches the surviving form; the deterministic-fingerprint approach is currently uncontested in the agent niche.
