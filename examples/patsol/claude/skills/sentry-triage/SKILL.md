---
name: sentry-triage
description: Triage a Sentry production error end-to-end — pull the issue via the Sentry MCP, analyze root cause against the deployed ref (default main), then gate on clear-vs-ambiguous. Clear (single pinned cause, local minimal fix, in our code) → hand to fix-bug and open a PR against the base (default develop). Even slightly ambiguous (multiple causes, cross-service/data-server, product/contract decision, wide blast radius) → post a concise Slack report via Incoming Webhook with an @mention to on-call, no code. Always posts a short Slack report. Works interactively or headless (auto-trigger from a Sentry alert). Respond in the user's language (match the language the user writes in).
---

# sentry-triage

A triage skill that takes a Sentry production error through **trace → clear/ambiguous verdict → branch handling**.
It doesn't fix things itself: if clear, it hands off to the `fix-bug` pipeline; if ambiguous, it hands off to a human. Respond in the user's language (match the language the user writes in).

- **Clear** → `fix-bug` reproduces, validates, makes the minimal fix, and opens a PR (base defaults to `develop`).
- **Even slightly ambiguous** → touch no code; post a summary to Slack + `@mention` on-call.
- **Always** leave a short result in Slack (Incoming Webhook).

## Input

`/sentry-triage <Sentry issue URL | issue-id | natural language>` `[--ref <analysis ref>]` `[--base <PR base>]`

- e.g. `/sentry-triage https://{{SENTRY_ORG}}.sentry.io/issues/12345678/`, `/sentry-triage 12345678 --base hotfix/x`
- Parse org (subdomain) and issue-id (path) from the URL. For natural language, find candidates with `search_issues` and confirm — **if it can't be narrowed to a single issue** (multiple candidates), ask back in interactive mode; in headless mode, absorb it as an ambiguous verdict, post to Slack, and exit (never start on a guess).
- `--ref` (analysis basis, default `main` = the branch deployed to prod) and `--base` (PR base, default `develop`) are **separate** — prod errors are analyzed against main, but the fix PR goes to develop.

## Run modes (premise for the verdict branch)

- **Interactive**: a human invokes `/sentry-triage`. If ambiguous, ask the user 1–2 clarifying questions; once resolved, continue down the clear flow.
- **Headless** (auto-trigger / `claude -p`): there's nobody to ask. **If ambiguous, never stop to wait — post to Slack + `@mention` and exit.** Report instead of asking. (See `automation/` for the plumbing.)
- Determine the mode from TTY / auto-trigger. If unsure, assume headless (the safe side).

## Preflight (on failure, explain and stop — never crash)

1. **Sentry MCP connected?** Check with `find_organizations`/`find_projects`. If not connected, explain how to connect the remote MCP (`https://mcp.sentry.dev/mcp`) and stop.
2. **Slack Webhook?** Check env `SENTRY_TRIAGE_SLACK_WEBHOOK`. If missing: interactive → warn only and proceed without Slack (console report instead); headless → log it and proceed.
3. **On-call mention target**: env `SENTRY_TRIAGE_ONCALL` (Slack member id, e.g. `<@U123ABC>`). If missing, use the channel default (`@here`).
4. `git fetch --all --prune` — refresh the `--ref`/`--base` remote branches.

## Flow

### 1. Trace the issue (Sentry MCP)
- Fetch issue details with `get_sentry_resource` (stack trace, frequency, affected users, first seen, tags). If `search_issues`/`search_events` is blocked (intermittent outage), work around it with a direct issue-id lookup.
- For root-cause analysis, get file/line candidates from `analyze_issue_with_seer` (Seer). Treat Seer's result as a **hypothesis** and cross-check it against the code.
- Map the stack trace's `file:line` onto **the code at `--ref` (main)**. Delegate any broad exploration to an Explore subagent.

### 2. Clear/ambiguous verdict (the core gate)
Only "clear" when **all** clear conditions below hold. If any one fails, classify as "ambiguous" (even slightly ambiguous means ambiguous).

**Clear (→ 3A auto-fix)**
- A single root cause is pinned down by the stack trace + code.
- Reproducible, or the cause is self-evident in the code.
- The fix is a **local minimal change** (inside our repo, no contract/schema change).
- No product/business judgment is needed.

**Ambiguous (→ 3B report + assign)** — if any of these apply:
- Two or more root-cause candidates, or reproduction depends on data/timing.
- The cause is **cross-service** (on-prem data server, lambda, external API, etc.), so this repo can't fix it. *(e.g. an `upstream-api` upstream 5xx can't be root-fixed here.)*
- It triggers a contract/response schema change or has a wide blast radius.
- A product decision or policy judgment is needed.

**Jev cross-check (optional — calibrates if available, skipped otherwise)**
Right after root-cause analysis, ask Jev (the TypeSafe decision model) the same gate criteria as noul questions and use the answers as a calibration signal.
Build `state` as a single string of **issue summary + analyzed cause + candidate fix location (`file:line`) + blast radius**.
One noul per criterion — each phrased so `true` = favors clear (single cause / local minimal fix / our code / not cross-service / no product decision needed):
```
echo '<JSON below>' | python3 ~/.claude/skills/jev-scope/jev.py call
```
```json
{
  "state": "<issue summary + cause + file:line + blast radius>",
  "questions": {
    "single_cause":        {"type":"noul","instructions":"Is a single root cause pinned down by the stack trace and code?","criteria":{"true":"The cause is fixed to one and confirmed by stack trace + code.","false":"There are two or more cause candidates, or reproduction depends on data/timing."}},
    "local_fix":           {"type":"noul","instructions":"Is the fix a local minimal change (no contract/schema change)?","criteria":{"true":"It ends with a narrow minimal fix and the blast radius is small.","false":"It triggers a contract/response schema change or the blast radius is wide."}},
    "our_code":            {"type":"noul","instructions":"Can it be fixed inside this repo's code?","criteria":{"true":"The cause and fix point are inside our repo's code.","false":"The fix point is outside this repo."}},
    "not_cross_service":   {"type":"noul","instructions":"Is the cause NOT cross-service (on-prem data server, lambda, external API)?","criteria":{"true":"The cause is internal to this service, not an upstream service's fault.","false":"The cause lies in another service such as an upstream data server, lambda, or external API."}},
    "no_product_decision": {"type":"noul","instructions":"Can it be fixed without a product/policy judgment?","criteria":{"true":"It can be fixed technically without a product/business decision.","false":"A product decision or policy judgment is needed."}}
  }
}
```
Combine the five probabilities in the response `{"answers":{id:{"noul":0..1}},...}` with Claude's own verdict to branch:
- All five noul **≥ 0.8** **and** Claude judges it clear → **3A (clear)**.
- Any one **< 0.5** → **3B (ambiguous)**.
- In between (straddling 0.5–0.8) → **3B (ambiguous)** — keeps this skill's "report if even slightly ambiguous" bias.
- If the Jev call fails (no key, error), **skip it silently** and decide with the Claude gate above alone (existing logic unchanged). **Never auto-fix on Jev alone** — a clear verdict always requires Claude's agreement.

### 3A. Clear → hand off to fix-bug + PR
1. **Duplicate check first**: before starting, check whether it's **already fixed on the PR base (`--base`)** (pickaxe for related commits/symbols in `git log <base>`). If it's a regression remaining only in prod (main) and base already has the fix — **no code change**; go to the report step as "resolved by next deploy" and exit.
2. Hand off to the `fix-bug` pipeline, seeding it with **the facts established in step 1** (cause, `file:line`, stack trace, repro hints) — don't make it re-investigate from scratch. fix-bug performs repro, impact-check/decide-approach, pre-fix validation, minimal fix, end-to-end re-verification, git tracing, a clean commit, and the PR.
3. The fix branch is `f-{{JIRA_PROJECT_KEY}}-XXXX/...` based on `--base` (develop). **No direct commits/merges to main/develop, no auto-merge** — the PR is for human review/merge.
4. If impact-check during fix-bug reveals a wide regression risk → it wasn't clear after all. Demote to 3B and report.

### 3B. Ambiguous → report + assign (no code)
- **Interactive**: ask the user 1–2 questions on what's ambiguous + the decision needed. If the answers make it clear, go to 3A.
- **Headless**: can't ask, so post a summary to Slack + `@on-call` and exit. (Assignment = Slack mention only — no Sentry/Jira assignee is set.)
- Either way, state the cause hypothesis, where it got stuck, and the judgment needed next.

### 4. Slack report (always, keep it brief)
Post **briefly** via Webhook in every case — success / ambiguous / resolved-by-duplicate:
```
🔴 [Sentry] <project> — <issue title>
• Issue: <url>   • Frequency/impact: <count> events · <n> users · first <first_seen>
• Cause (summary): <one line>
• Jev (verdict): single .__ · local .__ · ours .__ · x-service .__ · no-product .__   # omit this line if Jev was skipped
• Action: ✅ Fix PR #<n> (<base>) <pr_url>
        │ ⚠️ Ambiguous — needs review: <what/why> <@on-call>
        │ ⏭ Already fixed on base — resolved by next deploy
```
Send: `curl -sS -X POST -H 'Content-type: application/json' -d '{"text":"..."}' "$SENTRY_TRIAGE_SLACK_WEBHOOK"`.
**No sensitive data**: never put tokens, PII, or full tracebacks in Slack (summary / first lines only).

### 5. (Optional) Sentry status
- If a PR was opened, in interactive mode ask the user whether to leave a status/comment via `update_issue`, then do it. **Never auto-resolve** (before merge/deploy) — by default leave it untouched.

## Hard stops (the absolute lines among the rules above — for re-checking)

Analysis ref ≠ PR base (§Input) · auto-fix only when clear (§2) · no direct changes to protected branches, no auto-merge (§3A) · no blocking questions in headless (§Run modes) · cross-service goes to an upstream ticket, not a root fix (§2) · no secrets/PII in Slack/logs (§4).

## Auto-trigger plumbing (headless)

For the Sentry Alert → Webhook → CI (`claude -p "/sentry-triage <url>"`) plumbing, see **`automation/README.md`** and the example workflow **`automation/sentry-triage.yml`**. Headless auto-fix on/off is controlled by `SENTRY_TRIAGE_AUTOFIX` (default on); PRs always use `--base develop` · no auto-merge.

## Dependencies

- Sentry MCP connection (remote `mcp.sentry.dev/mcp` recommended).
- Slack Incoming Webhook URL (`SENTRY_TRIAGE_SLACK_WEBHOOK`), on-call mention (`SENTRY_TRIAGE_ONCALL`).
- `gh` (authenticated) · `git`, cwd = target repo. The `fix-bug` skill.

## Related skills

- [fix-bug](../fix-bug/) — receives the actual fix + PR on a clear verdict.
- [impact-check](../impact-check/), [decide-approach](../decide-approach/) — used in parallel inside fix-bug (demote to ambiguous if regression risk surfaces).
- [jira-sync](../jira-sync/) — syncs ticket status after the PR merges.

## Example

```
User: /sentry-triage https://{{SENTRY_ORG}}.sentry.io/issues/12345678/
→ Trace: python-django · "upstream-api non-2xx: 500" · 12 recent events · 3 users
→ Seer+code: search/numbers/ call fails on on-prem data server 5xx (app/base.py)
→ Verdict: ambiguous (cross-service — upstream data server cause, can't root-fix in this repo)
→ Slack: ⚠️ Needs review — data server 5xx, upstream ticket needed @oncall
→ (Note: the 502 conversion is already on develop → the 500 leak is resolved by next deploy)

User: /sentry-triage 87654321        # clear case
→ Trace: KeyError 'createdAt' at serializers.py:88 · reproduced
→ Verdict: clear (single cause · local minimal fix · our code)
→ Hand off to fix-bug → validate → PR #12 (develop) opened → Slack ✅ report
```
