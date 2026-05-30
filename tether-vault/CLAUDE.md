---
title: Vault overview
tags:
  - meta
  - vault
type: meta
status: active
---

## Purpose

This vault holds the human-authored design notes, research, etc. for the **tether** project. Treat the vault as the source of truth for design intent, drift behavior, vocabulary, and Claude Code integration design, etc.                                 

## Conventions

- **Filenames use Title-Case-Kebab** so Obsidian wikilinks (`[[File-Name]]`) resolve predictably. Acronyms stay uppercase (`MVP`, `CC`).
- **Use [[DICTION]] vocabulary** when introducing or referring to tether concepts (MVP terms — what the code does today). The "Aliases to avoid" column in each note is authoritative.

## Working with PDFs in this vault

Tether's `dev` dependency group includes `pdfplumber`, `pytesseract`, and `pdf2image`. Run scripts via `uv run python` from the repo root (`..` relative to this file):

- **`pdfplumber`** -- extract embedded text, tables, and metadata from PDFs.
- **`pytesseract`** + **`pdf2image`** -- OCR text from images within PDFs. Use `pdf2image.convert_from_path()` to rasterize pages, then `pytesseract.image_to_string()` to extract text. Requires system packages `tesseract-ocr` and `poppler-utils` (install once via `sudo apt install tesseract-ocr poppler-utils`).

Prefer these over the Read tool when pages contain text rendered as images.

## Obsidian conventions

For Obsidian CLI usage, linking, frontmatter, callouts, Mermaid syntax, embeds, tags, formatting, and style see:

@OBSIDIAN.md
