# Publishing Tether to PyPI

A step-by-step runbook for releasing `tether` to PyPI, grounded in the project's
actual packaging setup and current (2025–2026) PyPA standards.

The code is the source of truth for current behavior; this doc is the source of
truth for the release process and rationale.

## State of the project (what's ready, what's missing)

Reviewed against `pyproject.toml`, the package tree, and the README:

**Ready**
- Build backend is set: `hatchling` (`[build-system]`).
- Wheel target is correct: `[tool.hatch.build.targets.wheel] packages = ["tether"]`.
- Console script is wired: `tether = "tether.cli:main"`.
- `requires-python = ">=3.11"` is set. The floor may sit below `.python-version`
  (which pins the dev interpreter at 3.12); the package supports 3.11+.
- The package is **pure Python** — nothing under `tether/` is a non-`.py` data
  file, and `tether/claude_code/` reads only the *target project's* files at
  runtime (its hook/fragment/skill/settings content is embedded as Python
  strings). So no `package-data` / `force-include` is needed; the default wheel
  target captures everything.
- **The distribution name is `tether-it`.** The bare name `tether` is on PyPI's
  prohibited list ("This project name isn't allowed"), so the package publishes
  as `tether-it` (`pip install tether-it`) — the import package and the `tether`
  CLI command are unchanged. `tether-it` is unclaimed (JSON API returns 404), and
  PyPI is first-to-upload, so the first successful publish claims it. The built
  artifact normalizes to `tether_it-<ver>-*.whl` / `tether_it-<ver>.tar.gz`.

**Missing / must address before a good release**
1. **No `LICENSE` file and no `license` metadata.** Required for a respectable
   listing and for anyone to legally use the package. This is a decision you
   must make (see Step 1).
2. **Sparse listing metadata.** No `authors`, `keywords`, `classifiers`, or
   `[project.urls]`. PyPI renders these on the project page; without them the
   listing is bare.
3. **Version is single-sourced** — `pyproject.toml`'s `[project].version` is the
   sole version literal; `tether/__init__.py` derives `__version__` from the
   installed package metadata, so `tether --version` and the wheel can't desync.
   Not an action item: just bump `pyproject.toml` when releasing (see Step 2b).
4. **README uses repo-relative links** (`agent-notes/`, `tether-vault/...`).
   `readme = "README.md"` becomes the PyPI long description, and relative links
   **break on the PyPI page**. Convert the links you want to keep to absolute
   `https://github.com/rootdrew27/tether/...` URLs (see Step 3).
5. **`dist/` already holds wheels**, including
   `tether-0.1.0+g722f28d-py3-none-any.whl`. The `+g722f28d` is a *local version
   label* — **PyPI rejects local versions**. Always build fresh into a clean
   `dist/` for a release (Step 5); never publish the smoke-stamped artifact.

---

## Decisions you need to make

Two choices drive the rest. Pick before starting:

- **License.** Recommended: **MIT** (shortest, most permissive, ubiquitous for
  dev tooling). **Apache-2.0** is the main alternative — same permissiveness
  plus an explicit patent grant and a `NOTICE` convention; choose it if patent
  clarity matters to you. The runbook uses MIT in examples; swap the SPDX id and
  file contents if you choose otherwise.
- **Publish method.** Two supported paths, both documented below:
  - **A — Manual `uv publish` with an API token.** Fastest for a first release
    from your laptop. Fewer moving parts. (Step 6A)
  - **B — Trusted Publishing from GitHub Actions (OIDC).** The PyPA-recommended
    path: no long-lived secrets, publishes on a tag push, auto-emits PEP 740
    attestations. More setup up front. (Step 6B)
  - Recommendation: do the **TestPyPI dry run (Step 5) + manual publish (6A)**
    for `0.1.0` to claim the name and confirm the artifact installs, then adopt
    **Trusted Publishing (6B)** for all subsequent releases.

> Note: PyPI requires **2FA on your account** and no longer accepts a real
> username/password for uploads — only an API token (`__token__`) or a Trusted
> Publisher. Enable 2FA at https://pypi.org/manage/account/ before publishing.

---

## Step 1 — Add a LICENSE file

Create `LICENSE` at the repo root. For MIT, the contents are:

```
MIT License

Copyright (c) 2026 Andrew Root

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Confirm the copyright holder name/year. `git add LICENSE`.

---

## Step 2 — Fill in `pyproject.toml` metadata

Part (a) adds richer `[project]` metadata (the action item here). Part (b)
documents the version setup, which is already single-sourced — nothing to change.

### 2a. Metadata (PEP 621 + PEP 639)

Replace the current `[project]` block with the following. Note the modern
license form — **`license` is an SPDX expression string**, and `License ::`
Trove classifiers are deprecated (PEP 639), so do not add one.

```toml
[project]
name = "tether-it"
version = "0.1.0"
description = "Typed-relationship annotation layer over content, layered on git"
readme = "README.md"
requires-python = ">=3.11"
license = "MIT"
license-files = ["LICENSE"]
authors = [
    { name = "Andrew Root", email = "andrew.root@dentalagent.io" },
]
keywords = ["git", "documentation", "drift", "code-relationships", "claude-code"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "Topic :: Software Development :: Documentation",
    "Topic :: Software Development :: Version Control :: Git",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Operating System :: OS Independent",
    "Environment :: Console",
]
dependencies = [
    "click>=8.1.7",
    "msgspec>=0.19.0",
    "uuid-utils>=0.10.0",
]

[project.urls]
Homepage = "https://github.com/rootdrew27/tether"
Repository = "https://github.com/rootdrew27/tether"
Issues = "https://github.com/rootdrew27/tether/issues"
```

(`Development Status :: 3 - Alpha` matches the README's "WIP, no released users"
banner. Bump it as the project matures.)

### 2b. Version single-sourcing (already in place)

`pyproject.toml`'s `[project].version` is the **single source of truth**.
`tether/__init__.py` derives the version from the installed package metadata:

```python
from importlib.metadata import version

__version__ = version("tether-it")  # argument is the distribution name, not the import package
```

`cli.py` surfaces that as `tether --version`, so the CLI, the package metadata,
and the built wheel always agree — there is no second literal to desync. **Bump
a release by editing `pyproject.toml`'s `version` only.**

Keep `version` a **static literal** — do *not* switch to PEP 621
`dynamic = ["version"]`. `evals/margin/scripts/run-smoke.sh` stamps the smoke
wheel by `sed`-ing that exact `version = "..."` line into a local version
(`0.1.0+g<sha7>`); removing the literal would silently break the stamp and the
`verify-smoke.py` cross-check.

> The `pyproject.toml ↔ tether/__init__.py` coupling is recorded as tether
> `019ec7b1-02c5-...`; if you change how the version is wired, update and
> refresh it.

---

## Step 3 — Make the README render well on PyPI

`readme = "README.md"` is published verbatim as the project's long description.
Repo-relative links (`agent-notes/...`, `tether-vault/DICTION.md`, etc.) resolve
against `https://pypi.org/project/tether-it/` and **break**. `twine check` does
**not** catch this.

- Convert links you want functional on PyPI to absolute URLs, e.g.
  `https://github.com/rootdrew27/tether/blob/master/agent-notes/design/Tether-Design-MVP.md`.
- Sanity-check the rendered description after building with
  `uvx twine check dist/*` (validates metadata + that the long description
  renders) and, for a true preview, the TestPyPI upload in Step 5.

This is optional for a functional release but recommended for a clean listing.

---

## Step 4 — Pre-flight checks

From the repo root, confirm the project is green before building:

```bash
uv run pytest          # full suite passes
uv run ruff check      # lint clean
uv run pyright         # type-clean
uv run tether --help   # CLI imports and runs
```

---

## Step 5 — Build, verify, and dry-run on TestPyPI

TestPyPI is a separate instance with a **separate account** — register at
https://test.pypi.org/account/register/ (enable 2FA there too).

### 5a. Build a clean artifact set

```bash
rm -f dist/*.whl dist/*.tar.gz      # clear the smoke-stamped wheels
uv build --no-sources               # builds BOTH sdist (.tar.gz) and wheel (.whl) into dist/
```

`--no-sources` ignores any `[tool.uv.sources]` dev overrides so the artifact
matches what a clean build elsewhere would produce. Confirm the filenames have
**no** local `+g...` segment (e.g. `tether_it-0.1.0-py3-none-any.whl` and
`tether_it-0.1.0.tar.gz`).

### 5b. Validate metadata

```bash
uvx twine check --strict dist/*
```

(`uvx` runs twine without adding it as a project dependency.) This must pass
before any upload.

### 5c. Upload to TestPyPI

Create a TestPyPI API token at https://test.pypi.org/manage/account/token/
(scope "Entire account" — the project doesn't exist there yet), then:

```bash
uv publish \
  --publish-url https://test.pypi.org/legacy/ \
  --token pypi-<your-testpypi-token>
```

### 5d. Install back from TestPyPI to verify

Use an isolated, throwaway environment. The extra index is essential so the real
runtime deps (`click`, `msgspec`, `uuid-utils`) resolve from real PyPI:

```bash
uv run --no-project --isolated \
  --index https://test.pypi.org/simple/ \
  --index-strategy unsafe-best-match \
  --with tether-it \
  -- tether --version
```

It should print the version you built. If that works, the real publish will too.

---

## Step 6A — Publish to PyPI manually (`uv publish`)

For the first release / claiming the name.

1. Create a PyPI API token at https://pypi.org/manage/account/token/. For the
   **first** upload the token must be scoped **"Entire account"** (the project
   doesn't exist yet).
2. Build fresh (if you changed anything since Step 5a) and re-check:
   ```bash
   rm -f dist/*.whl dist/*.tar.gz
   uv build --no-sources
   uvx twine check --strict dist/*
   ```
3. Publish:
   ```bash
   uv publish --token pypi-<your-pypi-token>
   # or: export UV_PUBLISH_TOKEN=pypi-<token> && uv publish
   ```
4. Verify the live page: https://pypi.org/project/tether-it/ and a clean install:
   ```bash
   uv run --no-project --isolated --with tether-it -- tether --version
   ```
5. **Harden the token:** once the project exists, delete the account-wide token
   and (if you'll publish manually again) create a new one **scoped to the
   `tether-it` project**. Better yet, switch to Trusted Publishing (6B).

---

## Step 6B — Publish via Trusted Publishing (GitHub Actions, recommended ongoing)

No stored secrets; GitHub Actions authenticates to PyPI over short-lived OIDC.
Publishes when you push a version tag and auto-emits PEP 740 attestations.

### 6B.1 Configure a pending publisher on PyPI

If `tether-it` does **not** exist yet on PyPI, configure this from your account (it
creates the project on first publish). Go to
https://pypi.org/manage/account/publishing/ → "Add a new pending publisher" →
**GitHub Actions**, and enter:

- **PyPI Project Name:** `tether-it` (the distribution name; `tether` is prohibited)
- **Owner:** `rootdrew27`
- **Repository name:** `tether` (the GitHub repo name is unchanged)
- **Workflow filename:** `publish.yml`
- **Environment name:** `pypi` (recommended)

> A pending publisher does **not** reserve the name — if someone uploads
> `tether-it` first, it's invalidated. If you already published `0.1.0` via 6A, add
> the trusted publisher from the **project's** settings instead (Manage →
> Publishing on the project page).

### 6B.2 Add the workflow

Create `.github/workflows/publish.yml`:

```yaml
name: Publish to PyPI

on:
  push:
    tags: ["v*"]

jobs:
  build:
    name: Build distribution
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - name: Install uv
        uses: astral-sh/setup-uv@v6
      - name: Build sdist and wheel
        run: uv build --no-sources
      - name: Verify metadata
        run: uvx twine check --strict dist/*
      - name: Upload build artifacts
        uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/

  publish-to-pypi:
    name: Publish to PyPI
    needs: [build]
    runs-on: ubuntu-latest
    environment:
      name: pypi
      url: https://pypi.org/p/tether-it
    permissions:
      id-token: write          # MANDATORY for trusted publishing — without it OIDC fails
    steps:
      - name: Download dists
        uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/
      - name: Publish
        uses: pypa/gh-action-pypi-publish@release/v1
```

Notes:
- The YAML above is the baseline; **the committed `.github/workflows/publish.yml`
  is authoritative.** It additionally checks out full history (`fetch-depth: 0`)
  and runs a **master-only guard** in the build job that refuses to publish unless
  the tagged commit is contained in `origin/master`
  (`git merge-base --is-ancestor "$GITHUB_SHA" origin/master`) — so a tag created
  on any other branch can't release. A GitHub Environment *branch* rule cannot
  express this, because a tag push carries a tag ref, not a branch ref.
- `@release/v1` is PyPA's recommended moving ref; it stays current.
- The `environment: pypi` name must match what you set on PyPI in 6B.1.

### 6B.3 Release by tagging

The version comes from `pyproject.toml`'s `[project].version` (Step 2b). To cut
a release:

```bash
# 1. Bump version in pyproject.toml (e.g. to 0.1.0), commit it.
# 2. Tag and push:
git tag v0.1.0
git push origin v0.1.0
```

The tag push triggers the workflow, which builds, checks, and publishes. The
**first** successful run converts the pending publisher to active and creates
the project. Watch it under the repo's **Actions** tab; confirm at
https://pypi.org/project/tether-it/.

> Keep the `v` prefix on the git tag (`v0.1.0`) consistent with the `tags:
> ["v*"]` trigger; the PyPI version itself comes from `pyproject.toml`, not the
> tag.

---

## Releasing subsequent versions

1. Make changes; ensure pre-flight (Step 4) is green.
2. Bump `version` in `pyproject.toml` (PyPI versions are **immutable** — you can
   never re-upload a version, even after deleting/yanking, so every release
   needs a new number).
3. Update a `CHANGELOG.md` if you keep one (and add a `Changelog` entry to
   `[project.urls]`).
4. Commit, then `git tag vX.Y.Z && git push origin vX.Y.Z` (path 6B), or rebuild
   and `uv publish` (path 6A).

---

## Common pitfalls (quick reference)

- **Version immutability:** "File already exists" → bump the version; you cannot
  overwrite. Prefer *yanking* a bad release over deleting it.
- **Local version labels:** never publish a `+g<sha>` artifact (the smoke build
  produces these). Build releases with a clean `dist/`.
- **Missing `id-token: write`:** the #1 Trusted-Publishing failure. It must be on
  the publishing job.
- **2FA / token-only uploads:** username+password is rejected. Use a token
  (`__token__`) or OIDC.
- **Name normalization:** PyPI treats `-`, `_`, `.` and case as equivalent
  (`tether` is unambiguous here, but keep `pyproject` `name` and the
  pending-publisher name normalize-equal).
- **README relative links break on PyPI** (Step 3) — `twine check` won't warn.

## Sources

- uv — Building and publishing: https://docs.astral.sh/uv/guides/package/
- PyPI — Trusted Publishers: https://docs.pypi.org/trusted-publishers/
- PyPA — Publishing with GitHub Actions:
  https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/
- PEP 639 (license metadata): https://peps.python.org/pep-0639/
- PyPA — Writing pyproject.toml:
  https://packaging.python.org/en/latest/guides/writing-pyproject-toml/
- PyPA — Using TestPyPI:
  https://packaging.python.org/en/latest/guides/using-testpypi/
</content>
</invoke>
