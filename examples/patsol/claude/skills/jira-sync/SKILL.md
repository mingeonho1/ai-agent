---
name: jira-sync
description: Sync your own Jira tickets' status to match how far each ticket's work has progressed through the deploy pipeline (develop→DEV 배포완료, staging→QA, main→완료) across every sibling {{REPO_PREFIX}}-* repo — least-advanced repo wins, advance-only. Uses the Atlassian MCP + git. Respond in the user's language (match the language the user writes in).
---

# jira-sync

Reconcile Jira status with git reality. For each ticket assigned to you, find how far its work has merged through `f-{{JIRA_PROJECT_KEY}}-{n}/* → develop → staging → main` **in every sibling repo that carries the ticket**, take the least-advanced repo as the ticket's true stage, and move the ticket to match.

## Status ↔ branch mapping
Status names below are the **exact** {{JIRA_PROJECT_KEY}} project workflow names — match them verbatim. In JQL case doesn't matter but **the space does** (`DEV 배포완료`, not `dev배포완료`); for transitions/comparison, use the exact name to be safe:
| Work has reached | Jira status |
|---|---|
| feature branch only (`f-{{JIRA_PROJECT_KEY}}-{n}/*`, not merged) | 진행 중 |
| `develop` | DEV 배포완료 |
| `staging` | QA |
| `main` | 완료 |

({{JIRA_PROJECT_KEY}} workflow also has `해야 할 일`=To Do and `드롭`=Dropped. `완료`/`드롭` are terminal — never advanced.)

`develop → staging → main` promotions are automated (Mon/Thu cron), so status drifts behind reality — this skill catches up the staging/main promotions you didn't merge yourself.

## Input
`/jira-sync [assignee]` — Jira username/accountId. If omitted, **ask** (never default). Example: `{{GIT_AUTHOR}}`.
Only tickets assigned to this user are ever touched.

## Flow

### 0. Pre-checks (guide on fail, don't crash)
- **Atlassian MCP authenticated?** If MCP calls fail unauthenticated → tell the user to connect/authenticate the Atlassian (Jira) MCP, then stop.
- **assignee provided?** If not → ask (example `{{GIT_AUTHOR}}`); resolve via `lookupJiraAccountId` if needed.
- **git ↔ Jira linked?** Repos must reference Jira keys in branches/commits (`f-{{JIRA_PROJECT_KEY}}-{n}/*`, `[type]: {{JIRA_PROJECT_KEY}}-XXX …`). If no `{{JIRA_PROJECT_KEY}}-` references exist in any discovered repo → tell the user git isn't linked to Jira and stop.
- **Discover repos** — one ticket's work may merge across several repos, so sync spans all sibling `{{REPO_PREFIX}}-*` git repos in cwd's parent dir, auto-detected:
  ```bash
  for d in "$(dirname "$PWD")"/{{REPO_PREFIX}}-*/; do [ -d "$d.git" ] && echo "${d%/}"; done
  ```
  Use the list as the repo set (always include cwd if it qualifies). If only cwd qualifies, proceed with just that. List the detected repos to the user before continuing.
  > Jev note: a ticket's involved repos are determined **deterministically** in step 2 by grepping its key (`{{JIRA_PROJECT_KEY}}-{n}`) across each repo's history — there is no ambiguous "which repo?" choice here, so the Jev `choice` repo-routing does not apply and is intentionally not used in this skill.
- `git -C <repo> fetch --all --prune` for **each** discovered repo so remote env branches are current. git stays read-only throughout this skill — `fetch` only, never commit/push/merge.

### 1. Pull the user's active tickets
`searchJiraIssuesUsingJql`:
```
assignee = <user> AND project = {{JIRA_PROJECT_KEY}} AND status IN ("해야 할 일","진행 중","DEV 배포완료","QA") ORDER BY key
```
(`완료`/`드롭` are terminal — excluded. `해야 할 일` is included so a ticket coded but not yet moved still gets advanced.)

### 2. Determine each ticket's stage (MIN across all involved repos)
A ticket may touch several repos. **Per repo**, grep the key in each env branch's history (robust even after the feature branch is deleted), highest priority wins (main > staging > develop > feature). **Anchor the key on a word boundary** so `{{JIRA_PROJECT_KEY}}-12` doesn't match `{{JIRA_PROJECT_KEY}}-123` — a wrong match would mis-transition a ticket:
```bash
# run inside each discovered repo (git -C <repo> …); {n} = the ticket's number
git -C <repo> log origin/main    -E --grep "(^|[^0-9]){{JIRA_PROJECT_KEY}}-{n}([^0-9]|$)" --oneline -1   # → 완료
git -C <repo> log origin/staging -E --grep "(^|[^0-9]){{JIRA_PROJECT_KEY}}-{n}([^0-9]|$)" --oneline -1   # → QA
git -C <repo> log origin/develop -E --grep "(^|[^0-9]){{JIRA_PROJECT_KEY}}-{n}([^0-9]|$)" --oneline -1   # → DEV 배포완료
git -C <repo> branch -a --list "*{{JIRA_PROJECT_KEY}}-{n}" --list "*{{JIRA_PROJECT_KEY}}-{n}/*"                             # feature only → 진행 중
```
A repo that **never references** `{{JIRA_PROJECT_KEY}}-{n}` is not involved — skip it (don't let it drag the stage down). Among the **involved** repos, the ticket's effective stage is the **MIN (least-advanced)**: it isn't `완료` until *every* involved repo reached `main`, not `QA` until every one reached `staging`, etc. Record which repo is the limiting one — it's shown in the plan so the user sees what's holding the ticket back. (Repos can be grepped in parallel; outputs are one line each.)

### 3. Compare & plan
- expected **ahead** of current → plan a forward transition.
- expected **==** current → keep (already in sync).
- expected **behind** current (Jira ahead of git) → **never downgrade**; flag needs review.
- nothing found → flag "no branch — needs checking".

### 4. Present plan & confirm
Table: `# | {{JIRA_PROJECT_KEY}}-key | current | git reached (limiting repo) | → target | action (move/keep/needs review)`. Show the limiting repo when more than one repo carries the ticket (e.g. `develop — {{REPO_PREFIX}}-lambda is the limiter`).
Ask `move all` or per-item `1=move, 2=keep, …`. Transitioning Jira is outward-facing — never apply without confirmation.

### 5. Transition approved tickets
Per ticket: `getTransitionsForJiraIssue` → pick the transition to the target status → `transitionJiraIssue`. Re-check assignee == resolved user before each transition. If no direct transition to the target status exists (workflow needs intermediate steps), don't force it — flag needs review and move on.

### 6. Final summary
```
Jira sync complete (N targets, assignee <user>)
✅ Moved: N — {{JIRA_PROJECT_KEY}}-xxxx 진행 중 → QA (reached staging)
⏭ Kept: N — already in sync
⚠ Review: N — {{JIRA_PROJECT_KEY}}-xxxx Jira is ahead of git / no branch
```

## Dependencies
Atlassian (Jira) MCP authenticated; sibling `{{REPO_PREFIX}}-*` repos with remote `develop`/`staging`/`main` branches; project key `{{JIRA_PROJECT_KEY}}`. (See README to adapt project key / status names / repo glob for another team.)

## Example
```
User: /jira-sync
→ An assignee is required. Enter a Jira username (e.g. {{GIT_AUTHOR}})
User: {{GIT_AUTHOR}}
→ Repos detected: {{REPO_PREFIX}}-back, {{REPO_PREFIX}}-lambda, {{REPO_PREFIX}}-front / fetch done / 4 active tickets
→ Plan:
  {{JIRA_PROJECT_KEY}}-123 진행 중      → QA    (staging — back & lambda both reached)       move
  {{JIRA_PROJECT_KEY}}-124 DEV 배포완료 → keep   (develop — back is at main but lambda limits) keep
  {{JIRA_PROJECT_KEY}}-125 DEV 배포완료 → keep   (develop)                                    keep
  {{JIRA_PROJECT_KEY}}-126 QA           ⚠ only git develop reached — Jira is ahead           needs review
User: move all
→ {{JIRA_PROJECT_KEY}}-123 → QA transition done ({{JIRA_PROJECT_KEY}}-124 held because lambda is at develop)
```
