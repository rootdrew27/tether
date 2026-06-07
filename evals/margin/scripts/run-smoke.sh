#!/usr/bin/env bash
# Build a tether wheel from a committed ref and run the swe-minimal smoke
# eval with the claude-code-tether agent definition.
#
# Usage: run-smoke.sh [ref] [margin-run flags...]
#
# The wheel is built from `git archive <ref>` (default HEAD) — uncommitted
# changes are never included. The build is stamped with the source commit as
# a PEP 440 local version (0.1.0+g<sha7>), so the commit appears in each
# instance's setup marker and in pip metadata inside the container. After the
# run, the build is recorded in <run-dir>/tether-build.json.
set -euo pipefail

repo_root="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
margin_dir="$repo_root/evals/margin"

# First argument is a committish if it resolves; everything else passes
# through to `margin run`.
ref="HEAD"
if [[ $# -gt 0 && "$1" != -* ]] && git -C "$repo_root" rev-parse --verify --quiet "$1^{commit}" >/dev/null; then
  ref="$1"
  shift
fi
sha="$(git -C "$repo_root" rev-parse "$ref^{commit}")"
sha7="${sha:0:7}"
branch="$(git -C "$repo_root" rev-parse --symbolic-full-name "$ref" 2>/dev/null | sed 's|^refs/heads/||' || true)"

if [[ -n "$(git -C "$repo_root" status --porcelain -- tether pyproject.toml)" ]]; then
  echo "note: tether/ or pyproject.toml has uncommitted changes; building from $ref ($sha7) — uncommitted edits are NOT included" >&2
fi

# Build the wheel from the committed tree of $sha, stamped with the commit.
build_dir="$(mktemp -d)"
trap 'rm -rf "$build_dir"' EXIT
git -C "$repo_root" archive "$sha" | tar -x -C "$build_dir"
sed -E -i "s/^(version = \"[^\"]+)(\")/\1+g$sha7\2/" "$build_dir/pyproject.toml"
(cd "$build_dir" && uv build --wheel)

# Stage exactly one wheel: the in-container install globs tether-*.whl.
rm -rf "$repo_root/dist"
mkdir -p "$repo_root/dist"
cp "$build_dir"/dist/tether-*.whl "$repo_root/dist/"
wheel="$(basename "$repo_root"/dist/tether-*.whl)"
echo "built $wheel from $ref ($sha)" >&2

# Run from the margin dir so output lands in evals/margin/runs/<run-id>/.
cd "$margin_dir"
mkdir -p runs
pre_runs="$(ls -d runs/run_* 2>/dev/null | sort || true)"

status=0
margin run \
  --suite "git::https://github.com/Margin-Lab/test-suites.git//swe-minimal-test-suite" \
  --agent-config "$margin_dir/agent-configs/tether-sonnet" \
  --eval "$margin_dir/eval-configs/smoke.toml" \
  --agent-bind "$repo_root/dist=/opt/tether-dist" \
  "$@" || status=$?

# Record the tether build in the run directory created by this invocation.
post_runs="$(ls -d runs/run_* 2>/dev/null | sort || true)"
run_dir="$(comm -13 <(printf '%s\n' "$pre_runs") <(printf '%s\n' "$post_runs") | tail -1)"
if [[ -n "$run_dir" && -d "$run_dir" ]]; then
  python3 - "$run_dir/tether-build.json" "$ref" "$sha" "$branch" "$wheel" <<'EOF'
import datetime
import json
import sys

path, ref, sha, branch, wheel = sys.argv[1:6]
record = {
    "ref": ref,
    "commit": sha,
    "branch": branch or None,
    "wheel": wheel,
    "built_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
}
with open(path, "w") as f:
    json.dump(record, f, indent=2)
    f.write("\n")
EOF
  echo "recorded tether build ($sha7) in $run_dir/tether-build.json" >&2
fi
exit "$status"
