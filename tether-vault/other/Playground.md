# Playground

`playground/` at the repo root is a gitignored scratch dir for hand-testing
tether against a realistic project. It is not part of the main repo's git
tree, and nothing about its layout is shipped to users.

## Git convention

`playground/` has its own local git repo, separate from the main tether
repo. The pristine source lives on:

- **Tag `fresh`** — immutable pointer to the canonical pristine commit.
- **Branch `fresh`** — mutable, points at the tag by default. The reset
  script force-moves it back to the tag every run, so any experimental
  commits made on this branch are discarded on reset (recoverable via
  reflog for the usual window).

Hand-experiment on a different branch (`git checkout -b experiment`) if
you want commits to survive reset.

## Reset

    uv run python scripts/reset_playground.py

Force-resets `fresh` to the tag, removes every untracked or ignored file
(`.venv`, `__pycache__`, `.pytest_cache`, `.tether/`, `.claude/`,
hand-edits), and re-runs `uv sync` to recreate the venv.

## Bootstrapping a new playground

`playground/` is gitignored, so a fresh clone of the main repo will not
have one. To create yours:

    mkdir playground && cd playground
    # drop in whatever source you want as the pristine state
    git init -q
    git add <files>            # do NOT add .tether/, .claude/, CLAUDE.md
    git commit -m "fresh"
    git branch -m fresh        # rename default branch to fresh
    git tag fresh              # immutable pointer to the pristine commit

After that, `scripts/reset_playground.py` will work.

## Updating the fresh state

To change what counts as "fresh" (add a source file, swap the example
app, etc.) the tag must be force-moved:

    cd playground
    git checkout fresh
    # edit files
    git add <files> && git commit --amend     # or a fresh commit
    git tag -f fresh                          # move the tag to the new commit
