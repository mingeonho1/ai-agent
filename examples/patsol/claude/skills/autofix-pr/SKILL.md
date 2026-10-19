---
name: autofix-pr
description: Fetch a PR locally, run a fresh Claude code review, classify findings by severity (High/Medium/Low), let the user pick Apply/Skip/Defer per item, then apply approved fixes in a single commit and reply under each line comment with the disposition. Uses gh CLI only — no Claude GitHub App required.
---

# autofix-pr

Local PR review with selective fix application. Operates on the git repo at cwd.

Respond in the user's language (match the language the user writes in). This applies to tables, PR review comments and replies, and the final summary.

## Input

`/autofix-pr [PR_NUMBER]` — if omitted, resolve via `gh pr list --head $(git branch --show-current)`. Ask user if 0 or >1 match.

## Flow

### 0. Pre-checks (abort on fail)

```bash
gh pr view <N> --json number,headRefName,baseRefName,url,state,isDraft,title
git status --short
```

- `state != OPEN` → ask user before continuing.
- `headRefName` is `main` or `develop` → **abort** (no commits to protected branches).
- Working tree dirty → abort, tell user to stash/commit.

### 1. Checkout + diff

```bash
gh pr checkout <N>
gh pr diff <N> > /tmp/autofix-pr-<N>.diff
gh pr view <N> --json files --jq '.files[].path'
```

Read changed files in full for context.

### 2. Fresh review

Analyze the diff across:
- **Security**: hardcoded secrets, SQL/NoSQL injection, auth/authz, PII exposure
- **Bugs**: missing await, None/exception handling, race conditions, tx boundaries
- **Performance**: blocking sync I/O, N+1, inefficient queries
- **Conventions**: project CLAUDE.md (e.g. gw is JWT-verify-only, 202+task_id pattern, commit format)
- **Tests**: coverage for new logic, edge cases

Structure each finding: `{id, severity: High|Medium|Low, category, path, line, title, detail, suggested_fix}`

**Severity rubric**:
- **High**: security vulns, data loss, outage risk, major convention violations
- **Medium**: functional bugs, normal convention violations, perf regressions
- **Low**: style, naming, comments, nice-to-have

### 2.5 Jev cross-check (required — skip only when the call fails)

**Always run `jev.py`** — don't omit it even if there are few findings or the classification looks obvious. Don't pre-judge whether a key exists from `$TYPESAFE_API_KEY` (the key may live in the `~/.config/jev/api_key` file; if it's missing, jev.py tells you by exiting abnormally).

An auxiliary signal for deciding whether a human should take a second look at Claude's classification. Send **all**
findings to Jev (TypeSafe System One) in **a single call**. Question ids are only my keys and are not passed to the
model, so put the finding's title/detail and code context (`path:line`, a relevant code excerpt) directly inside each
question's `instructions`.

Two questions per finding:
- `sev_<id>` — `score`; criteria are the severity definitions above in **Low→Medium→High (low→high)** order.
- `real_<id>` — `noul`, "Is this finding a real defect in the code shown (not a false positive)?"

Write the request JSON to a temp file `$f` (Write tool recommended, or `mktemp`) and pass it via stdin. Quotes, backticks, and `$` in code excerpts break an inline heredoc, so don't use a heredoc. Contents of `$f`:
```json
{
  "state": "Cross-check of code review findings for PR #<N>. Judge only from each question's code context.",
  "questions": {
    "sev_1": {
      "type": "score",
      "instructions": "[finding] <title>\n<detail>\n<path>:<line>\n```\n<relevant code excerpt>\n```\nHow severe is this review finding?",
      "criteria": [
        "style, naming, comments, nice-to-have",
        "functional bugs, normal convention violations, perf regressions",
        "security vulns, data loss, outage risk, major convention violations"
      ]
    },
    "real_1": {
      "type": "noul",
      "instructions": "[finding] <title>\n<detail>\n<path>:<line>\n```\n<relevant code excerpt>\n```\nIs this a real defect in the code shown (not a false positive)?"
    }
  }
}
```
```bash
python3 ~/.claude/skills/jev-scope/jev.py call < "$f"
```

Response: `{"answers":{"sev_1":{"score":N,"probabilities":[...],"confidence":..},"real_1":{"noul":0..1}},"usage":..}`.
- `score` is the level picked from the criteria array → **map it back to Low/Medium/High by position**, and show that
  level's `probabilities` value as the probability.
- Only two skips are allowed: jev.py exits abnormally (no key / API error), or there are 0 findings. In that case
  print one line `Jev skipped — <reason>` and continue the normal flow (omit the Jev columns and ⚠ below).

### 3. Present to user

Show findings grouped by severity in a table. If the Jev cross-check ran, append Jev severity (prob) and defect
probability (noul) columns next to Claude's severity — **Claude's severity is primary**, Jev is for reference only.
Columns: `# | Claude severity | Jev severity (prob) | Defect prob | ⚠ | category | path:line | Gist`.

**⚠ flag (a "take another look" marker):** add ⚠ to items where Claude says High but Jev says Low, or the defect
probability (noul) < 0.4. The flag is only a caution signal; it does not change Claude's severity.

Ask for per-item disposition. Accept:
- `all apply` / `all skip` / `all defer`
- Per-item: `1=apply, 2=skip, 3=defer, ...`
- Korean equivalents are also accepted (e.g. `전부 반영` / `전부 스킵` / `전부 보류`, `1=반영, 2=스킵, 3=보류`) — Korean users type these.

Dispositions: **Apply** apply, **Skip** reply with rationale only, **Defer** reply marking for later, no edit.

### 4. Post the review on the PR

Post **before** editing — creates the line comments step 6 replies to.

```bash
gh api -X POST repos/{owner}/{repo}/pulls/<N>/reviews \
  -f event="COMMENT" \
  -f body="<summary of findings>" \
  -F "comments=@/tmp/autofix-pr-comments.json"
```

Each entry in `comments[]` has `path`, `line`, `body` (in the user's language). Capture returned comment IDs.

### 5. Apply items marked Apply — single commit

Edit all Apply files. Stage + commit. Message format (from `~/.claude/CLAUDE.md`):

```
[fix]: {{JIRA_PROJECT_KEY}}-XXX Apply PR review feedback (High N / Medium N)

- <path>:<line> <short description>
- ...
```

- Extract `{{JIRA_PROJECT_KEY}}-XXX` from PR title; if absent, ask user.
- pre-commit hooks **must pass** — never `--no-verify`. Fix the root cause and commit again on failure.
- `git push` (never `--force`).

### 6. Reply under each line comment

```bash
gh api -X POST repos/{owner}/{repo}/pulls/<N>/comments/{ID}/replies -f body="<text>"
```

Reply templates (write PR replies in the user's language):
- **Apply**: `Applied — {SHORT_SHA}.` + optional 1-line summary
- **Skip**: `Not applying. Reason: {structural/constraint-based rationale}.` (no bare rejections)
- **Defer**: `Decision deferred for now. Will revisit at {trigger/time}.`

### 7. Final summary to user

```
PR #<N> done
✅ Applied N (1 commit: <SHA>) - <path>:<line> ...
💬 Skipped N               - <path>:<line> — <reason>
⏸ Deferred N               - <path>:<line> — <note>
🔎 Jev: ran (⚠ N) | skipped — <reason>
```

## Guardrails (hard stops)

- Never `gh pr merge`, never `git reset --hard`.
- Only handle **new findings** — do not read or reply to existing bot/human review comments.
- **No frontend edits** — FE repos (`{{GITHUB_ORG}}/{{FRONTEND_REPO_NAME}}`, `{{FRONTEND_REPO_NAME}}`) are owned by a separate agent. If a finding needs FE changes, mark Skip with that reason or update `docs/fe/` only.
- **No JWT issuance** in gw — verify-only.

## Dependencies

`gh` CLI (authenticated), `git`. cwd must be the PR's target repo.

## Example

```
User: /autofix-pr 12
→ 7 findings: High 3 / Medium 3 / Low 1 → [table shown]
User: 1=apply, 2=apply, 3=apply, 4=apply, 5=apply, 6=defer, 7=skip
→ review posted (7 line comments) → 5 fixes applied (commit abc1234, pushed) → 7 replies → Done
```
