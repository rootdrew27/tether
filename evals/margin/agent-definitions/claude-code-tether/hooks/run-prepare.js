#!/usr/bin/env node
const fs = require("node:fs");
const path = require("node:path");

function shellQuote(value) {
  const text = String(value);
  if (text.length === 0) {
    return "''";
  }
  if (/^[A-Za-z0-9_@%+=:,./-]+$/.test(text)) {
    return text;
  }
  return `'${text.replace(/'/g, `'\"'\"'`)}'`;
}

function ensureSkipDangerousModePermissionPrompt(settingsPath) {
  let settings = {};
  if (fs.existsSync(settingsPath)) {
    settings = JSON.parse(fs.readFileSync(settingsPath, "utf8"));
  }
  settings.skipDangerousModePermissionPrompt = true;
  fs.writeFileSync(settingsPath, JSON.stringify(settings, null, 2) + "\n", "utf8");
}

const ctx = JSON.parse(fs.readFileSync(process.env.AGENT_CONTEXT_JSON, "utf8"));
const run = ctx.run;
const cfg = ctx.config.input;
const paths = ctx.paths;
const install = ctx.install || {};
const runHome = paths.run_home;
const claudeDir = path.join(runHome, ".claude");
const stderrPath = path.join(paths.artifacts_dir, "claude.stderr.log");
fs.mkdirSync(claudeDir, { recursive: true });
const binPath = install.bin_path || path.join(paths.install_dir, "bin", "claude");

const settingsPath = path.join(claudeDir, "settings.json");
fs.writeFileSync(settingsPath, cfg.settings_json, "utf8");
ensureSkipDangerousModePermissionPrompt(settingsPath);

const env = { ...run.env, DISABLE_AUTOUPDATER: "1", CLAUDE_CONFIG_DIR: claudeDir };
const apiKey = String(env.ANTHROPIC_API_KEY || "").trim();
const claudeState = {};
const mcpJSON = String(cfg.mcp_json || "").trim();
if (mcpJSON) {
  Object.assign(claudeState, JSON.parse(mcpJSON));
}
claudeState.hasCompletedOnboarding = true;
// Pre-trust the case workspace so project-level settings (tether's hooks in
// .claude/settings.local.json) load without an interactive trust dialog.
claudeState.projects = {
  [run.cwd]: {
    hasTrustDialogAccepted: true,
    hasCompletedProjectOnboarding: true,
  },
};
if (apiKey) {
  claudeState.customApiKeyResponses = { approved: [apiKey.slice(-20)], rejected: [] };
}
fs.writeFileSync(path.join(claudeDir, ".claude.json"), JSON.stringify(claudeState, null, 2) + "\n", "utf8");

const command = [
  shellQuote(binPath),
  "--dangerously-skip-permissions",
  "--verbose",
  "--output-format=stream-json",
  "--session-id",
  shellQuote(run.session_id),
  ...(cfg.startup_args || []).map(shellQuote),
  ...(cfg.run_args || []).map(shellQuote),
  "-p",
  shellQuote(run.initial_prompt),
].join(" ");

// Tether setup, run before the agent launches: install the bind-mounted wheel
// into an isolated Python 3.12 venv (the testbed env must stay untouched),
// expose the CLI on PATH, then initialize tether and its Claude Code
// integration in the case workspace. All output goes to stderr so stdout
// stays a clean stream-json channel; markers land in agent_server_pty.log.
const wheelDir = "/opt/tether-dist"; // bind-mount target; matches run-smoke.sh --agent-bind
const tetherVenv = "/opt/tether-venv";
const tetherSetup = [
  "{",
  `echo "tether-setup: begin (wheel dir: ${wheelDir})"`,
  "if ! command -v uv >/dev/null 2>&1; then",
  "  curl -LsSf https://astral.sh/uv/install.sh | sh",
  '  export PATH="$HOME/.local/bin:$PATH"',
  "fi",
  `uv venv --seed --python 3.12 ${tetherVenv}`,
  `${tetherVenv}/bin/pip install --quiet ${wheelDir}/tether-*.whl`,
  `ln -sf ${tetherVenv}/bin/tether /usr/local/bin/tether`,
  `echo "tether-setup: installed $(${tetherVenv}/bin/pip show tether | sed -n 's/^Version: /tether /p') via pip"`,
  `cd ${shellQuote(run.cwd)}`,
  "tether init",
  "tether init claude-code",
  'test -d .tether/tethers && echo "tether-setup: project initialized (.tether/tethers present)"',
  'test -f .claude/settings.local.json && echo "tether-setup: claude-code integration installed (.claude/settings.local.json present)"',
  'echo "tether-setup: done"',
  "} >&2",
].join("\n");

const shellCommand = [
  "set -euo pipefail",
  tetherSetup,
  `mkdir -p ${shellQuote(path.dirname(stderrPath))}`,
  `${command} 2> >(tee ${shellQuote(stderrPath)} >&2)`,
].join("\n");

process.stdout.write(JSON.stringify({
  path: "bash",
  args: ["-c", shellCommand],
  env,
  dir: run.cwd,
}) + "\n");
