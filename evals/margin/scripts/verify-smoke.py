#!/usr/bin/env python3
"""Verify a tether smoke run produced by run-smoke.sh.

Usage: verify-smoke.py <run-dir>

Checks, per instance:
  1. tether installed via pip (setup marker in agent_server_pty.log)
  2. tether initialized in the case workspace (setup marker)
  3. Claude Code integration installed (setup marker)
  4. tether hooks fired during the session (structured hook_started /
     hook_response events in the --verbose stream-json output)
and summarizes results.json. Exits non-zero if any setup marker is missing,
any instance infra-failed, or any fired hook reported a non-success outcome.

Only the SessionStart hook is required to have fired: Claude Code 2.1.x
emits stream-json hook events for SessionStart only. PreToolUse and Stop
hooks run but leave no trace in the stream or the session transcript when
their output is empty (always the case on an empty tether graph) — verified
empirically with marker-file hooks under the same headless configuration.
They are reported when present (seeded graphs / future Claude Code versions).
"""

import json
import re
import sys
from pathlib import Path

# Wheel versions are stamped 0.1.0+g<sha7> by run-smoke.sh; the marker line
# carries the version, so each instance records the tether commit it ran.
VERSION_RE = re.compile(r"tether-setup: installed (tether \S+) via pip")

SETUP_MARKERS = {
    "installed via pip": "tether-setup: installed tether",
    "project initialized": "tether-setup: project initialized",
    "integration installed": "tether-setup: claude-code integration installed",
    "setup completed": "tether-setup: done",
}


# tether registers SessionStart, Stop, and PreToolUse hooks in
# .claude/settings.local.json. Claude Code's stream-json (with --verbose) emits
# {"type": "system", "subtype": "hook_started"/"hook_response",
# "hook_event": <event>, ...} for each firing.
def hook_responses(log_text: str) -> dict[str, list[dict]]:
    """Collect hook_response events from a pty log, grouped by hook event."""
    by_event: dict[str, list[dict]] = {}
    for line in log_text.splitlines():
        if '"hook_response"' not in line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("type") == "system" and record.get("subtype") == "hook_response":
            by_event.setdefault(record.get("hook_event", "?"), []).append(record)
    return by_event


def main() -> int:
    if len(sys.argv) != 2:
        print((__doc__ or "").strip(), file=sys.stderr)
        return 2
    run_dir = Path(sys.argv[1])
    results_path = run_dir / "results.json"
    if not results_path.is_file():
        print(f"error: {results_path} not found", file=sys.stderr)
        return 2
    results = json.loads(results_path.read_text())

    build_path = run_dir / "tether-build.json"
    build = json.loads(build_path.read_text()) if build_path.is_file() else None
    if build:
        print(
            f"tether build: {build.get('commit', '?')[:7]}"
            f" (ref {build.get('ref', '?')}, branch {build.get('branch')},"
            f" wheel {build.get('wheel', '?')})"
        )
    else:
        print("tether build: no tether-build.json in run dir (pre-stamping run?)")

    failures = 0
    for inst_dir in sorted((run_dir / "instances").iterdir()):
        result = json.loads((inst_dir / "result.json").read_text())
        pty_log = inst_dir / "run" / "agent_server_pty.log"
        log_text = pty_log.read_text(errors="replace") if pty_log.is_file() else ""

        print(f"\n{inst_dir.name}  [{result.get('instance_key', '?')}]")
        print(f"  final_state: {result.get('final_state', '?')}")
        if result.get("final_state") == "infra_failed":
            failures += 1

        for label, marker in SETUP_MARKERS.items():
            ok = marker in log_text
            print(f"  setup / {label}: {'OK' if ok else 'MISSING'}")
            if not ok:
                failures += 1

        version_match = VERSION_RE.search(log_text)
        if version_match:
            version = version_match.group(1)
            if build:
                expected = f"+g{build.get('commit', '')[:7]}"
                consistent = expected in version
                print(
                    f"  tether version: {version}{'' if consistent else f' MISMATCH (expected {expected})'}"
                )
                if not consistent:
                    failures += 1
            else:
                print(f"  tether version: {version}")

        # Report every hook event that surfaced in the stream, validating its
        # outcome. On an empty graph only SessionStart appears (Stop/PreToolUse
        # run silently — see module docstring), so a clean run shows one line.
        responses = hook_responses(log_text)
        for event, fired in sorted(responses.items()):
            bad = [r for r in fired if r.get("outcome") != "success"]
            suffix = f", {len(bad)} NON-SUCCESS" if bad else ", all success"
            print(f"  hook / {event}: fired x{len(fired)}{suffix}")
            if bad:
                failures += 1
        if not responses.get("SessionStart"):
            print("  hook / SessionStart: NOT OBSERVED")
            failures += 1

    status = results.get("status", {})
    usage = results.get("usage", {})
    print(f"\nrun: {results.get('run_id')}  state: {results.get('state')}")
    print(
        f"  succeeded {status.get('succeeded', {}).get('count', '?')}"
        f" / test_failed {status.get('test_failed', {}).get('count', '?')}"
        f" / infra_failed {status.get('infra_failed', {}).get('count', '?')}"
        f"   tokens in/out: {usage.get('input_tokens', '?')}/{usage.get('output_tokens', '?')}"
        f"   tool calls: {usage.get('tool_calls', '?')}"
    )

    if failures:
        print(f"\nFAIL: {failures} check(s) failed")
        return 1
    print("\nPASS: all required checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
