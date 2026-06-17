# README

Tether is an agent-first, semantic relationship database. It is a simple database, storing one type of object (a tether), and is easily interfaced via CLI commands (e.g. `tether status`).

A **tether** is a link between two objects (e.g. files) indicating a relationship, and optionally describing that relationship. This is easily understood when viewing the data model:

```json
{
  "a": {
    "fingerprint": "a3a02...",
    "path": "script.py"
  },
  "b": {
    "fingerprint": "e417b...",
    "path": "doc.md"
  },
  "description": "The doc.md file details the program implemented in script.py",
}
```

> [!NOTE] A few fields of the tether are not included in order to not overwhelm the reader

As seen above, a tether consists of two artifacts, `a` and `b`, as well as a description. The description makes the connection a semantic one.

## Concepts

| Term | Meaning |
|---|---|
| **Tether** | A declaration of connection between two **artifacts**, with content fingerprints recorded at both ends and a required description. |
| **Artifact** | One end of a tether: a path plus a locator. In MVP the locator is always `WholeFile`. |
| **Fingerprint** | The git blob OID of the artifact's content, captured at tether creation or refresh. |
| **Drift** | The condition where current content no longer matches the fingerprint. |
| **HEALTHY / DRIFTED / BROKEN** | Per-artifact state. A tether's aggregate is the most severe of its two artifacts. |

Full glossary: [`DICTION.md`](tether-vault/DICTION.md) (MVP vocabulary, matches current code). Forward-state model lives in [`DICTION-Future.md`](agent-notes/design/future/DICTION-Future.md).

## Relationship Layer

If **Git** is the content layer, then **Tether** is the relationship layer.

Tether is built on top of Git, though any VCS would likely suffice, and as such, it relies on, and exploits, the many advantages of having a version-control.

Tether uses a simple database, consisting of tethers, which should be included in git commits.

## Requirements

- **Python 3.11+**
- **A git repository.** Tether records fingerprints as git blob OIDs, so `tether init` refuses to run outside a git work tree.

## Install

> **Naming:** the PyPI package is **`tether-it`** (the bare name `tether` is
> reserved on PyPI), while the command you run and the Python package you import
> are both `tether`, and the GitHub repo is
> [`rootdrew27/tether`](https://github.com/rootdrew27/tether). In short —
> `pip install tether-it`, then use `tether`.

Tether is a CLI. Install it as a standalone tool:

```bash
uv tool install tether-it  # with uv
# or
pipx install tether-it     # with pipx
```

…or add it to a project's environment:

```bash
uv add tether-it
```

Confirm it resolves:

```bash
tether --help
```

## Quick start

```bash
cd my-project
tether init                                    # create .tether/ in the repo

# Link two files whose content must stay aligned:
tether add docs/auth.md src/auth.py \
  --description "The auth.md specifies password reset and 2FA enrollment implemented in the auth module."

tether status                                  # both ends HEALTHY
# …edit src/auth.py…
tether status                                  # src/auth.py now DRIFTED
tether status <id>                             # per-artifact view + unified diff

# Once the doc is back in line with the code, ratify the alignment:
tether refresh <id>                            # re-fingerprint both ends
```

`refresh` is the explicit assertion that the two ends are aligned again — not an automatic side effect of editing. Until you refresh, the drift signal stands.

## Claude Code

Tether is agent-first: it ships a Claude Code integration that keeps a coding agent aware of drift as it works.

```bash
tether init claude-code
```

This installs, in the current project:

- a **memory fragment** (`.tether/tether.md`, imported into `CLAUDE.md`) teaching the agent the tether vocabulary and how to react to drift;
- **SessionStart** and **Stop** hooks that surface drifted or broken tethers at the start of a session and when the agent finishes a turn;
- **permission rules** that route the agent through the `tether` CLI — blocking hand-edits under `.tether/` and pre-approving the read-only subcommands;
- a **`/tether-onboard` skill** for seeding a project's initial tether graph.

### Seed the graph with `/tether-onboard`

In a project that has no tethers yet, invoke the skill from Claude Code:

```
/tether-onboard
```

The agent surveys the repository, proposes candidate relationships (doc↔code, test↔code, schema↔consumer, registry↔variants, and more), judges each one with **precision over recall**, records the keepers via `tether add` with quality descriptions, and reports coverage at the end. It runs autonomously and only when you invoke it — it never triggers on its own.

From then on, when the agent reads a tethered file, tether injects that file's relationships and their drift state alongside the content, so coordinated edits happen within the turn.

## CLI reference

| Command | Purpose |
|---|---|
| `tether init` | Initialize `.tether/` in the current git repo. |
| `tether init claude-code` | Install the Claude Code integration (hooks, permissions, memory fragment, onboard skill). |
| `tether add A B --description "…"` | Create a tether. `--description` is required. |
| `tether status [ID] [--json] [--plain] [--no-color] [--diff/--no-diff]` | Report tether state; per-artifact view + diff for one ID, summary for all. |
| `tether show [--plain] [--no-color]` | List every tether with its description, regardless of state. |
| `tether refs PATH [--json] [--plain] [--no-color]` | List tethers referencing a path. |
| `tether coverage [--list-untethered-files] [--list-tethered-files] [--json]` | Report what fraction of git-tracked files participate in a tether. |
| `tether refresh ID` | Re-fingerprint both artifacts; assert they are aligned. |
| `tether update ID [--a-path P] [--b-path P] [--description …]` | Change a path or description without touching fingerprints. |
| `tether mv OLD NEW` | Rewrite every tether artifact pointing at OLD to NEW. |
| `tether rm ID` | Delete a tether record. |

`status`, `show`, and `refs` adapt to where their output goes: on a terminal they render a colorized, aligned view; piped or run by an agent they emit plain text (`status`, `show`) or JSON (`refs`). Force a surface with `--json` / `--plain`, or keep the layout without color via `--no-color`.

## How drift works

`tether status` resolves each artifact against the current on-disk bytes and compares its git blob OID to the recorded fingerprint:

- **HEALTHY** — the OID matches.
- **DRIFTED** — the file exists but its content's OID differs.
- **BROKEN** — the file is no longer at the recorded path; tether feeds the path and fingerprint to git's rename detector and surfaces the most content-similar file as a rename candidate.

When the raw OIDs disagree, tether re-runs the comparison through a language-agnostic normalizer (line endings, BOM, trailing whitespace, EOF newlines, leading-tab expansion). If the normalized content matches, the artifact stays HEALTHY and the difference is reported as encoding-only.

## Storage & version control

State lives as one JSON file per tether under `.tether/tethers/<uuid7>.json` (sorted-key, pretty-printed), committed alongside your content. The graph is reviewable in pull requests and travels with the repo, and `git log .tether/tethers/<id>.json` is a tether's audit trail — when it was created, refreshed, and retargeted.

## Documentation

- [Glossary (`DICTION.md`)](https://github.com/rootdrew27/tether/blob/master/tether-vault/DICTION.md) — the canonical MVP vocabulary.

## License

[MIT](https://github.com/rootdrew27/tether/blob/master/LICENSE)

