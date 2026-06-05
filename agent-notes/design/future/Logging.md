> [!NOTE]
> **Proposed design — not implemented.** Tether has no logging subsystem today; the only log it touches is `git log`. This document specifies a hook-activity log and a `tether log` reader for if/when hook observability becomes a real need — the deferred-feature framing lives in [Claude-Code-Integration-Open](../../claude-code/Claude-Code-Integration-Open.md) under "Observability — `tether.log` for hook activity". Everything below describes the intended design, not current behavior.

Tether's logging would make the silent surfaces of the system legible — the work that happens during hook fires, which git history alone cannot see. CLI mutations are not in scope: every state-changing CLI command updates a tether record, and the audit trail is `git log .tether/tethers/<id>.json` (see [Git Integration](../../../tether-vault/DICTION.md#git-integration)).

## Hook trace

The hook trace would live at `.tether/hooks.log` and capture every fire of every Claude Code hook tether installs.

### File and format

- Newline-delimited JSON, one record per hook invocation, append-only.
- Gitignored via `.tether/.gitignore` (which `tether init` would write — it does not today).
- Rotates at 10 MiB: the current file becomes `hooks.log.1` and a fresh `hooks.log` is opened. One rotation generation is retained; older content is dropped.

### Per-record fields

| Field | Type | Description |
| --- | --- | --- |
| `ts` | ISO 8601 UTC | Event start. |
| `event` | string | `hook.session_start`, `hook.stop`, or `hook.pre_tool_use`. |
| `cwd` | string | The cwd reported on hook stdin. |
| `matched` | list[string] | UUIDs of tethers the fire touched. Empty when nothing matched. |
| `aggregate` | object | State counts (`healthy`, `drifted`, `broken`) at fire time. Present for `session_start` and `stop` only. |
| `file_path` | string | Project-relative POSIX path the hook reacted to. `pre_tool_use` only. |
| `tool_name` | string | Claude Code tool name (`Read`, etc.). `pre_tool_use` only. |
| `blocked` | bool | Whether `stop` returned a block decision. `stop` only. |
| `output` | string | The exact bytes emitted on stdout — the markdown, XML, or JSON the harness saw. Empty when nothing was emitted. Capped at 8 KiB; longer values are truncated. |
| `output_truncated` | bool | True when `output` was clipped by the 8 KiB cap. |
| `elapsed_ms` | int | Wall-clock duration of the hook handler. |
| `exit_code` | int | Process exit code returned to Claude Code. |

`output` carries the full payload, so the log doubles as a transcript of *what tether handed Claude* — there is no separate file for that.

## Reading: `tether log`

`tether log` would be the user-facing reader. The pretty form prints one line per record: `<ts> <event> matched=<n> elapsed=<ms>ms [flags]`, where flags include `blocked`, `trunc`, and `err` (non-zero `exit_code`).

| Invocation | Behaviour |
| --- | --- |
| `tether log` | Last 20 records, newest last. |
| `tether log -n <N>` | Last `N` records. |
| `tether log --since <duration>` | Records with `ts >= now − duration`. Duration accepts `5m`, `2h`, `1d`. |
| `tether log --event <name>` | Filter by `event` field. Repeatable. |
| `tether log -f` | Follow new appends (`tail -f` shape). |
| `tether log --json` | Emit raw NDJSON instead of the pretty form. |

The full `output` field is reachable via `--json`; the pretty form summarises.

## Out of scope

- **CLI invocations.** `tether add`, `tether refresh`, `tether update`, `tether mv`, `tether rm`, and `tether status` do not write log records. Mutations are captured by git on the tether record; reads are user-initiated and visible in shell history.
- **CLI surface.** The log does not replace `tether status`, `tether refs`, or `tether refresh`. The log answers *what tether did*; the CLI answers *what tether knows*.
