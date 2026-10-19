---
name: review-feedback
description: Respond to existing bot reviews already posted on a PR (Gemini Code Assist, GitHub Action reviewers, CodeRabbit, etc.) — not a fresh Claude review. Independently verifies each finding against the real code, triages Apply/Skip/Defer with the user, applies approved fixes in one commit, replies in each original thread. Uses gh CLI only.
---

# review-feedback

Respond to **pre-existing bot/human review comments** on a PR. Does NOT generate a new review — it triages comments other reviewers already left. Operates on the git repo at cwd.

Complements `autofix-pr` (which starts a fresh Claude review). Use this when Gemini / GitHub Action / CodeRabbit have already commented and you want to triage + apply + reply.

Respond in the user's language (match the language the user writes in). This applies to tables, PR replies, and the final summary.

## Input

`/review-feedback [PR_NUMBER]` — if omitted, resolve via `gh pr list --head $(git branch --show-current)`. Ask user if 0 or >1 match.

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
gh pr diff <N> > /tmp/review-feedback-<N>.diff
gh pr view <N> --json files --jq '.files[].path'
```

Read the changed code as needed to judge whether each comment is in-scope.

### 2. Collect existing review comments

Pull from all three surfaces; bots use different ones:

```bash
# Inline line comments (most bots: Gemini, CodeRabbit)
gh api --paginate repos/{owner}/{repo}/pulls/<N>/comments
# Review-level summaries
gh api --paginate repos/{owner}/{repo}/pulls/<N>/reviews
# Issue-level comments (Gemini often posts its summary here)
gh api --paginate repos/{owner}/{repo}/issues/<N>/comments
```

Keep for each: `{comment_id, in_reply_to_id, author(login/type), path, line, body, html_url}`.

**Filter:**
- Keep bot authors (`user.type == "Bot"`, or logins like `gemini-code-assist[bot]`, `github-actions[bot]`, `coderabbitai[bot]`) and human reviewers. Drop the PR author's own comments and Claude's prior replies.
- **Skip threads already answered** — if a comment already has a reply from the PR author or from this skill, don't re-handle it. (Check `in_reply_to_id` chains.)
- Collapse a bot's summary comment into context; act on the concrete line findings.

If zero actionable comments remain → tell the user and stop (nothing to respond to).

### 3. Independently verify each comment, THEN judge (do NOT trust the bot)

The reviewers here (Gemini Code Assist, GitHub Action reviewers, CodeRabbit) run **weaker models than this session**. Their findings are **hypotheses, not facts** — on subtle behavior, types, and codebase-specific context they are wrong at least as often as they are right. **Never accept OR reject a finding on the bot's say-so. Establish the truth yourself from the code.** This is the most important step of the skill — a wrong Apply ships a bad change, a wrong Skip dismisses a real bug.

For every actionable comment:

1. **Reproduce the claim against the real code.** Read the cited file/lines and the surrounding flow; trace actual types, call sites, and whether the claimed failure can really happen on this PR's code. When a claim is mechanically checkable, **check it — don't reason in your head**: run `python -c "..."`, a focused test, or `rg` for call sites. (e.g. claim "`Decimal >= float` raises TypeError" → actually run `python -c "from decimal import Decimal; print(Decimal('0.5') >= 1.0)"` before believing it.)
2. **Spawn subagent(s) to verify when it pays off** — several findings at once, or a claim needing wide tracing (all callers, cross-module flow, legacy behavior). Launch independent read-only verifiers in parallel; each returns **CONFIRMED / REFUTED with code evidence**. Never let one agent both surface and rubber-stamp the same claim.
3. **Decide from your verification, not from the comment text:**
   - **scope**: `in` (targets a line/behavior this PR introduced or changed) vs `out` (pre-existing code this PR didn't touch, or unrelated work).
   - **validity**: `valid` only after you have **positive evidence** the problem is real on this code; `false_positive` once you have shown it cannot occur (bot misread, wrong about the language/codebase, or already handled elsewhere). "Sounds plausible" is not `valid`.
   - **severity**: High | Medium | Low.

Record the **evidence** (the check you ran, the code fact) for each item — it becomes both the user-facing reason and the reply body. A disposition with no verification evidence is not ready to present.

Severity rubric:
- **High**: security vulns, data loss, outage risk, major convention violations.
- **Medium**: functional bugs, normal convention violations, perf regressions.
- **Low**: style, naming, comments, nice-to-have.

Default suggestion per item (**after** verification):
- `in` + `valid` (confirmed) → suggest **Apply**.
- `false_positive` (refuted) → suggest **Skip** with the proof it doesn't apply.
- `out` of scope → suggest **Skip** ("outside this PR's change scope — a separate issue/PR is recommended").
- verification **inconclusive** (couldn't confirm or refute) → suggest **Defer** stating what's unresolved — never guess Apply/Skip.

### 3.5 Jev cross-check (required — skip only when the call fails)

**Always run `jev.py`** — don't omit it even if there are few comments or the triage looks obvious. Don't pre-judge whether a key exists from `$TYPESAFE_API_KEY` (the key may live in the `~/.config/jev/api_key` file; if it's missing, jev.py tells you by exiting abnormally).

An auxiliary signal for deciding whether a human should take a second look at my triage. Send **all** bot
comments to be handled to Jev (TypeSafe System One) in **a single call**. Question ids are only my keys and
are not passed to the model, so put the comment's gist and code context (`path:line`, a relevant code excerpt)
directly inside each question's `instructions`. It is a signal obtained **independently** of my verification conclusion.

Two questions per comment:
- `tri_<id>` — `choice`; Apply/Skip/Defer criteria exactly as the default suggestion definitions above.
- `real_<id>` — `noul`, "Is this a real defect in the code shown (not a false positive)?"

Write the request JSON to a temp file `$f` (Write tool recommended, or `mktemp`) and pass it via stdin. Quotes, backticks, and `$` in code excerpts break an inline heredoc, so don't use a heredoc. Contents of `$f`:
```json
{
  "state": "Cross-check of bot review comment triage for PR #<N>. Judge only from each question's code context.",
  "questions": {
    "tri_1": {
      "type": "choice",
      "instructions": "[bot comment] <author>: <gist>\n<path>:<line>\n```\n<relevant code excerpt>\n```\nHow should this comment be handled?",
      "criteria": {
        "Apply": "Valid defect within this PR's change scope — apply the fix",
        "Skip": "False positive or outside this PR's change scope — no code change",
        "Defer": "Verification inconclusive — revisit later, no guessing"
      }
    },
    "real_1": {
      "type": "noul",
      "instructions": "[bot comment] <author>: <gist>\n<path>:<line>\n```\n<relevant code excerpt>\n```\nIs this a real defect in the code shown (not a false positive)?"
    }
  }
}
```
```bash
python3 ~/.claude/skills/jev-scope/jev.py call < "$f"
```

Response: `{"answers":{"tri_1":{"choice":"Apply","probabilities":{..},"confidence":..},"real_1":{"noul":0..1}},"usage":..}`.
Only two skips are allowed: jev.py exits abnormally (no key / API error), or there are 0 comments to handle. In that case
print one line `Jev skipped — <reason>` and continue the normal flow (omit the Jev columns and ⚠ below).

### 4. Present to user

Show a table grouped by severity. Columns: `# | Severity | Scope (in/out) | Verdict (valid/false positive) | Evidence (facts checked / run results) | author | path:line | Gist | Suggestion (Apply/Skip/Defer)`. If the Jev cross-check ran, append `Jev handling (prob) | Defect prob | ⚠` columns next to the suggestion — **my verdict is primary**, Jev is for reference only.

**⚠ flag (a "take another look" marker):** add ⚠ to items where my suggestion differs from Jev's choice, or the defect probability (noul) < 0.4. The flag is only a caution signal; it does not change my verdict.

Ask for per-item disposition. Accept:
- `all as suggested` (apply each item's suggested disposition)
- `all apply` / `all skip` / `all defer`
- Per-item: `1=apply, 2=skip, 3=defer, ...`
- Korean equivalents are also accepted (e.g. `전부 추천대로`, `전부 반영` / `전부 스킵` / `전부 보류`, `1=반영, 2=스킵, 3=보류`) — Korean users type these.

Dispositions: **Apply** apply fix, **Skip** reply with rationale only, **Defer** reply marking for later, no edit.

### 5. Apply items marked Apply — single commit

Edit all Apply files. Stage + commit. Message format (from `~/.claude/CLAUDE.md`):

```
[fix]: {{JIRA_PROJECT_KEY}}-XXX Apply review feedback (High N / Medium N)

- <path>:<line> <short description>
- ...
```

- Extract `{{JIRA_PROJECT_KEY}}-XXX` from PR title; if absent, ask user.
- pre-commit hooks **must pass** — never `--no-verify`. Fix the root cause and commit again on failure.
- `git push` (never `--force`).

### 6. Reply under each original bot comment

Reply **in the existing thread** — use the original comment's id, do not open new top-level comments.

```bash
# Inline line-comment thread
gh api -X POST repos/{owner}/{repo}/pulls/<N>/comments/{COMMENT_ID}/replies -f body="<text>"
# Issue-level comment (no thread API) → post a new issue comment quoting it
gh api -X POST repos/{owner}/{repo}/issues/<N>/comments -f body="> @<author> <quoted gist>\n\n<text>"
```

Reply templates (write PR replies in the user's language):
- **Apply**: `Applied — {SHORT_SHA}.` + optional 1-line summary.
- **Skip (out of scope)**: `Not applying: this code is outside this PR's change scope. We'll handle it in a separate issue if needed.`
- **Skip (false positive)**: `Not applying. Direct verification shows this cannot occur: {repro/evidence — run result or code fact}.` (don't just contradict the bot's claim; present the evidence you checked yourself)
- **Defer**: `Decision deferred for now. Will revisit at {trigger/time}.`

### 7. Final summary to user

```
PR #<N> review response done (M bot comments handled)
✅ Applied N (1 commit: <SHA>) - <author> <path>:<line> ...
💬 Skipped N               - <path>:<line> — <reason: out of scope/false positive>
⏸ Deferred N               - <path>:<line> — <note>
🔎 Jev: ran (⚠ N) | skipped — <reason>
```

Then, to wrap up, offer the user the design-challenge review in **See also** below.

## See also

Triage only asks "is the bot comment right?". Whether the PR's **design decisions themselves** are good is a separate axis, and skipping it turns review into a rubber stamp. Once Step 7 is done, suggest the user run `/challenge-pr <N>` — 3-5 pointed "why did you do it this way?" challenge questions from a Toss senior engineer's perspective (questions only). The challenge logic belongs to that skill (`challenge-pr`), so don't reproduce it here.

## Guardrails (hard stops)

- Never `gh pr merge`, never `git reset --hard`.
- **No frontend edits** — FE repos (`{{GITHUB_ORG}}/{{FRONTEND_REPO_NAME}}`, `{{FRONTEND_REPO_NAME}}`) are owned by a separate agent. If a comment needs FE changes, mark Skip with that reason or update `docs/fe/` only.
- **No JWT issuance** in gw — verify-only.

## Dependencies

`gh` CLI (authenticated, `repo` scope + PR write), `git`. cwd must be the PR's target repo.

## Example

```
User: /review-feedback 12
→ PR #12 fetched (head=feat/{{JIRA_PROJECT_KEY}}-123-x, base=develop)
→ 9 bot comments found (gemini-code-assist 6, github-actions 3); 2 already replied → 7 actionable
→ independently verified each (read code + ran 2 quick `python -c` repros + 1 subagent traced all callers):
    • 3 CONFIRMED (real on this code)
    • 2 REFUTED (e.g. "Decimal >= float raises TypeError" → ran it, returns False, no error → false positive)
    • 2 out of scope (pre-existing code)
→ [table shown with Evidence + Suggestion]

User: all as suggested
→ 3 fixes applied → commit abc1234 → pushed
→ 7 replies posted in original threads (each citing the verification evidence)
→ to wrap up, suggests "Want a design-challenge review too, via /challenge-pr 12?"
→ Done
```
