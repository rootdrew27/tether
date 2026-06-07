# Margin evals for tether

Evaluating tether's effect on Claude Code using
[Margin](https://github.com/Margin-Lab/evals). Each case runs in a Docker
container. The **treatment** arm installs tether and its Claude Code
integration into the case workspace before the agent starts; the **control**
arm runs stock Claude Code. Run output lands in `runs/<run-id>/` (gitignored).

## Layout

```
evals/margin/
  agent-definitions/
    claude-code-tether/    Margin's claude-code definition + tether install
    claude-code-stock/     committed snapshot of stock claude-code (control)
  agent-configs/
    tether-sonnet/         treatment arm  → claude-code-tether
    baseline-sonnet/       control arm    → claude-code-stock
  eval-configs/
    smoke.toml             3-case swe-minimal, the plumbing check
  scripts/
    run-smoke.sh           build a pinned wheel + run the treatment arm
    verify-smoke.py        assert install/init/hooks + summarize a run
  runs/                    margin run output (gitignored)
```

## Running

Treatment arm (builds a fresh wheel from `HEAD`, then runs and verifies):

```bash
evals/margin/scripts/run-smoke.sh --non-interactive --exit-on-complete
evals/margin/scripts/verify-smoke.py evals/margin/runs/<run-id>
```

Build from a specific commit/branch/tag instead of `HEAD`:

```bash
evals/margin/scripts/run-smoke.sh <ref> --non-interactive --exit-on-complete
```

Control arm (no tether; run directly, no wheel needed):

```bash
margin run \
  --suite "git::https://github.com/Margin-Lab/test-suites.git//swe-minimal-test-suite" \
  --agent-config evals/margin/agent-configs/baseline-sonnet \
  --eval evals/margin/eval-configs/smoke.toml \
  --non-interactive --exit-on-complete
```

## Reproducibility

A result is comparable to another only if every behavior-affecting input is
pinned (forced to a version) or recorded (captured for attribution):

| Input | Status |
| --- | --- |
| **tether** | Pinned to a commit (built from `git archive`, wheel stamped `0.1.0+g<sha7>`); recorded in `<run-dir>/tether-build.json`. |
| **Model** | Pinned: `claude-sonnet-4-6` (both arms). |
| **Claude Code** | Pinned: `2.1.167` (both arms). |
| **Baseline harness** | Pinned: control arm uses the committed `claude-code-stock` definition. |
| **Suite** | Recorded, not pinned: margin records the resolved commit in `internal/bundle.json`. |
| **uv + Python** | Not pinned (tether arm only); low impact. |

---

Working on this harness (editing the agent definitions, the install hook, or
the verifier)? See `CLAUDE.md` for the install path, pinning rules, and
verifier internals.
