---
title: Git integration
tags:
  - design
  - git
type: design
status: active
---

This document elaborates on how tether's data shape rides on top of git's working-tree, branch, and history operations. The conceptual point — that putting tether records in `.tether/tethers/*.json` makes the relationship graph branch, merge, and time-travel as one unit with the code — is in [[Tether-Design-MVP]] under §"How tether is version controlled by git". This doc walks through each mechanism.

## Branching

A feature branch can introduce new tethers, modify existing ones, or remove them. Those changes live with the code changes that motivated them. Two parallel feature branches can each evolve their own tether graphs without interference.

## Merging

Because each tether is its own file with a globally unique ID (UUIDv7), parallel branches usually edit disjoint files. Merge conflicts on tethers are rare and meaningful — when they happen, two branches genuinely modified the *same* relationship, which is exactly the case a human reviewer should look at.

## Pull request review

A new tether shows up in a PR as one new JSON file. A reviewer can see the relationship being proposed: which two files are being linked, and the description that explains why. Modifications to existing tethers show up as field-level diffs. The PR review surface is the same one the team already uses for code.

## Time travel

`git checkout <commit>` checks out the tether graph as it existed at that commit. The state of relationships at any point in the project's history is recoverable in the same way the state of code is. This enables future features like "show me how this relationship has evolved" without tether building its own history machinery.

## Provenance

`git blame .tether/tethers/<id>.json` shows who created the tether and who refreshed it last. `git log` on the same file shows its lifecycle. This information is free; it would otherwise have to be stored as fields inside the tether record and maintained by tether's own write paths.

## Distribution

Teammates pull tethers along with code. A clone is a complete tether graph. There is no "tether server" to run, no separate sync step, no extra credentials. The relationship layer rides every operation the team already performs on the content layer.
