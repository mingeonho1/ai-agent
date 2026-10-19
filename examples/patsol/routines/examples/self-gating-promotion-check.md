---
name: example-self-gating-promotion-check
description: (Example pattern) A weekday recurring task that gates itself on whether the observation period has ended; once it has, it checks read-only metrics and only judges "promotion OK / hold" — never merges or deploys itself, only proposes. Respond in the user's language (match the language the user writes in).
---

> This file is **an example template for the self-gating recurring check pattern**.
> Use it when you've shipped a change to a lower environment (dev), observe it for a set period, and once the period
> is up, decide with data whether to promote it to the upper environment (main). Fill in `<...>` with your own
> context and register it as a scheduled task. Three core patterns:
> **(1) do nothing before the condition, (2) announce self-termination once the condition is met / work is done,
> (3) read and query only — merge/deploy/PR creation only after user approval.**

<One line on what this follow-up check is for>. Respond in the user's language (match the language the user writes in).

0. If today's date is before `<observation end date YYYY-MM-DD>`, do nothing; leave only the one line "Waiting (checks start `<that date>`)" and exit.
   First check whether it's already in the upper environment (e.g. `gh pr list --repo {{GITHUB_ORG}}/{{BACKEND_REPO_NAME}} --base main --state merged --search "{{JIRA_PROJECT_KEY}}-123"`, or whether the change already exists on the main branch). If it already is, report only the one line "Promotion done — please turn off this scheduled task under Scheduled in the sidebar." and exit.

Background: `<What was shipped, when, and where (lower environment) — summary of the change's nature and what to observe>`. The plan was to observe it in the lower environment for `<observation period>` and promote it if there were no problems.

To do (read and query only; do not merge, deploy, or create PRs):
1. Query the lower environment's key metrics as a time series since the deploy (e.g. memory/CPU/error-rate trends, any restarts, OOMs, or error-log anomalies). Judge slopes and anomaly signs.
2. Conclusion: "Promotion OK" or "Hold (reason) — recheck next weekday". Report query failures (permissions, credentials, network, etc.) as "Hold (query failed: cause)" too — the next weekday run retries automatically.
3. If OK, **only propose** the promotion procedure (state the review/approval steps per team rules). Actually creating a PR, merging, or deploying happens only after user approval.
