---
title: TODO
tags:
  - meta
  - todo
type: meta
status: active
---

## Current
- [x] Clean documentation
	- [x] Remove redundancies
	- [x] Remove out-dated or inaccurate info
- [ ] Research memory systems, coding agents, evals, etc.
- [ ] Gain understanding of Tether
	- How is git used? What other git internals could be used?
	-  What are the failure cases? Is a watcher needed for MVP?
	- Review Case Study 01
- [ ] Enhanced testing framework for Claude Code integration (resume via `claude --resume testing-framework-enhancement`)
	- Example scenarios like the one described in Case 01 should be simulated.x   
	-  Do hooks fire? Does Claude respond appropriately given certain states? Are tethers maintained?
	- Consider **explicit** vs **implicit** metrics 
- [ ] Setup CI/CD
- [ ] Use `tether` to develop `tether`!
	- [ ] Create Claude Skill to create tethers in a new repository
- [ ] Convert GitHub to public and create package
## Dev Tools
- [ ] Simple Claude Skill for commits (should be callable by claude or user)
- [ ] Create a precommit hook for formatting, linting, and type checking (and/or include these commands in the claude skill for committing)
## Future
- [ ] Implement Watcher
	- [ ] Have the watcher occasionally check the CLAUDE.md, settings.json, settings.local.json, etc. for misconfigurations.
## Considerations
- [ ] Use pretool usage hooks or add a `tether show ...` command so that Claude can see info about tethers (i.e. read the descriptions)
- [ ] Add a `tether` command for displaying tethers regardless of their status, via markdown or perhaps with a visualization.