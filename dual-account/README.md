# Dual-account split (dual-account)

The main account is used in the Claude app (or CLI) only for planning, judgment, and synthesizing results; token-heavy execution runs headless on a second account's CLI. Only the instructions and the final report stay in the main session.

```
Main (app, account A) ── instructions ──▶ alt-agent ──▶ second CLI (account B, ~/.claude-alt)
        ▲                                                │ build · test · research
        └────────────── final report + session ID ◀─────┘
```

## Contents

| File | Role |
|---|---|
| [`setup.sh`](setup.sh) | Creates the `~/.claude-alt` profile, symlinks shared items, installs `alt-agent`, adds `claude2` to your shell |
| [`bin/alt-agent`](bin/alt-agent) | Runs `claude -p --agent <role>` on the second account and prints only the result |

Shared: `CLAUDE.md`, `settings.json`, `agents/`, `skills/`, `commands/`, `plugins/`, `projects/` (sessions · memory), input history. Not shared: login (`.claude.json`; keychain entries are stored per config folder) and session runtime state. User-scope MCP server settings are copied once.

## Install

```bash
bash dual-account/setup.sh --dry-run
bash dual-account/setup.sh
```

In a new shell, run `claude2` and `/login` with the second account. Check each profile's login with `claude auth status` and `CLAUDE_CONFIG_DIR=~/.claude-alt claude auth status`.

## Usage

`cd` into the working repo first. From the main session, run it in the background with the Bash tool and only the result comes back when it finishes.

```bash
alt-agent -t normal ai-builder <<'EOF'
Write a self-contained brief: goal, target files, done criteria, report format.
EOF
```

### Model tiers

The main session already does the planning and heavy reasoning, so execution leans on Sonnet 5.5. Pick a tier with `-t`; `-m`/`-e` override it.

| Tier | Model · effort | Use for |
|---|---|---|
| `simple` | Sonnet 5.5 · medium | run/inspect, build/test, logs, mechanical edits |
| `normal` (default) | Sonnet 5.5 · high | regular implementation, fixes, debugging |
| `hard` | Opus 5.5 · low | cross-module refactors, subtle/concurrency/security bugs, retry after a failed Sonnet run |
| `harder` | Opus 5.5 · medium | code work that `hard` is not enough for |
| `auto` | one of the above | when the choice is unclear: Jev (TypeSafe's decision model) answers two yes/no questions about the brief (needs Opus? needs extended reasoning?) and picks the tier; falls back to `normal` on any error |

`auto` needs a Jev helper that accepts `call` with `{"state", "questions"}` JSON on stdin; point `JEV_PY` at it. Without it, `auto` behaves like `normal`.

- Full records are kept in `~/.claude-alt/runs/`. See the details with `claude2 --resume <session ID>`.
- Exit code 2 means the second account is not logged in, hit a usage limit, or the run failed. The main agent hands the same instructions to a default subagent.
- Headless runs cannot ask for permission, so they run with `--dangerously-skip-permissions`. Use only in repos you trust, and run in a worktree if needed.
- Second-account runs disable hooks and load no MCP servers, so gate/notification hooks on the main account do not run twice.

## Paragraph for the main instructions

Add this to `~/.claude/CLAUDE.md` so the main session knows the delegation path.

```markdown
## Second-account delegation (save main-account tokens)

Use the main account only for planning, judgment, and synthesizing results; send token-heavy work to the second account.

- Multi-file builds, tests, debugging, long research → Bash: `~/.claude/bin/alt-agent -t <tier> ai-builder <<'EOF' … EOF`
  (cd into the working repo, run in the background). Simple runs → `ai-runner`.
- Prefer Sonnet: `simple` (Sonnet medium) for runs/lookups/mechanical edits, `normal` (Sonnet high, default) for regular
  implementation; `hard` (Opus low) / `harder` (Opus medium) only for genuinely hard code or after a failed Sonnet run.
  If the choice is unclear, use `auto`.
- The instructions share no context, so write goal, target files, done criteria, and report format self-contained.
- Small edits to 1–2 files or simple lookups cost more to delegate; the main agent does them directly.
- On exit code 2, delegate the same instructions to a default subagent and mention it in one line.
- Do not run two alt-agents that touch the same file at the same time.
```

## Caveats

- Run `scripts/install.py --user` in a normal shell with `CLAUDE_CONFIG_DIR` unset. `agents/` in `~/.claude-alt` is a symlink and fails the install path check; anything installed into `~/.claude` is visible to the second account anyway.
- Shared items in `~/.claude-alt` are symlinks into your real `~/.claude`, so any tool a second-account run uses that writes to its config dir (installers, uninstallers) changes your real setup. `alt-agent` tells every run this and to unset `CLAUDE_CONFIG_DIR` for temp-home test installs; keep that rule in your briefs too.
- Do not continue the same session from both accounts at once. Concurrent writes to the same record file can corrupt it.
- Mixing a company account and a personal account means company code is processed under another account. Check your organization's policy first.
- If you are adding accounts to get around usage limits, check the terms of service.
- Token savings have not been measured yet.
