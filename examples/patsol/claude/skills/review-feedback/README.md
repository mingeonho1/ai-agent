# review-feedback

A Claude Code skill that responds to **bot reviews already posted** on a PR (Gemini Code Assist, GitHub Action reviewers, CodeRabbit, etc.).

It doesn't run a new review. It fetches the comments someone (a bot) already left and:

1. Judges **whether each comment fits this PR's change scope** + **whether it's valid**
2. After user approval, handles **applied items as 1 commit and non-applied items as replies to the original comments**

> This is the companion skill to [`autofix-pr`](../autofix-pr/), where Claude starts with its own review. Use this one for PRs that already have bot reviews.

---

## 1. Prerequisites

| Item | Check command | Install/setup |
|---|---|---|
| Claude Code | `claude --version` | https://docs.claude.com/claude-code |
| `gh` CLI | `gh --version` | `brew install gh` |
| GitHub auth | `gh auth status` | `gh auth login` (scopes: `repo`, PR write) |
| `git` | `git --version` | System default |

> ❌ No external Claude GitHub App installation **needed**. The PR just needs bot reviews (Gemini/Action) on it.

---

## 2. Installation

Rendering the `patsol` example (`examples/patsol/` in the ai-agent repo) installs this skill to `~/.claude/skills/review-feedback/`, or copy the folder there yourself. Restart Claude Code after installation to enable the `/review-feedback` slash command.

> To use the design-challenge review in Step 8 (`/challenge-pr`), install the [`challenge-pr`](../challenge-pr/) skill as well.

---

## 3. Usage

```
/review-feedback 12
```

If the PR number is omitted, the open PR for the current branch is found automatically:

```
/review-feedback
```

### Steps (run automatically)

1. **Pre-checks** — PR state, head branch (abort if main/develop), working tree state
2. **Checkout & diff collection** — `gh pr checkout`, `gh pr diff`
3. **Collect existing bot comments** — scrapes all 3 surfaces: line comments + review summaries + issue comments
   - Keeps only bot/human reviewers and **excludes threads that already have a reply** (avoids duplicate responses)
4. **Independent verification + verdict** — bot reviewers run weaker models than this session, so they're **more likely to be wrong**. Don't take a comment's claim at face value: **reproduce/refute it directly against the code** (with `python -c`, tests, or subagents as needed), then classify as `in scope/out of scope` + `valid/false positive` + severity. The verification evidence (run results, code facts) is shown in the table
5. **User input** — choose [Apply / Skip / Defer] per item
6. **Code fixes + 1 commit push** — all Apply items handled together
7. **Post replies** — result reply **inside each original bot comment's thread**
8. **(Optional) Suggest a design-challenge review** — after triage, suggests running `/challenge-pr <N>`. A separate skill (questions only) that challenges **the PR's design decisions themselves**, not the bot comments, from a Toss senior engineer's perspective. A complementary axis that keeps triage from becoming a rubber stamp

Output follows the user's language (match the language the user writes in).

### User input format

When the verdict table appears, reply with one of:

```
all as suggested
all apply
all skip
all defer
1=apply, 2=skip, 3=defer, 4=apply, ...
```

Korean equivalents (`전부 추천대로`, `1=반영, 2=스킵, 3=보류`, ...) are also accepted.

### Verdict criteria

| Axis | Values | Meaning |
|---|---|---|
| **Scope** | in scope / out of scope | Does it point at code/behavior this PR touched, or ask for work on existing code / unrelated work? |
| **Validity** | valid / false positive | Is it a correct finding actually reproduced by **direct verification**, or a refuted bot misreading / already handled / misunderstanding of the codebase? (based on facts I checked, not the bot's claim) |
| **Severity** | High / Medium / Low | Security, data corruption (High) / functional bugs, conventions (Medium) / style (Low) |

> ⚠️ **Don't blindly trust bots.** Bot reviewers run weaker models than this session and are often wrong. Assign `valid` **only after confirming** it by direct reproduction, and `false positive` **only after refuting** it by showing it can't occur. If you can neither confirm nor refute it, **Defer** (no guessing).

Default suggestion (**after** verification):

- In scope + valid (confirmed) → **Apply**
- False positive (refuted) → **Skip** (with the evidence you checked)
- Out of scope → **Skip** (separate issue/PR recommended)
- Can't verify (neither confirmed nor refuted) → **Defer**

---

## 4. Example result

```
PR #12 review response done (7 bot comments handled)

✅ Applied 4 (1 commit: abc1234)
  - gemini-code-assist  service.py:25  SQL injection → parameter binding
  - gemini-code-assist  service.py:11  hardcoded secret → load from env
  - github-actions      handler.py:28  add missing await
  - gemini-code-assist  util.py:7      add None guard

💬 Skipped 2
  - legacy.py:140  request to refactor existing code — outside this PR's scope
  - service.py:35  "sync I/O" finding — that path is async, bot false positive

⏸ Deferred 1
  - config.py:16  cache TTL tuning — revisit after load testing
```

---

## 5. Guardrails (actions the skill blocks automatically)

- **Abort immediately if the PR head is `main`/`develop`** — no direct commits to protected branches
- **No new reviews** — respond to existing comments only (new reviews are `autofix-pr`)
- **No re-responding to threads that already have a reply** — prevents duplicates/spam
- **No arbitrary fixes for out-of-scope findings** — Skip unless the user explicitly marks Apply
- **No `gh pr merge`**, **no `git push --force`**, **no `git reset --hard`**
- **No `pre-commit --no-verify`** — on hook failure, fix the cause and make a new commit
- **No direct frontend code edits** — FE repos are owned by a separate agent
- **No adding JWT issuance/refresh logic** — gw only verifies
- **Never modify an item the user marked "Defer"**

---

## 6. Commit message convention

Apply items are automatically bundled into 1 commit in this format:

```
[fix]: {{JIRA_PROJECT_KEY}}-XXX Apply review feedback (High N / Medium N)

- service.py:25 SQL injection → parameter binding
- service.py:11 hardcoded secret → load from env
- ...
```

- If the PR title has a `{{JIRA_PROJECT_KEY}}-XXX` ticket it's used automatically; otherwise the user is asked

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `gh: command not found` | `gh` not installed | `brew install gh` |
| `HTTP 401` / `Bad credentials` | `gh` auth expired | `gh auth refresh` |
| `0 comments to handle` | Bot review not posted yet / all already replied | Re-run after the bot review completes |
| Reply not grouped into a thread | Issue-level comment (no thread API) | Falls back to a quoted reply automatically |
| Out of scope but applied | User explicitly marked Apply | Intended behavior — the default is Skip |

---

## 8. Relationship to other skills

| Skill | Role | Starting point |
|---|---|---|
| `autofix-pr` | Claude does a fresh review → classify → apply/reply | **Fresh review** |
| **review-feedback** | Judges scope of **existing bot reviews** → apply/reply | **Comments already posted** |

Typical flow:

1. Create PR → bot reviews (Gemini / GitHub Action) posted automatically
2. `/review-feedback <PR number>` → scope verdicts on bot reviews + apply + reply
3. (Optional) `/autofix-pr <PR number>` → an additional fresh Claude review

---

## 9. File layout

```
~/.claude/skills/review-feedback/
├── SKILL.md      # Skill definition (Claude reads and runs it directly)
└── README.md     # This document (usage guide for teammates)
```

The design-challenge review in Step 8 is handled by the separate [`challenge-pr`](../challenge-pr/) skill, which uses its `toss-senior-challenger.md` subagent.

The `description` in `SKILL.md`'s frontmatter is used by Claude to match and select skills, so don't shorten it carelessly.
