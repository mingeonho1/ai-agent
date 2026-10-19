# jira-sync

A skill that automatically keeps my Jira ticket status in sync with **how far** that ticket's work has progressed through the deploy pipeline.

## Background
As the deploy flow shifted to `f-{{JIRA_PROJECT_KEY}}-{n}/* → develop → staging → main`, the `develop → staging → main` promotions happen via automated merges (Mon/Thu cron). So the staging/main arrivals you didn't merge yourself tend to leave the Jira status lagging behind reality. This skill catches up that gap.

## Multi-repo (the MIN rule)
A single ticket can touch several repos at once — `{{REPO_PREFIX}}-back`, `{{REPO_PREFIX}}-lambda`, `{{REPO_PREFIX}}-front`, etc. The skill **auto-detects `{{REPO_PREFIX}}-*` git repos in cwd's parent directory** and inspects them all. Among the repos that reference the ticket, it treats the **least-advanced repo (MIN)** as the ticket's real stage — i.e. the ticket only advances to `완료` once *every* related repo has reached `main`. If even one repo is still at `develop`, the ticket stops there too, and the plan table shows "what's holding it back (the limiting repo)". (Repos that don't reference the ticket are irrelevant and excluded.)

## Status ↔ branch mapping
| Work has reached | Jira status (exact spelling) |
|---|---|
| feature branch only (`f-{{JIRA_PROJECT_KEY}}-{n}/*`) | 진행 중 |
| `develop` | DEV 배포완료 |
| `staging` | QA |
| `main` | 완료 |

> Status names must match **exactly, down to case and spaces** (`DEV 배포완료` ≠ `dev배포완료`). The {{JIRA_PROJECT_KEY}} workflow also has `해야 할 일` and `드롭`, and `완료`/`드롭` are terminal states, so they aren't advancement targets.

## Usage
```
/jira-sync [assignee]
```
- If no assignee is given, it **always asks for input** (e.g. `{{GIT_AUTHOR}}`). It only touches your own tickets.
- It shows the plan table first and transitions status **only after getting confirmation**.
- Status only moves **forward**. If Jira is ahead of git, it doesn't roll back — it marks the ticket "needs review".

## Prerequisites
- **Atlassian (Jira) MCP connected/authenticated**. If not connected, it guides you to connect and stops.
- Commits/branches must carry the `{{JIRA_PROJECT_KEY}}-{n}` key (`f-{{JIRA_PROJECT_KEY}}-{n}/*`, `[type]: {{JIRA_PROJECT_KEY}}-XXX …`). git↔Jira are effectively linked by the key.
- The `{{REPO_PREFIX}}-*` repos to inspect must be **checked out together in cwd's parent directory** (e.g. `~/work/{{REPO_PREFIX}}-back`, `~/work/{{REPO_PREFIX}}-lambda`). Each repo must have the remote branches `develop`/`staging`/`main`.

## Porting to another team/project
In SKILL.md, change only the following:
- JQL `project = {{JIRA_PROJECT_KEY}}` → that project's key
- Status names `진행 중 / dev배포완료 / qa / 완료` → that workflow's status names
- The branch names in the mapping table (`develop`/`staging`/`main`)
- The repo auto-detect glob `{{REPO_PREFIX}}-*` → that team's repo prefix
