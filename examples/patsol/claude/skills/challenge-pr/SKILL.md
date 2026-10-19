---
name: challenge-pr
description: Adversarially challenge a PR's DESIGN DECISIONS in the style of a Toss senior engineer — not a bug hunt and not a bot-comment triage (complements review-feedback). Returns 3-5 pointed "Why did you do it this way?" questions, each with the alternative the reviewer would have taken. Read-only, questions-only — never edits code, never posts to the PR. Respond in the user's language (match the language the user writes in).
---

# challenge-pr

Force the author to **defend their design decisions** — the ones a green test and a passing linter never question. A challenge review where a Toss senior engineer questions the PR head-on.

Complements `review-feedback` (which triages whether **comments bots already posted** are valid). This skill is the other axis: independently of the bots, it asks **whether this PR's design is good**. Running it right after review-feedback keeps the triage from becoming a rubber stamp.

## Input

`/challenge-pr [PR_NUMBER]` — if omitted, find the current branch's open PR with `gh pr list --head $(git branch --show-current)`. If there are 0 or 2+ results, confirm with the user. If there is no PR, ask whether to proceed with the branch diff (base chosen as in step 1 below).

## Flow

### 1. Get the target diff (read-only)

```bash
# when there is a PR
gh pr view <N> --json number,headRefName,baseRefName,url,title
gh pr diff <N> > /tmp/challenge-pr-<N>.diff
```

If there is no PR, pick the base, then `git diff <base>...HEAD > /tmp/challenge-pr-branch.diff`:

```bash
# choose base: look up and use the repo's default branch
base=$(gh repo view --json defaultBranchRef --jq .defaultBranchRef.name)   # usually main or develop
```

If the default branch isn't this work's base (e.g. the PR targets develop but the default is main), **ask the user for the base branch name**. **Read only — no checkout, no edits.**

### 2. Run the challenge review

Spawn the `toss-senior-challenger` subagent. Pass the diff file path (or branch + base) and the PR title/description to give it clues to the **business intent**. The agent picks the 3-5 most contentious design decisions and writes strongly opposing questions — the question format, labeling rules, and focus (architecture / trade-offs / business impact) are all owned by the agent, so don't reproduce them here.

### 3. Present the questions to the user

Show the agent's questions as-is. Whether to act on them is the author's call.

## Guardrails (hard stops)

- **Read-only, questions-only** — no PR checkout, working-tree changes, code edits, commits, pushes, or PR comments whatsoever. The only output is the question list. (To apply changes, use `autofix-pr`/`review-feedback`.)
- Content rules for the questions (no style nitpicks, alternative required, no padding the count) are owned by the `toss-senior-challenger` agent.

## Dependencies

`gh` CLI (authenticated), `git`, `toss-senior-challenger` subagent (linked into `~/.claude/agents/`). cwd is the target repo.

## Example

```
User: /challenge-pr 12
→ Got PR #12 diff (feat/{{JIRA_PROJECT_KEY}}-123-x → develop), read intent from title/description
→ Ran toss-senior-challenger → challenged 4 design decisions:
    • [question] service.py:82 — Why did you bind payment confirmation into a synchronous call?
        (I'd probably have moved it to an event — settlement delays propagate into the order API response.)
    • [suggestion] handler.py:30 — Wouldn't this branching logic be better in the domain layer? ...
    • [question] ... / [fyi] ...
→ Want an answer to this first: #1
(questions shown only — code/PR unchanged)
```
