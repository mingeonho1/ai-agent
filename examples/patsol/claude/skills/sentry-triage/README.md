# sentry-triage

A triage skill that takes a Sentry production error through **trace → clear/ambiguous verdict → branch**.
Rather than fixing directly, it hands clear cases to `fix-bug` all the way to a PR, and reports/assigns anything even slightly ambiguous via Slack.

## Usage

```
/sentry-triage <Sentry issue URL | issue-id | natural language> [--ref <analysis ref>] [--base <PR base>]
```

- `--ref` is the analysis branch (default `main` = deployed to prod), `--base` the PR base (default `develop`). The defaults separate the two so prod errors are analyzed on main and PRs go to develop.

## Flow

1. **Trace** — get issue details (`get_sentry_resource`) + Seer root cause (`analyze_issue_with_seer`) via the Sentry MCP and map them onto the `--ref` code.
2. **Verdict** — clear (single cause · local minimal fix · our code) vs ambiguous (multiple causes · cross-service · contract change · product judgment · wide blast radius). Even slightly ambiguous means ambiguous.
3. **Clear** → hand off to `fix-bug` (seeded with the established facts) → minimal fix · validation · PR (`--base`). Before starting, check whether base already has the fix to avoid duplicates.
4. **Ambiguous** → handled without code. Interactive asks the user; headless posts to Slack + `@mentions` on-call.
5. **Report** — always leave a short note via Slack Incoming Webhook (no sensitive data).

## Settings (env)

| env | Purpose |
|---|---|
| `SENTRY_TRIAGE_SLACK_WEBHOOK` | Slack Incoming Webhook URL (sends the report) |
| `SENTRY_TRIAGE_ONCALL` | Slack member id to mention when ambiguous (e.g. `<@U123>`) |
| `SENTRY_TRIAGE_AUTOFIX` | Headless auto-fix on/off (default on). When off, headless only reports |

Connecting the remote Sentry MCP (`https://mcp.sentry.dev/mcp`) is recommended:
`claude mcp add --transport http sentry https://mcp.sentry.dev/mcp`

## Auto-trigger (headless)

For the plumbing that starts it with no human involvement — Sentry Alert → Webhook → CI running `claude -p "/sentry-triage <url>"` — see
[`automation/README.md`](automation/README.md) and [`automation/sentry-triage.yml`](automation/sentry-triage.yml).
Safe defaults: PRs always use `--base develop`, **no auto-merge** (humans review/merge).

## Related skills

- [fix-bug](../fix-bug/) — receives the actual fix + PR on a clear verdict.
- [impact-check](../impact-check/), [decide-approach](../decide-approach/) — used in parallel inside fix-bug.
- [jira-sync](../jira-sync/) — syncs ticket status after merge.

## Using it outside the team

The Sentry org/project, Slack channel, and branch conventions (`main`/`develop`/`f-{{JIRA_PROJECT_KEY}}-*`) follow this team's setup.
Change only the `--ref`/`--base` defaults, the env, and org parsing (subdomain) to fit your team and it's reusable.
