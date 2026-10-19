New task setup pipeline. Run all phases in order without stopping except where user input is required.

Task description: $ARGUMENTS

Respond in the user's language (match the language the user writes in).

The mechanical work (Jira ticket + Notion page + git branch) is handled by a deterministic script — you only generate the *content*. Do NOT make raw Jira/Notion API calls or read the JIRA/NOTION/GIT rule files; the templates and rules you need are inlined below.

---

## Phase 1 — Clarification (ask BEFORE creating anything)

Analyze `$ARGUMENTS` and the conversation so far. Identify genuinely ambiguous points that would change the ticket content or technical approach.

Use `AskUserQuestion` to ask 2–3 targeted questions. Good topics:
- Scope boundary (how far this ticket goes)
- Technical approach options (when several methods are possible)
- Connected systems / dependencies (impact on other apps or modules)
- Fixed constraints (performance, backward compatibility, etc.)

Skip questions already obvious from the task or codebase conventions. If nothing is genuinely ambiguous, skip this phase entirely and proceed. Wait for answers before continuing.

---

## Phase 2 — Generate content (you do this directly — no subagent)

Using the full conversation context + clarification answers, write a content JSON to `/tmp/new-task-content.json`. Write all content in the user's language (match the language the user writes in). Do NOT invent features, metrics, or scope — convert the request into accurate backend/architecture terms only.

### Required JSON shape
```json
{
  "summary": "Jira title (one concise line)",
  "jira_wiki": "<the Jira template below, in wiki markup>",
  "jira_comment": "1 line core goal + 1 line technical concern",
  "label": "backend",
  "notion_title": "may be the same as summary",
  "notion_md": "<the Notion template below, in markdown>",
  "work_type": ["기능 개발"],
  "branch_slug": "short-kebab-description",
  "branch_type": "feature"
}
```
- `label`: exactly one of `backend` or `frontend` (by the work's domain).
- `branch_type`: normally `feature`; `hotfix` for an urgent production fix.
- `branch_slug`: English kebab-case summary of the work.
- `work_type`: fill it when clear, omit the key entirely when ambiguous. Values must match the Notion "작업 유형" multi-select options verbatim, which are Korean in this workspace (e.g. `기능 개발` = feature, `버그 수정` = bug fix, `리팩터링` = refactoring).

### Jira body (`jira_wiki`) — wiki markup
```
h3. Background (Why)
- The problem and its technical/operational risk

h3. Work (What)
- Only the work the user requested

h3. Technical approach (How)
- Implementation principles, stability, transactions, type safety, etc.

h3. OKR linkage
- Quote the key wording of KR [name] verbatim and explain which outcome metric this work directly connects to
- Describe concretely the technical path by which this scope contributes to that KR
- Use quantitative figures as-is if given; otherwise state the target direction, e.g. "aim for 0% error rate / ensure 100% data integrity / block the risk"
- At least 3 lines
```
Rules: use the actual KR wording if provided; otherwise describe the target direction. No fake numbers. Do not put assignee/sprint/team/label in the body — the script sets them automatically.

### Notion body (`notion_md`) — markdown, STAR/OKR structure
```
### [Task name]
- One-line summary:

#### 1. Background and purpose
- Existing problem
- Technical/business reasons the work is needed

#### 2. Work performed
- Core logic to implement
- API, DB, architecture changes

#### 3. Considerations and technical decisions
- Alternatives / rationale for the choice / edge cases

#### 4. Results and quantitative gains
- Quantitative results / qualitative results

#### 5. 1–3 line summary for performance records
- A summary ready to drop into a resume or performance review
```
(The start date, URL, and work-type properties are set automatically by the script.)

---

## Phase 2.5 — Repo routing (Jev)

Decide which repo this ticket targets, so the branch/worktree (Phase 3) and plan/coding (Phase 4–5) run against the right repo. Record the result as `[TARGET REPO]` (an absolute repo path). **The default for `[TARGET REPO]` is `{{BACKEND_REPO_PATH}}`** — used when Claude has no signal at all to choose from (or when this phase is skipped).

Principle: **Claude judges the repo first; Jev is only a cross-check — add a ⚠ warning only when the two differ.** If a key exists, the Jev call in this phase must run; if it is skipped or fails, leave a one-line reason. The key may live in the `~/.config/jev/api_key` file rather than the `$TYPESAFE_API_KEY` env var, so do not pre-judge key presence from the env var — actually call `jev.py` and judge by its result (or abnormal exit).

1. **Decide the target repo yourself first** from `$ARGUMENTS` / Phase 1 answers / ticket content — this is your working pick for `[TARGET REPO]`. If there is no signal at all, pick the default `{{BACKEND_REPO_NAME}}`.
2. Discover the sibling repos — sibling `{{REPO_PREFIX}}-*` git repos in the parent of cwd. Match **case-insensitively** (the default repos are `{{BACKEND_REPO_NAME}}`/`{{FRONTEND_REPO_NAME}}`, which a case-sensitive `{{REPO_PREFIX}}-*` glob may skip), so use `find -iname`; the `.git` **directory** check excludes worktrees (whose `.git` is a file):
   ```bash
   find "$(dirname "$PWD")" -maxdepth 1 -type d -iname '{{REPO_PREFIX}}-*' | while read -r d; do
     [ -d "$d/.git" ] && echo "$d"
   done
   ```
   For each discovered repo, gather a one-line description **at runtime** — the first non-empty line(s) of its `README*`, else its `package.json`/`pyproject.toml` name. Do NOT hardcode these descriptions.
3. **The Jev `choice` call is mandatory (cross-check).** It may be skipped only when the user **explicitly** named the repo in `$ARGUMENTS` / Phase 1 answers, and even then print one line: `Jev repo routing skipped — user-specified`. Build a Jev `choice` whose options are the discovered repo names plus a `none` option, with the ticket summary + description (from Phase 2) in the state:
   ```bash
   python3 ~/.claude/skills/jev-scope/jev.py call <<'JSON'
   {
     "state": "Ticket summary: <summary>\nDescription: <key summary of the Jira body>",
     "questions": {
       "repo": {
         "type": "choice",
         "instructions": "Which repo is the target for this ticket's work?",
         "criteria": {
           "{{REPO_PREFIX}}-back": "<README first line / package name>",
           "{{REPO_PREFIX}}-front": "<README first line / package name>",
           "none": "Matches none of the repos above, or unclear"
         }
       }
     }
   }
   JSON
   ```
   The answer is `{"choice":..,"probabilities":{repo:prob,..},"confidence":..}`. Jev is only a **cross-check** of the choice you already made in step 1:
   - Jev matches Claude's pick → keep it.
   - Jev picks a **different** repo that is not `none` (mismatch) → print one line `⚠ Jev repo mismatch — Claude: <A> / Jev: <B>(p=..)` and **continue with Claude's pick** (do not stop for user confirmation).
   - Jev returns `none` / low confidence → keep Claude's pick.
   If `jev.py` exits abnormally (no key, error, non-zero exit), print one line `Jev skipped — <reason>` and keep Claude's pick.
   `[TARGET REPO]` is always **Claude's final pick**, never Jev's raw output.

The chosen repo is the target repo/worktree: its path is `[TARGET REPO]`, used as the Project root in Phase 4 and where coding happens in Phase 5.

---

## Phase 3 — Execute (one script call)

Run (pass the Phase 2.5 decision as `--repo`; omit it to fall back to the configured default repo):
```
python3 {{CLAUDE_DIR}}/example-profiles/patsol/scripts/new-task.py /tmp/new-task-content.json --repo [TARGET REPO]
```
The script discovers the active sprint, creates the Jira ticket + comment, creates the Notion page, and cuts the branch — all from cached IDs, never pushing. It prints a JSON result line then:
```
JIRA: {{JIRA_PROJECT_KEY}}-XXX | https://{{JIRA_SITE}}/browse/{{JIRA_PROJECT_KEY}}-XXX
NOTION: <url>
BRANCH: f-{{JIRA_PROJECT_KEY}}-XXX/<slug>
```
Display those 3 lines to the user. If the script exits with `ERROR:`, read the message, fix the content JSON (or report a config issue), and re-run. To preview without creating anything, add `--dry-run`.

---

## Phase 4 — Plan elaboration (subagent: opus)

Spawn ONE subagent (`model: opus`) with the prompt below. Fill in [PLACEHOLDERS] from earlier phases.

```
You are a senior backend architect. Produce a detailed PLAN.md for the task below.

## Task
[TASK DESCRIPTION]

## Clarifications from developer
[PASTE PHASE 1 ANSWERS VERBATIM]

## Constraints
- Project root: [TARGET REPO]
- Branch already checked out: [BRANCH NAME FROM PHASE 3]
- Architecture: follow the layering convention in CLAUDE.md at project root
- Write all content in the user's language (match the language the user writes in)
- Do NOT write code, create PRs, or git push

## Your job
1. Get a Jev file-scope hint first: run
   `python3 ~/.claude/skills/jev-scope/jev.py scope --task "[TASK DESCRIPTION]" --repo [TARGET REPO] --top 15 --json`
   and treat the ranked paths as a shortlist of where to look — a hint to verify, not the answer. If a key exists, this scope call must run; on abnormal exit (no key / error), print one line `Jev scope skipped — <reason>` and proceed. Then read only what's relevant: CLAUDE.md at project root, and the app dir(s) this task touches — verifying the Jev shortlist with targeted grep/glob rather than scanning the whole repo.
2. Identify exactly which files change. For each: file path / reason for change (one line) / add·modify·delete.
3. Write the plan to [TARGET REPO]/PLAN.md:

# [Task Title] Implementation Plan
## Goal
One-line summary.
## Changed files
| File | Change | Reason |
|------|--------|--------|
## Logic flow
Step-by-step description + pseudocode to show the structure.
## DTO / Serializer changes
Fields added/modified/removed and why.
## DB / query changes
New queries, indexes, whether a migration is needed.
## Edge cases & caveats
Easy-to-miss cases, transaction boundaries, type mismatches, etc.
## Work order (recommended)
1. ...

Return only: PLAN_WRITTEN: [TARGET REPO]/PLAN.md
```

After it returns, tell the user: "PLAN.md written. Starting the coding work now."

---

## Phase 5 — Start coding

Read PLAN.md and implement immediately, following its "Work order". Apply all CLAUDE.md rules. When done, say "Coding done." and proceed to Phase 6.

---

## Phase 6 — Review (conditional — only for PR work)

Use the `autofix-pr` skill for review. `autofix-pr` operates on an **already-opened PR**, so run this phase **only if the original task instruction included "create/push a PR"**.

**Condition check** — did the original instruction ask to open a PR? (e.g. "open a PR", "make the PR too", "push and create a PR"; Korean triggers such as "PR 올려줘", "PR까지 만들어줘", "push하고 PR 생성해줘" count too)

### If the condition is met

**Completion check gate (Jev noul) — once, right before the final commit.** Ask one noul question per acceptance criterion of the ticket (the items under `Work (What)` in the Jira body) to check whether this diff satisfies each one. Put the list of acceptance criteria + `git diff --stat` output + a summary of the key hunks in the state:
```bash
python3 ~/.claude/skills/jev-scope/jev.py call <<'JSON'
{
  "state": "Acceptance criteria:\n- <criterion 1>\n- <criterion 2>\n\ngit diff --stat:\n<stat output>\n\nKey changes:\n- <main hunk summary>",
  "questions": {
    "c1": {"type": "noul", "instructions": "Does this diff satisfy the following acceptance criterion: <criterion 1>"},
    "c2": {"type": "noul", "instructions": "Does this diff satisfy the following acceptance criterion: <criterion 2>"}
  }
}
JSON
```
Each answer is `{"noul":0..1}`. **If any criterion is below 0.6, stop**, show the user which criteria fall short, and ask whether to continue. This gate is only an extra safeguard — Claude's own verification still runs as usual. If a key exists, this Jev call must run; if it fails (no key / error), print one line `Jev skipped — <reason>` and continue with the steps below as-is.

1. Commit the changes — commit format `[prefix]: title` (feat/fix/refactor/test/docs/design/format), atomic, debug code removed. If a pre-commit hook fails, never use `--no-verify`; fix the cause and recommit.
2. Push the branch, then create the PR with `gh pr create` (base: develop). Never `--force` push.
3. Call `/autofix-pr <PR number>` with the created PR number — it handles fresh review → per-item apply/skip/defer → single commit → push → line comments.

### If the condition is not met
Do **none** of code review, commit, push, or PR creation. Tell the user "Coding done. No PR was requested, so the review/PR steps were skipped. Say the word if you want it opened." and stop.
