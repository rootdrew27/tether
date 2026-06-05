> [!NOTE]
> Pre-MVP exploration. Early-design survey of Claude Code integration surfaces; written before the integration spec was committed. Several recommendations here were not adopted — the implemented integration is documented in [Claude-Code-Integration](../claude-code/Claude-Code-Integration.md) and uses SessionStart, Stop, and a PreToolUse-on-Read hook that injects a `RefsReport` JSON payload when a tethered file is read (not PostToolUse on Edit/Write), goes through `tether status` / `tether refresh` (not a hypothetical `tether list --file`), and installs via `tether init claude-code` (not `tether --init-claude-code`). Kept as reference for revisiting these surfaces post-MVP.

## Executive Recommendation

**For tether, the most valuable mechanisms are a combination of:**

1. **Hooks (PostToolUse on Edit/Write)** — deterministic, always fires, can inject context.
2. **CLAUDE.md + project-level integration** — persistent documentation of tether surfaces.

**Why this combination:**
- Hooks ensure Claude automatically sees tether relationships whenever editing a tethered file, without requiring explicit prompts or CLI invocations.
- CLAUDE.md documents the tether system itself so Claude knows the CLI exists and how to use it.

Tether is invoked through Bash and the Python API; an MCP server is **not** part of the plan. Claude Code's own [best-practices guide](https://code.claude.com/docs/en/best-practices#:~:text=CLI%20tools%20are%20the%20most%20context%2Defficient%20way%20to%20interact%20with%20external%20services) names CLI tools as "the most context-efficient way to interact with external services," which matches tether's design constraints.

**Secondary mechanisms** (skills, subagents, slash commands) are less critical because the primary use case is ambient context injection, not explicit task workflows.

---

## Integration Mechanism Comparison

### 1. HOOKS

#### What it is
Hooks are shell commands that fire at specific lifecycle points in Claude's work (before/after tool calls, at session start, when user submits, when context compacts, etc.). They run outside the LLM, so their behavior is deterministic. Hooks receive JSON on stdin describing the event, can read/modify state, and return JSON to Claude instructing it to block, allow, add context, or update tool input.

#### How tether would use it
**PostToolUse hook on Edit/Write events:**

```json
{
  "matcher": "Edit|Write",
  "hooks": [
    {
      "type": "command",
      "command": "tether list --file $(echo \"$HOOK_INPUT\" | jq -r '.tool_input.file_path') --json 2>/dev/null | jq -R --slurpfile input <(cat) '.hookSpecificOutput.additionalContext = (input[0] | fromjson | \"Related tethers:\\n\" + (. | to_entries | map(\"\\(.key): \\(.value.type)\") | join(\"\\n\"))) | select(.additionalContext)' || true"
      ]
    }
  ]
}
```

More concretely: after Claude writes/edits a file, the hook:
1. Extracts the file path from the tool input
2. Calls `tether list --file <path> --json`
3. Formats the output and injects it into the conversation as additional context

**UserPromptSubmit hook (optional, to block risky edits):**
```json
{
  "matcher": "",
  "hooks": [
    {
      "type": "command",
      "command": "bash -c 'if [[ $PROMPT == *\"delete\"* ]] && tether reconcile --check-only &>/dev/null; then exit 2; fi; exit 0'"
    }
  ]
}
```
This example shows how you could (hypothetically) block a deletion if tether detects offline changes, though the actual use case is weaker.

#### Strengths for this use case
- **Always fires** — no need for Claude to remember to run a command or invoke a skill
- **No context cost** — runs in the harness, doesn't consume tokens
- **Can inject context** — tether relationships flow into Claude's prompt automatically
- **Can block or warn** — if you want to enforce "update spec before code," hooks can delay tool execution
- **Tool-agnostic** — works on any Edit/Write without needing tether to be a first-class tool
- **Fast feedback loop** — Claude learns about tethers as it edits, encouraging natural discovery

#### Weaknesses / footguns
- **No tool listing** — hooks don't surface tether commands in the tools list; Claude only learns about tether through context injection
- **Shell command parsing fragile** — extracting structured data from hook JSON and formatting it back is error-prone (though jq helps)
- **Context pollution** — injecting tether info on every edit can eat context tokens if tethers are verbose
- **Timing** — PostToolUse fires after the tool succeeds, so it's notification/reactionary, not preventative (PreToolUse is available but fires before we know the file path)
- **No way to update tool input** — PostToolUse can add context but not modify the Edit/Write call itself (that happens in PreToolUse, which has less info)

#### What it's NOT good for
- Guiding Claude's behavior before it acts (use PreToolUse, but you have limited data)
- Triggering side effects across the system (hooks are deterministic, not LLM-driven)

#### Event Data Available (PostToolUse)
```json
{
  "hook_event_name": "PostToolUse",
  "tool_name": "Write|Edit",
  "tool_input": {
    "file_path": "/path/to/file.txt",
    "old_string": "...",      // Edit only
    "new_string": "..."       // Edit only
  },
  "tool_response": {
    "filePath": "/path/to/file.txt",
    "success": true
  }
}
```

#### Return Value Shape (PostToolUse)
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "## Related Tethers\n- docs/spec.md --specifies--> src/foo.py\n- src/utils.py --depends-on--> src/core.py"
  }
}
```

---

### 2. SLASH COMMANDS & SKILLS

#### What it is
Slash commands (also called "custom commands" or now unified as "Skills") are invocable workflows. Users type `/command-name` or Claude invokes them automatically when relevant. They're markdown files (SKILL.md) with optional YAML frontmatter and instructions. Skills can be project-level (`.claude/skills/`) or personal (`~/.claude/skills/`). They support arguments, pre-execution shell commands (to inject dynamic data), and subagent execution.

#### How tether would use it
**Project-level skill** at `.claude/skills/tether-integrate/SKILL.md`:

```yaml
---
name: tether-integrate
description: List and review tethers for a file or the whole project. Use when you need to understand relationships between files or when editing code that has tethers.
when_to_use: When exploring file relationships, when updating code that is tethered, when refactoring
allowed-tools: Bash(tether *)
---

## Tether Integration

When working with tethered files, run:

\`\`\`bash
tether list --json
\`\`\`

Or for a specific file:

\`\`\`bash
tether list --file $0 --json
\`\`\`

Results show directional relationships. Pay special attention to files that specify the one you're editing.
```

Alternatively, a simpler reference skill that just documents the tether CLI:

```yaml
---
name: tether-commands
description: Quick reference for tether CLI
user-invocable: false
disable-model-invocation: false
---

## Tether Commands

- `tether list` — Show all tethers
- `tether list --file <path>` — Show tethers for a specific file
- `tether show <tether-id>` — Show details
- `tether add <source> <type> <target>` — Create a tether
- `tether rm <tether-id>` — Delete a tether
- `tether watch` — Stream file change events
- `tether reconcile` — Detect offline renames
```

#### Strengths for this use case
- **Claude can invoke automatically** — if description matches the task, Claude loads it without user prompting
- **Persistent project configuration** — commit to `.claude/skills/` and all team members get it
- **Supports arguments** — `/tether-integrate src/foo.py` can pass file context
- **Can grant pre-approval** — `allowed-tools: Bash(tether *)` means no permission prompts for tether calls
- **Visible in `/help`** — skill names appear in the commands list
- **Supports dynamic data injection** — `` !`tether list --json` `` embedded in skill content executes at render time

#### Weaknesses / footguns
- **Not ambient** — Claude must decide to invoke the skill or remember to do so; doesn't happen automatically on every edit
- **Skill descriptions compete for context** — if you have many skills, descriptions get truncated
- **No tool listing** — skills don't appear as tools, just as documented commands
- **Manual invocation friction** — users (humans) need to type `/tether` or ask Claude to use it
- **Argument passing is awkward** — skills receive text arguments, not structured data
- **Skill content only loads when invoked** — no persistent ambient context between skill calls

#### What it's NOT good for
- Ambient context (use hooks for that)
- Blocking Claude's actions (hooks are better)

#### Where to put it
- **Project-level** (`.claude/skills/tether-reference/SKILL.md`): checked in, shared with team
- **Personal** (`~/.claude/skills/tether-utils/SKILL.md`): personal shortcuts, all projects

---

### 3. SUBAGENTS

#### What it is
Subagents are specialized AI workers that run in isolated contexts with custom system prompts, restricted tool access, and independent permission settings. The main conversation delegates tasks to subagents; they work independently and return results. Each subagent has its own context window, so complex exploration doesn't pollute your main conversation.

#### How tether would use it
**Create `.claude/agents/tether-explorer/agent.md`:**

```yaml
---
name: tether-explorer
type: Explore
description: Explore and analyze tether relationships in the codebase
system-prompt: |
  You are a tether relationship analyzer. Your job is to explore file dependencies and relationships defined by tethers.
  When asked about a file, use `tether list --file <path>` to find its relationships.
  Summarize in a concise report of what files depend on or are related to the target.
allowed-tools: Bash(tether *) Glob Grep Read
---

# Tether Explorer Subagent

Explore tether relationships. You have access to:
- `tether list` commands
- File reading and searching tools

When exploring, always check what files specify the target file, and what files the target specifies.
```

Then in a skill or main conversation:
```
/delegate tether-explorer "What are all the files that depend on src/core.py according to tethers?"
```

The subagent runs in isolation, explores tethers, and returns a summary without flooding the main context.

#### Strengths for this use case
- **Isolates exploration** — tether lookups don't fill main context with file listings
- **Reusable across tasks** — once defined, any prompt can delegate to the explorer
- **Custom tooling** — can restrict to read-only tools + tether commands
- **Cost control** — can use cheaper model (Haiku) for tether exploration
- **Structured delegation** — explicit task with results, not ambient context

#### Weaknesses / footguns
- **Not ambient** — only runs when explicitly delegated
- **Extra latency** — spawns a separate conversation
- **Overkill for simple lookups** — subagents are heavyweight for "show me the tethers for this file"
- **No integration with main editing loop** — doesn't influence Claude's choices while editing

#### What it's NOT good for
- Real-time context during editing (use hooks)
- Simple reference material (use CLAUDE.md)

#### When to create one
- You have a complex task that requires deep exploration and would clutter the main context
- You want to let Claude delegate "figure out all the tether relationships" as a subgoal
- You're running tether analysis in a separate workflow from your editing

---

### 4. CLAUDE.MD & PROJECT MEMORY

#### What it is
CLAUDE.md files are markdown instructions that live in your project and are loaded into every Claude session. They persist across sessions as static context (not maintained by Claude, you write them). CLAUDE.md files can be in the project root, a `.claude/` directory, or nested in subdirectories. They document conventions, build commands, architecture, and instructions Claude should follow. **Auto memory** is a separate feature where Claude writes notes to itself (in `~/.claude/projects/<project>/memory/MEMORY.md`), but that's more for Claude's learnings than for documenting tether.

#### How tether would use it
**Project CLAUDE.md** at `./CLAUDE.md` or `./.claude/CLAUDE.md`:

```markdown
# Tether

This project uses **tether** to define directional relationships between files.

## Key Tether Commands

- `tether list` — Show all tethers
- `tether list --file <path>` — Show tethers related to a file
- `tether add <source> <type> <target>` — Create a tether (e.g., `tether add docs/spec.md specifies src/foo.py`)
- `tether show <id>` — View details of a tether
- `tether types` — List available tether types
- `tether reconcile` — Detect offline renames via content hash

## Workflow

When editing a file, always check if there are related tethers:

\`\`\`bash
tether list --file src/your-file.py
\`\`\`

If you edit a file that is `specifies`-d by another (e.g., a design doc), consider updating that doc alongside the code.

## Tether Types

- `specifies` — a docs/spec specifies how the code should work
- `depends-on` — a file depends on another (reverse: `depended-on-by`)
- `tests` — a test file tests a source file
- (check `tether types` for full list)

## Example Tether

```
docs/api-spec.md
  --specifies--> src/api/handler.py
  --specifies--> tests/api/test_handler.py
```

The spec document specifies how both the handler and its tests should work.
```

Or in a path-scoped rule (`.claude/rules/tether-conventions.md`):

```markdown
---
paths:
  - "**/*.py"
---

# Tether Conventions for Python Files

Python files in this project may have tethers. Before modifying a file, run:

\`tether list --file <file>\`

This shows:
- What files this file specifies
- What files specify this file
- What tests relate to this file

If a spec file specifies the code you're changing, update the spec too.
```

#### Strengths for this use case
- **Persistent project knowledge** — checked into version control, shared with team
- **No tokens spent on context** — CLAUDE.md content is loaded but static (survives compaction)
- **Low friction** — just markdown, no special configuration
- **Path-scoped rules** — can limit tether guidance to relevant file types
- **Searchable** — humans can grep the CLAUDE.md for tether info
- **Familiar format** — developers already read README.md and CLAUDE.md

#### Weaknesses / footguns
- **Not actionable by Claude** — CLAUDE.md documents tether but doesn't trigger Claude to run commands
- **Requires discipline** — Claude may forget to check tethers if not reminded by hooks
- **Static** — CLAUDE.md doesn't update as tethers change; manual maintenance
- **Context inefficient for dynamic data** — listing all tethers inline is wasteful; better to reference the CLI
- **No enforcement** — Claude might read it and choose not to act

#### What it's NOT good for
- Dynamic context that changes per-file (use hooks)
- First-class tool invocation (use skills)
- Blocking or preventing actions (use hooks)

#### Where to put it
- **Project CLAUDE.md** (`.claude/CLAUDE.md` or `./CLAUDE.md`): shared with team, checked in
- **Nested rules** (`.claude/rules/tether.md` or `.claude/rules/backend/tether.md`): scoped to file paths, loaded on demand
- **User CLAUDE.md** (`~/.claude/CLAUDE.md`): personal instructions for all projects

---

## Specific Questions Answered

### Q1: Can a hook inject tether context into the conversation when Claude is about to edit a tethered file?

**Yes, via PostToolUse on Edit/Write.**

Hook event: **`PostToolUse`** (fires after tool succeeds)  
Tool matcher: **`Edit|Write`**  
Return shape:
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "Related tethers:\n- src/foo.py specifies docs/spec.md\n- src/foo.py depends-on src/utils.py"
  }
}
```

**Caveats:**
- Fires *after* Claude writes, not before, so it's notification not prevention
- For prevention (to warn Claude before editing), use **`PreToolUse`**, but you get less data (no file content yet)
- Context is injected as user message, so it consumes tokens

**Alternative (pre-edit warning):** Use `PreToolUse` + `decision: "ask"` to force a permission dialog:
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "ask",
    "permissionDecisionReason": "This file is specified by docs/spec.md. Confirm you've checked the spec."
  }
}
```

---

### Q2: Can a hook block an Edit and tell Claude "update the tethered spec first"?

**Yes, via PreToolUse or PostToolUse with decision: "block".**

**PreToolUse approach (prevents the edit):**
```json
{
  "decision": "block",
  "reason": "docs/spec.md (tethered as 'specifies' this file) has uncommitted changes. Review and commit the spec first, or pass --force."
}
```

This shows a dialog; Claude can read the message and decide to edit the spec first.

**PostToolUse approach (after edit, prevent forward progress):**
```json
{
  "decision": "block",
  "reason": "You edited src/foo.py, but docs/spec.md specifies it. Consider updating the spec to match the new behavior."
}
```

This is softer (edit already done) but can encourage Claude to loop back.

**Practical limitation:** Hooks can block, but Claude's next move is unpredictable. For strict enforcement, combine with `UserPromptSubmit` hooks to catch risky patterns (e.g., if Claude tries to commit without updating tethered docs).

---

### Q3: For a distributed pip/uv package, where should recommended config live?

**Answer: A combination of approaches, depending on scope.**

| Scope | Location | Mechanism |
|-------|----------|-----------|
| **Single tethered project** | `./.claude/settings.json` | Project settings (checked in) |
| **All projects (user)** | `~/.claude/settings.json` + `~/.claude/CLAUDE.md` | User settings + memory |
| **Team distribution** | GitHub/marketplace plugin | Plugin with skills + hooks |

**Recommended approach for tether as a pip package:**

1. **Include a setup script** that generates `.claude/settings.json`:
   ```bash
   tether --init-claude-code
   ```
   This writes a hook entry on Edit/Write plus a permission allowlist for `Bash(tether *)`.

2. **Provide a recommended `.claude/CLAUDE.md`** snippet:
   ```markdown
   ## Tether Integration

   See `tether --help` for CLI reference. Tether is invoked through Bash; query relationships with `tether list --file <path> --json`.
   ```

3. **Optional: Publish a plugin** that includes:
   - Skills for tether reference
   - Hooks for PostToolUse context injection
   - `.claude/CLAUDE.md` fragment

**For a pip/uv package:**
- **Don't** require users to edit `.claude/` files manually
- **Do** provide a `--init-claude-code` or similar command that scaffolds config
- **Document** the setup in your README

---

## Integration Pattern Recommendations

### Pattern A: Lightweight (Hooks + CLAUDE.md)
**Best for:** projects where tether is a supporting tool, not central

- Add `PostToolUse` hook to inject tether context on Edit/Write
- Document tether CLI in CLAUDE.md
- No skills, no subagents

**Setup:**
```bash
tether init  # Create .tether/ and .claude/settings.json with hooks
```

**Result:** Claude naturally sees tether relationships as it edits, learns to run `tether list --file` from CLAUDE.md.

### Pattern B: Discoverable (Hooks + Skills + CLAUDE.md)
**Best for:** teams where tether is central, developers need to explore relationships

- Add PostToolUse hook to inject context
- Project-level skills (`.claude/skills/tether-*`) for reference and common workflows
- Document in CLAUDE.md

**Setup:**
```bash
tether init --with-skills
```

**Result:** Claude sees context on edit, can invoke `/tether-list` or `/tether-explore` for deep dives, has persistent reference material.

---

## Technical Deep Dives

### Hook JSON Schema Example

**Input (PostToolUse):**
```json
{
  "session_id": "sess_abc123",
  "transcript_path": "/tmp/transcript.jsonl",
  "cwd": "/home/user/myproject",
  "permission_mode": "default",
  "hook_event_name": "PostToolUse",
  "tool_name": "Edit",
  "tool_input": {
    "file_path": "/home/user/myproject/src/foo.py",
    "old_string": "def bar():\n  pass",
    "new_string": "def bar():\n  return 42"
  },
  "tool_response": {
    "filePath": "/home/user/myproject/src/foo.py",
    "success": true
  },
  "tool_use_id": "toolu_01ABC123xyz"
}
```

**Output (with tether context):**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "## Tethered Files\n\nThis file is affected by the following tethers:\n\n**Specifies:**\n- docs/api_spec.md (specifies this file)\n\n**Depends On:**\n- src/core.py (depends-on relationship)\n\n**Tests:**\n- tests/test_foo.py (tests this file)\n\nConsider reviewing related files before closing."
  }
}
```

### Hook Command Implementation

```bash
#!/bin/bash
# .claude/hooks/tether-context.sh

# Read hook input from stdin
input=$(cat)

# Extract tool name and file path
tool_name=$(echo "$input" | jq -r '.tool_name')
file_path=$(echo "$input" | jq -r '.tool_input.file_path')

# Only inject context for Edit/Write
if [[ "$tool_name" != "Edit" && "$tool_name" != "Write" ]]; then
  exit 0
fi

# Run tether list and format output
tethers=$(tether list --file "$file_path" --json 2>/dev/null)

if [[ -z "$tethers" ]]; then
  exit 0
fi

# Build context message
context=$(echo "$tethers" | jq -r '
  "## Tethers for " + (.file // "this file") + "\n" +
  "Relationships: " + (.tethers | length | tostring) + "\n" +
  (.tethers | map("- " + .source + " (" + .type + ") -> " + .target) | join("\n"))
')

# Return JSON output
jq -n \
  --arg context "$context" \
  '{
    "hookSpecificOutput": {
      "hookEventName": "PostToolUse",
      "additionalContext": $context
    }
  }'

exit 0
```

---

## Checklist for Implementation

### Phase 1: MVP (Hooks + CLAUDE.md)
- [ ] Define `PostToolUse` hook on Edit/Write
- [ ] Hook script calls `tether list --file <path> --json` and injects context
- [ ] Create `.claude/CLAUDE.md` documenting tether CLI
- [ ] Test: edit a file, verify tether context appears in conversation

### Phase 2: Enhanced (Add Skills)
- [ ] Create `.claude/skills/tether-reference/SKILL.md` (documentation)
- [ ] Create `.claude/skills/tether-explore/SKILL.md` (exploratory workflow)
- [ ] Test: invoke `/tether-reference` and `/tether-explore`

### Phase 3: Distribution
- [ ] Provide `tether --init-claude-code` command
- [ ] Publish plugin to marketplace (optional)
- [ ] Update README with setup instructions
- [ ] Document expected behavior in CLAUDE.md

---

## Summary Table

| Mechanism | Ambient Context | Tool Discovery | Deterministic | Complexity | Use for |
|-----------|-----------------|-----------------|---------------|-----------|---------|
| **Hooks** | Yes (PostToolUse) | No | Yes | Low | Context injection, warnings, blocking |
| **Skills** | No | Partial (in help) | Via Claude | Medium | Documented workflows, optional |
| **Subagents** | No | No | Via Claude | High | Complex exploration tasks |
| **CLAUDE.md** | Always | No (docs) | No (Claude-driven) | Low | Persistent reference, conventions |

---

## References

1. [Hooks Guide](https://code.claude.com/docs/en/hooks-guide.md) — Overview and common patterns
2. [Hooks Reference](https://code.claude.com/docs/en/hooks.md) — Complete event schemas and data
3. [Skills](https://code.claude.com/docs/en/skills.md) — Skill authoring, frontmatter, lifecycle
4. [Subagents](https://code.claude.com/docs/en/sub-agents.md) — Custom agent configuration
5. [Plugins](https://code.claude.com/docs/en/plugins.md) — Plugin structure and distribution
6. [Memory](https://code.claude.com/docs/en/memory.md) — CLAUDE.md files and auto memory
7. [Best Practices](https://code.claude.com/docs/en/best-practices) — Claude Code best practices, including the recommendation that [CLI tools are the most context-efficient way to interact with external services](https://code.claude.com/docs/en/best-practices#:~:text=CLI%20tools%20are%20the%20most%20context%2Defficient%20way%20to%20interact%20with%20external%20services)

