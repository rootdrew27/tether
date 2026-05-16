---
title: TODO
tags:
  - meta
  - todo
type: meta
status: active
---

## Current
- [ ] Clean documentation
	- [ ] Remove redundancies
	- [ ] Remove out-dated or inaccurate info
- [ ] Gain understanding of Tether
	-  What are the failure cases? Is a watcher needed for V1?
	- [ ] Test in playground
	- [ ] Update this document or others with notes on what you notice
- [ ] Enhanced testing framework for Claude Code integration (resume via `claude --resume testing-framework-enhancement`)
	- [ ] Do hooks fire?
	- [ ] Does Claude respond appropriately given certain states?
	- [ ] Are tethers maintained?
- [ ] Setup CI/CD
- [ ] Find a way to measure Claude's performance with `tether`
	- [ ] Compare it against other versions of `tether` and against Claude w/o `tether`
	- [ ] Automate this process!
- [ ] Use `tether` to develop `tether`!
- [ ] Convert GitHub to public and create package


## Future
- [ ] Implement Watcher
	- [ ] Have the watcher occasionally check the CLAUDE.md, settings.json, settings.local.json, etc. for misconfigurations.
## Considerations
- [ ] Use pretool usage hooks or add a `tether show ...` command so that Claude can see info about tethers (i.e. read the descriptions)
- [ ] Add a `tether` command for displaying tethers regardless of their status, via markdown or perhaps with a visualization.