Apply code review results for the current branch. Do NOT spawn subagents.

Respond in the user's language (match the language the user writes in).

## Step 1 — Identify current task
Run: git branch --show-current
Extract Jira ticket ID from branch name (e.g. f-{{JIRA_PROJECT_KEY}}-123/... → {{JIRA_PROJECT_KEY}}-123).

## Step 2 — Get review feedback
Look for review output already in this conversation (from your review step).
If not found, ask the user to paste it before continuing.

## Step 3 — Evaluate each review item
For every item in the review, decide APPLY or SKIP:

**APPLY criteria** (all must be true):
- Security bug or data integrity issue, OR
- Clear correctness fix that touches ≤ 5 lines
- Does not require changes to > 2 files

**SKIP criteria** (any one is enough):
- Refactoring or abstraction
- Style / naming preference
- Architecture change
- Touches > 2 files
- "Would be nice" / non-critical

Default bias: **SKIP**. When in doubt, skip.

## Step 4 — Apply APPLY items
Make the minimal possible change for each accepted item.
One item at a time. Smallest diff. Do not clean up surrounding code.

## Step 5 — Update Notion page
Run: source {{AGENT_RULES_ENV}}

Find the Notion page:
  POST https://api.notion.com/v1/search
  Bearer ${NOTION_API_TOKEN}, Notion-Version: 2022-06-28
  body: { "query": "{{JIRA_PROJECT_KEY}}-<ID>" }

Append a "Code Review" section via PATCH /v1/blocks/<page_id>/children with a table:
  Columns: Item | Decision (apply/skip) | Reason

## Report to user
List what was applied and what was skipped, one line each with reason.
