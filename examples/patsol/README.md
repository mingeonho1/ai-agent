# patsol — a real company setup, kept as an example

> 한국어: 실제 회사에서 쓰는 Claude Code 커스터마이징을 예제로 공개한 것입니다. 회사별 값은 설치 시 질문으로 채웁니다.

This is the Claude Code setup one team (**PatSol**) actually uses for day-to-day work, kept
here as a worked example of *how one team customized Claude Code with skills, routines and
automations*. Nothing company-specific is hardcoded: every environment-specific value (Jira
site, repo names, Slack/Notion IDs, emails, people) is a `{{variable}}` placeholder, and
[`../render.py`](../render.py) asks for them and fills them in. **Secrets (tokens, webhooks)
never go into files** — they are referenced only through environment variables or an
external `.env`.

> It works standalone — no other tooling is required. (For the separate desktop
> mission-control kit, see [claudi](https://github.com/mingeonho1/claudi).)

## What's inside

### Skills (`claude/skills/`)

| Skill | What it does | Trigger | Required connectors / environment |
|-------|--------------|---------|-----------------------------------|
| `autofix-pr` | Fetch a PR locally, run a fresh Claude review → classify by severity (high/mid/low) → per-item apply/skip/defer → single commit + line-comment replies | `/autofix-pr <PR number>` | `gh` CLI. (optional) Jev |
| `challenge-pr` | 3–5 questions that challenge a PR's **design decisions** head-on, Toss senior style. Read-only, questions only | `/challenge-pr <PR>` | `gh` CLI, `toss-senior-challenger` agent |
| `review-feedback` | Check existing bot reviews (Gemini/CodeRabbit/GH Action, etc.) against the real code → apply/skip → reply in the original thread | `/review-feedback <PR>` | `gh` CLI. (optional) Jev |
| `decide-approach` | Weigh the **choice of approach** for a task on performance/cost/security/maintainability and commit to one (proposal only) | "which approach", `/decide-approach` | — |
| `impact-check` | Read-only impact briefing before writing code — what changes and how far the blast radius reaches | `/impact-check <task>` | (optional) Jev |
| `fix-bug` | Bug-fix pipeline (reproduce → impact/decide in parallel → validate → minimal fix → e2e → commit·PR) | `/fix-bug <ticket/symptom>` | `gh` CLI, git. (optional) Jev |
| `jira-sync` | Sync my Jira tickets' status to how far they reached the deploy pipeline (develop→DEV 배포완료, staging→QA, main→완료). Auto-detects sibling `<REPO_PREFIX>-*` repos, advance-only | `/jira-sync [assignee]` | Atlassian (Jira) MCP, git |
| `sentry-triage` | End-to-end triage of a Sentry production error → if clear, hand to `fix-bug` and open a PR; if ambiguous, Slack report + on-call mention | `/sentry-triage <url>` | Sentry MCP, Slack Webhook (env) |
| `jev-scope` | Rank task-relevant files by probability with the Jev (TypeSafe "System One") API. General-purpose noul/choice/score helper (`jev.py`) used by other skills | `/jev-scope <task>` | `TYPESAFE_API_KEY` (env or `~/.config/jev/api_key`) |
| `work-journal` | Per-Jira-ticket work journal — auto-collects sessions·commits·Jira + asks only for values only a human knows → records to Notion | "업무 정리" / "work journal", `/work-journal` | Notion MCP, Atlassian MCP, WandSol MCP, `worklog/` scripts |
| `orchestrate-workers` | Dispatch and coordinate worker agents (codex·claude, etc.) in isolated worktrees via the orchterm orchestration MCP | "워크트리 멀티에이전트로" (Korean trigger phrase) | orchterm MCP |
| `anti-ai-writing` | Final filter that catches text that "sounds like AI" (copy, newsletters, threads, etc.) | when writing/editing | — |

### Commands (`claude/commands/`)

| Command | What it does | Required environment |
|---------|--------------|----------------------|
| `/new-task` | New task setup pipeline — clarify → generate content → Jev repo routing → deterministic script creates Jira ticket + Notion page + git branch → plan → implement → (conditional) PR·review | `scripts/new-task.py` (+`requests`), `AGENT_RULES_ENV` `.env` |
| `/apply-review` | Apply the review results in the conversation to the current branch with minimal changes + record them on the Notion page | `AGENT_RULES_ENV` `.env` (`NOTION_API_TOKEN`) |

### Agents (`claude/agents/`)

- `toss-senior-challenger` — Toss-style senior persona that challenges PR design decisions (called by `challenge-pr`).

### Hooks (`settings.fragment.json` → merged into `settings.json`)

- `worklog/bin/wandsol_track_hook.py` (`UserPromptSubmit`) — once, on a session's first prompt,
  injects classification guidance on how to use WandSol time tracking (start right away if the
  ticket is clear, ask once if ambiguous). Not injected into scheduled/subagent sessions, and
  never blocks the prompt under any circumstances.

### Work-journal / automation scripts (`claude/worklog/`)

- `bin/collect.py` — auto-collects sessions·commits·tickets (standard library).
- `bin/aggregate.py` — computes running totals·dashboard·figure tables.
- `config.json` — Notion DB/Jira settings **template** (variables filled at render). Deep IDs
  can be left empty and filled in later.

### Scheduled task templates (`routines/` → `<out>/example-profiles/patsol/routines/`)

`render.py` does not register these — you upload them yourself to Claude's Scheduled Task feature.

| Routine | Schedule (recommended) | What it does |
|---------|------------------------|--------------|
| `slack-digest` | Hourly on weekdays | Picks the top 10 "Slack items I need to see now" by importance and saves them (run by a Sonnet subagent to keep the main session cheap). Slack is read-only |
| `work-journal-daily` | Weekdays 09:30 | Auto-summarizes the previous weekday's work + backfills gaps + refreshes the dashboard + today's plan |
| `examples/announce-only-reminder` | Example | Pattern for an announce-only reminder at a specific time (notice only, no lookups or changes) |
| `examples/self-gating-promotion-check` | Example | Pattern that gates its own observation period and only decides promote/no-promote from read-only metrics |
| `examples/one-shot-slack-followup` | Example | Pattern that first checks whether it was already handled, and if not, sends a single Slack reminder |

> `slack-digest` saves its results to `example-profiles/patsol/slack-items.json`; show them in any dashboard or status bar you like.

### Helper scripts (`scripts/` → `<out>/example-profiles/patsol/scripts/`)

- `new-task.py` — creates the Jira ticket·Notion page·git branch from cached IDs (deterministic). Requires `requests`.
- `discover.py` — looks up Jira/Notion stable IDs (sprint·team field·accountId·issue type, etc.) in one go and
  prints them. Use it to fill `task-config.json` / `answers.json`. Requires `requests`.
- `task-config.json` — bundle of stable IDs read by new-task (template). Some are Jira-Cloud defaults;
  if they fail, replace them with your instance's values via `discover.py`.

## The customization story (which patterns went in)

- **A triple PR quality gate**: `autofix-pr` for an opened PR (fresh review → apply),
  `review-feedback` for existing bot reviews (verify → apply), `challenge-pr` when the design looks
  suspicious (challenge why it was done this way). Roles are split so they don't overlap.
- **Incidents/bugs: "stop when ambiguous"**: `sentry-triage` hands off to `fix-bug` through to a PR only
  when clear; if even slightly ambiguous, zero lines of code + a Slack report. `impact-check` (blast radius)
  and `decide-approach` (approach choice) sit up front to force "think before fixing."
- **Ticket lifecycle automation**: `/new-task` (create) → work → `jira-sync` (match status to how far the
  branch reached) → `work-journal` (asks only for what a human knows, collects the rest automatically).
  The key is leaving unknowable values like real ticket numbers and human time empty and filling in only
  automatic facts.
- **Quiet time tracking**: `wandsol_track_hook` prompts only once per session with "This has a ticket —
  turn on tracking?". It never blocks; if ambiguous, it asks once and is done.
- **Jev (TypeSafe) cross-checks plugged into several skills**: file scope (`scope`), completeness (`noul`),
  and choice (`choice`) are used only as auxiliary signals; Claude's own judgment always comes first.

## How values are asked and rendered

- `profile.json` declares every variable: its question (`question`, plus an optional
  Korean `question_ko`), an example, a default, and whether it is required.
- `render.py` resolves each answer in this order: `--answers` file → interactive prompt →
  previously saved `answers.json` → default. A missing required answer, or any `{{...}}` left
  unrendered, **fails the run and writes nothing**.
- Existing files that would change are backed up to `<name>.bak-<timestamp>` first. Hooks are
  merged into `settings.json` idempotently (re-running adds no duplicates). Non-secret answers
  are saved to `<out>/example-profiles/patsol/answers.json` so a re-run reuses them.

## Install (standalone)

```bash
# 1) Preview the questions
python3 examples/render.py patsol --list-questions

# 2a) Render into ~/.claude (or $CLAUDE_CONFIG_DIR), answering interactively
python3 examples/render.py patsol

# 2b) ...or non-interactively from an answers file
python3 examples/render.py patsol --answers my-answers.json --yes

# 2c) ...or into a project: render elsewhere, then copy what you want
python3 examples/render.py patsol --out /tmp/patsol-out --answers my-answers.json --yes
cp -R /tmp/patsol-out/skills/. <project>/.claude/skills/
cp -R /tmp/patsol-out/commands/. <project>/.claude/commands/
cp -R /tmp/patsol-out/agents/. <project>/.claude/agents/

# Dry run (writes nothing)
python3 examples/render.py patsol --out /tmp/try --answers my-answers.json --dry-run
```

Only five values are required — `USER_DISPLAY_NAME`, `GIT_AUTHOR`, `USER_EMAIL`,
`JIRA_SITE`, `JIRA_PROJECT_KEY`. The rest (repo names/paths, Slack/Notion/Jira deep IDs,
Sentry org, etc.) have defaults or can be left empty and filled in when you turn on that feature.
See [`profile.json`](./profile.json) for every variable and question (or `--list-questions`).

Tests: `python3 -m unittest discover -s examples/tests`.

After installing:

1. **Create the secrets `.env`** — `/new-task`, `/apply-review`, and `discover.py` read tokens from the
   `.env` that `AGENT_RULES_ENV` points to (default `~/.config/patsol/patsol.env`). Fill it with the
   names below (use your own values):
   ```sh
   export JIRA_BASE_URL=https://<your>.atlassian.net
   export JIRA_EMAIL=you@yourco.com
   export JIRA_API_TOKEN=...        # secret
   export NOTION_API_TOKEN=...      # secret
   export NOTION_PLAN_DB_ID=...     # DB where new-task creates pages
   ```
2. **Jev key** (optional) — `export TYPESAFE_API_KEY=...` or `~/.config/jev/api_key` (`chmod 600`).
3. **Sentry triage** (optional) — `SENTRY_TRIAGE_SLACK_WEBHOOK` (Slack Incoming Webhook for reports),
   `SENTRY_TRIAGE_ONCALL` (on-call mention id). For automation (CI) plumbing see `skills/sentry-triage/automation/`.
4. **Work-journal deep IDs** — if you need Notion DB/data-source IDs and Jira cloud_id/account_id,
   look them up with `discover.py` and re-render (answers are reused), or fill `worklog/config.json` directly.
5. **Register scheduled tasks** — upload the SKILL.md files in `example-profiles/patsol/routines/` to
   Claude's Scheduled Task feature yourself (recommended schedules in the table above).
6. **The time-tracking hook** is merged idempotently into `settings.json` by `render.py` (re-running adds no duplicates).

Prerequisite connectors: Atlassian (Jira) MCP, Notion MCP, Sentry MCP, Slack MCP, and WandSol MCP must
each be enabled for the corresponding skills to work (without one, only that skill stops working).

## Environment dependencies / scope

- Written on macOS (the example notification commands use `osascript`); the skill logic itself is OS-agnostic.
- `new-task.py` and `discover.py` require `requests` (the other scripts and `render.py` use the standard library only).
- The branch conventions (`develop`/`staging`/`main`, `f-`/`h-`) and the "PatSol"·"WandSol" names were kept as-is.
  For another team to use it, change `JIRA_PROJECT_KEY`·`REPO_PREFIX`·branch names, etc. to your team's own.
- Some scripts optionally read a language hint (`CLAUDI_LANG`) and an optional enforce/sessionkind helper;
  without them they default to English and keep working.
