# sentry-triage auto-trigger plumbing

Goal: **when Sentry raises an error, with no human involvement**, `sentry-triage` starts, opens a PR (if clear),
or reports to Slack with an `@mention` (if ambiguous).

## Why a relay is needed

A Sentry Alert's Webhook POSTs **Sentry's own payload** to an arbitrary URL. The `repository_dispatch` that triggers
GitHub Actions requires a separate auth header + a fixed body format, so a **thin relay** is needed between them.
(Adding one function to the team's existing `{{REPO_PREFIX}}-lambda` is cheapest.)

```
Sentry Alert Rule
   └─(Webhook: issue payload)→  relay (Lambda/Function)
                                   └─(repository_dispatch: type=sentry-alert, issue_url)→  GitHub Actions
                                                                                              └─ claude -p "/sentry-triage <url>"
```

## 1. Sentry Alert Rule

- Target project → **Alerts → Create Alert → Issues**.
- Example conditions: "A new issue is created" or "event frequency > N / 5m".
- Action: **Send a notification via a webhook** → the relay endpoint URL.
- (Leave existing Slack alert rules as they are — this is a separate channel for auto-start.)

## 2. Relay (example — language-agnostic, essentials only)

Extract the issue URL from the Sentry payload and pass it to GitHub `repository_dispatch`:

```python
# pseudo — Lambda handler
import json, urllib.request

def handler(event, _ctx):
    body = json.loads(event["body"])
    issue_url = body.get("url") or body["data"]["issue"]["web_url"]  # adjust to the payload format
    req = urllib.request.Request(
        "https://api.github.com/repos/{{GITHUB_ORG}}/{{BACKEND_REPO_NAME}}/dispatches",
        method="POST",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",   # repo scope PAT / App token
            "Accept": "application/vnd.github+json",
        },
        data=json.dumps({"event_type": "sentry-alert",
                         "client_payload": {"issue_url": issue_url}}).encode(),
    )
    urllib.request.urlopen(req)
    return {"statusCode": 204}
```

- The relay should **verify** the Sentry Webhook signature (if present) and debounce repeat firings for the same issue (e.g. once per issue per hour).

## 3. GitHub Actions

Put `sentry-triage.yml` in the target repo's `.github/workflows/`. It triggers on both `repository_dispatch(type: sentry-alert)`
and manual (`workflow_dispatch`). Headless `claude -p` runs the skill.

### Required Secrets

| secret | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Run Claude Code |
| `SENTRY_TRIAGE_SLACK_WEBHOOK` | Slack report |
| `SENTRY_TRIAGE_ONCALL` | Mention target when ambiguous |
| `SENTRY_MCP_TOKEN` | Auth token for the local (stdio) Sentry MCP (scopes: org/project read, event write) |
| `GH_PR_TOKEN` | For opening PRs (`gh`) |

## Safe defaults (important)

- **The PR base is always `develop`**; **no** direct commits/merges/auto-merges to prod (main). PRs are reviewed/merged by humans.
- **If ambiguous, zero lines of code** — only a Slack report + `@on-call`.
- With `SENTRY_TRIAGE_AUTOFIX=0`, headless **only reports** (no PR even when clear) — start with this early on and turn it on once trust builds.
- Keep the permission mode minimal (`--permission-mode acceptEdits`) and limit shell/network to the CI runner's scope.
