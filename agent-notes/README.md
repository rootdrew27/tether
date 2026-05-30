# agent-notes/

Claude's writable documentation space for the tether project.

`tether-vault/` is human-authored and read-only for Claude, enforced by deny rules in
`.claude/settings.json`. This directory is the counterpart: the documentation Claude
maintains, plus any working notes it generates. Claude may freely create, edit, and
delete files here.

Contents:

- `design/` — the MVP design spec (`Tether-Design-MVP.md`) and per-area elaborations;
  `design/future/` holds the forward-state model and vocabulary.
- `research/` — pre-MVP surveys of comparable systems and Claude Code integration surfaces.
- `claude-code/` — the Claude Code integration spec, its open items, and a `strategies/`
  subfolder for deferred strategies.

## Format

This space sits at the repo root, outside the Obsidian vault, so its docs are read in
VSCode and on GitHub — not Obsidian. They use **standard GitHub-flavored markdown, with
no YAML frontmatter and no Obsidian syntax:**

- **No YAML frontmatter.** Start each doc with its first heading or intro paragraph, not
  a `---` properties block.
- **Relative links, not wikilinks** — `[Normalization](Normalization.md)`,
  `[Future-Work](../design/Future-Work.md)`, not `[[Normalization]]`. Heading anchors use
  GitHub slugs: `[Git Integration](../../tether-vault/DICTION.md#git-integration)`.
- **GitHub alerts, not Obsidian callouts** — `> [!NOTE]`, `> [!WARNING]` instead of
  `> [!info]+`.
- Avoid `==highlights==`, `%%comments%%`, `![[embeds]]`, and `#tags`.

(The Obsidian vault `tether-vault/` keeps its own Obsidian conventions; those rules do not
apply here.)

This is project infrastructure for working *on* tether. It is not part of the tether
package and is never installed into a user's project.
