---
title: TODO
tags:
  - meta
  - todo
type: meta
status: active
---
## Pre-"Break My Product" Goals
- [ ] Update README and ensure setup instructions are followable
- [ ] Improve visuals (e.g. `tether show`)
- [ ] Discourage Claude from surfacing tether decisions. Tether should operate in the background as far as the user is concerned.
- [ ] Improve onboarding skill -> it should be usable for most repos
## Current
- [x] Split documentation into **For Claude** and **For Me**
- [x] Remove tests, simplify/organize codebase (the rendering in particular)
- [x] Simplify: Remove XML rendering -- keep light markdown and JSON
- [x] Finish implementing the `/tether-onboard` skill into the evals (`claude --resume onboarding-skill-added-to-evals`)
- [x] New playground
- [ ] Review the Tether positioning analysis (`claude --resume tether-cli-positioning-analysis`)
- [ ] Find way to track and/or estimate token usage due to tether
- [ ] Fix issue with Stop hook (when the artifact of a non-editable artifact is DRIFTED the stop hook may keep claude running ~infinitely)
- [ ] Implement Line-span tethers (or implement python and markdown parsers)
- [ ] Make the quick MultiEdit removal fix (`claude --resume remove-deprecated-multiedit-references`)
- [ ] Enhanced testing framework for Claude Code integration (resume via `claude --resume testing-framework-enhancement`)
	- Example scenarios like the one described in Case 01 should be simulated.   
	-  Do hooks fire? Does Claude respond appropriately given certain states? Are tethers maintained?
	- Consider **explicit** vs **implicit** metrics 
	- https://claude.ai/share/77b79a9d-39c4-4d03-8449-ee95129e2e37
- [ ] Setup CI/CD
- [x] Use `tether` to develop `tether`!
- [ ] Convert GitHub to public and create package
## Dev Tools
- [x] Simple Claude Skill for commits (should be callable by claude or user)
- [x] Create a precommit hook for formatting, linting, and type checking (and/or include these commands in the claude skill for committing)
- [ ] Write a convenience command for uninstalling tether from a project (mostly for development purposes but it also may be useful for users if breaking changes are made to the project)
- [ ] Convert `mk-commit-msg` to `prepare-for-commit`
	- It will focus heavily on finalizing the feature, fix, refactor relevant to the current changes, rather than making a commit msg; though, a commit message will still be the final output.
## Future
- [ ] Implement Watcher
	- [ ] Have the watcher occasionally check the CLAUDE.md, settings.json, settings.local.json, etc. for misconfigurations.
## Considerations
- [ ] Use pretool usage hooks or add a `tether show ...` command so that Claude can see info about tethers (i.e. read the descriptions)
- [x] Add a `tether show` command for displaying tethers regardless of their status (structural-only, paged plain-text list; no drift computation).