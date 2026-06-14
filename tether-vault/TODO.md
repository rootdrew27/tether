---
title: TODO
tags:
  - meta
  - todo
type: meta
status: active
---
## Pre-"Break My Product" Goals
- [ ] Improve onboarding skill -> it should be usable for most repos
- [ ] Create install instructions
- [ ] New playground (`claude --resume new-playground`)
## Current
- [x] Clean documentation
	- [x] Remove redundancies
	- [x] Remove out-dated or inaccurate info
- [x] Split documentation into **For Claude** and **For Me**
- [x] Remove tests, simplify/organize codebase (the rendering in particular)
- [x] Simplify: Remove XML rendering -- keep light markdown and JSON
- [x] Finish implementing the `/tether-onboard` skill into the evals (`claude --resume onboarding-skill-added-to-evals`)
- [ ] New playground
- [ ] Review the Tether positioning analysis (`claude --resume tether-cli-positioning-analysis`)
- [ ] Implement Line-span tethers
- [ ] Make the quick MultiEdit removal fix (`claude --resume remove-deprecated-multiedit-references`)
- [ ] Enhanced testing framework for Claude Code integration (resume via `claude --resume testing-framework-enhancement`)
	- Example scenarios like the one described in Case 01 should be simulated.   
	-  Do hooks fire? Does Claude respond appropriately given certain states? Are tethers maintained?
	- Consider **explicit** vs **implicit** metrics 
	- https://claude.ai/share/77b79a9d-39c4-4d03-8449-ee95129e2e37
- [ ] Implement "onboard" feature (e.g. a Claude Code Skill) to create tethers for an existing project 
- [ ] Setup CI/CD
- [ ] Use `tether` to develop `tether`!
	- [ ] Create Claude Skill to create tethers in a new repository
- [ ] Convert GitHub to public and create package
## Dev Tools
- [x] Simple Claude Skill for commits (should be callable by claude or user)
- [x] Create a precommit hook for formatting, linting, and type checking (and/or include these commands in the claude skill for committing)
- [ ] Convert `mk-commit-msg` to `prepare-for-commit`
	- It will focus heavily on finalizing the feature, fix, refactor relevant to the current changes, rather than making a commit msg; though, a commit message will still be the final output.
## Future
- [ ] Implement Watcher
	- [ ] Have the watcher occasionally check the CLAUDE.md, settings.json, settings.local.json, etc. for misconfigurations.
## Considerations
- [ ] Use pretool usage hooks or add a `tether show ...` command so that Claude can see info about tethers (i.e. read the descriptions)
- [x] Add a `tether show` command for displaying tethers regardless of their status (structural-only, paged plain-text list; no drift computation).