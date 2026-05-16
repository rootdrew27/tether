---
title: Vault overview
tags:
  - meta
  - vault
type: meta
status: active
---

## Purpose

This vault holds the design notes, research, and integration strategies for the **tether** project. Source code lives at `..` (the parent repo). Treat the vault as the source of truth for design intent, drift behavior, vocabulary, and Claude Code integration design; treat the repo's `CLAUDE.md` and `pyproject.toml` as the source of truth for code, dependencies, and conventions.

## Structure

| Path | Contents |
| --- | --- |
| `DICTION.md` | Canonical MVP vocabulary. Matches what the code does today; imported into the project's `CLAUDE.md`. |
| `TODO.md` | Active work list. |
| `design/` | MVP design spec (`Tether-Design-MVP.md`), per-area elaborations (`Normalization.md`, `Git-Integration.md`), and `Future-Work.md` -- the catalog of deferred ideas not specific to the Claude Code integration. |
| `design/future/` | Docs describing forward-state model and behavior that does not yet match MVP code. Includes `DICTION-Future.md` (vocabulary written against the target data model: sub-file locators, region hashes, reconcile) and `Drift-Cases.md` (sub-file region drift cases). New docs that describe future-state design land here. |
| `claude-code/` | Claude Code integration spec (`Claude-Code-Integration.md`), open items (`Claude-Code-Integration-Open.md`), and a `strategies/` subfolder for deferred integration strategies. |
| `research/` | Raw research notes from earlier design exploration. |

## Conventions

- **Filenames use Title-Case-Kebab** so Obsidian wikilinks (`[[File-Name]]`) resolve predictably. Acronyms stay uppercase (`MVP`, `CC`).
- **Use [[DICTION]] vocabulary** when introducing or referring to tether concepts (MVP terms — what the code does today). For forward-state work, [[DICTION-Future]] is the matching glossary. The "Aliases to avoid" column in each note is authoritative.
- **Describe current state only.** Do not record change history in vault docs -- notes about previous behavior, what was changed, or when belong in git history, not in prose. Include change history only when explicitly asked.

## Working with PDFs in this vault

Tether's `dev` dependency group includes `pdfplumber`, `pytesseract`, and `pdf2image`. Run scripts via `uv run python` from the repo root (`..` relative to this file):

- **`pdfplumber`** -- extract embedded text, tables, and metadata from PDFs.
- **`pytesseract`** + **`pdf2image`** -- OCR text from images within PDFs. Use `pdf2image.convert_from_path()` to rasterize pages, then `pytesseract.image_to_string()` to extract text. Requires system packages `tesseract-ocr` and `poppler-utils` (install once via `sudo apt install tesseract-ocr poppler-utils`).

Prefer these over the Read tool when pages contain text rendered as images.

## Obsidian conventions

For Obsidian CLI usage, linking, frontmatter, callouts, Mermaid syntax, embeds, tags, formatting, and style see:

@OBSIDIAN.md
