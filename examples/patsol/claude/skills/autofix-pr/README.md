# autofix-pr

A Claude Code skill that fetches a PR locally, has Claude review it directly, classifies findings by priority, and — after user approval — handles **applied items as a code commit and non-applied items as replies to the review comments**.

Unlike `/review-feedback`, which responds to existing bot reviews, this one **starts from a fresh review**.

---

## 1. Prerequisites

| Item | Check command | Install/setup |
|---|---|---|
| Claude Code | `claude --version` | https://docs.claude.com/claude-code |
| `gh` CLI | `gh --version` | `brew install gh` (macOS) / `apt install gh` |
| GitHub auth | `gh auth status` | `gh auth login` (required scopes: `repo`, `read:org`) |
| `git` | `git --version` | System default |

> ❌ No external Claude GitHub App installation **needed**.

---

## 2. Installation

Rendering the `patsol` example (`examples/patsol/` in the ai-agent repo) installs this skill to `~/.claude/skills/autofix-pr/`, or copy the folder there yourself. Restart Claude Code after installation to enable the `/autofix-pr` slash command.

---

## 3. Usage

### Basic invocation

```
/autofix-pr 12
```

If the PR number is omitted, the open PR for the current branch is found automatically:

```
/autofix-pr
```

### Steps (run automatically)

1. **Pre-checks** — PR state, head branch (abort if main/develop), working tree state
2. **Checkout & diff collection** — `gh pr checkout`, `gh pr diff`
3. **Fresh Claude review** — analyzed along 5 axes: security / bugs / performance / conventions / tests
4. **Present classification** — High/Medium/Low priority table
5. **User input** — choose [Apply / Skip / Defer] per item
6. **Post PR review** — each finding attached as a line comment
7. **Code fixes + 1 commit push** — all Apply items handled together
8. **Post replies** — result on each line comment (Apply SHA / Skip reason / Defer note)

Output follows the user's language (match the language the user writes in).

### User input format

When the classification table appears, reply with one of:

```
all apply
all skip
all defer
1=apply, 2=apply, 3=apply, 4=apply, 5=apply, 6=defer, 7=skip
```

Korean equivalents (`전부 반영`, `1=반영, 2=스킵, 3=보류`, ...) are also accepted.

### Classification criteria

| Severity | Criteria | Examples |
|---|---|---|
| **High** | Security, data corruption, outage-causing, major convention violations | Hardcoded secret, SQL injection, JWT issuance in gw |
| **Medium** | Functional bugs, normal convention violations, perf regressions | Missing await, unhandled None, sync I/O |
| **Low** | Style, naming, comments, nice-to-have | Docstring format, variable names |

---

## 4. Example result

```
PR #12 done

✅ Applied 3 (1 commit: abc1234)
  - review_demo.py:25 Fix SQL injection
  - review_demo.py:11 Remove hardcoded secret
  - review_demo.py:28 Add await

💬 Skipped 2 (replies posted)
  - review_demo.py:1 docstring — no project convention for it
  - review_demo.py:35 unhandled None — test dummy

⏸ Deferred 1
  - review_demo.py:16 JWT issuance — intentional for the demo, to be discussed separately
```

---

## 5. Guardrails (actions the skill blocks automatically)

- **Abort immediately if the PR head is `main`/`develop`** — no direct commits to protected branches
- **No `gh pr merge`** — apply/respond only; merging is the user's call
- **No `git push --force`**, no `git reset --hard`
- **No `pre-commit --no-verify`** — on hook failure, fix the cause and make a new commit
- **No direct frontend code edits** — FE repos are owned by a separate agent
- **No adding JWT issuance/refresh logic** — gw only verifies
- **Never modify an item the user marked "Defer"**

---

## 6. Commit message convention

Apply items are automatically bundled into 1 commit in this format:

```
[fix]: {{JIRA_PROJECT_KEY}}-XXX Apply PR review feedback (High N / Medium N)

- review_demo.py:25 Fix SQL injection → parameter binding
- review_demo.py:11 Remove hardcoded secret → load from env
- ...
```

- If the PR title has a `{{JIRA_PROJECT_KEY}}-XXX` ticket, it's used automatically
- Otherwise Claude asks the user for the ticket number

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `gh: command not found` | `gh` not installed | `brew install gh` |
| `HTTP 401` / `Bad credentials` | `gh` auth expired | `gh auth refresh` or `gh auth login` |
| `the requested branch is protected` | head is a protected branch | Aborted per the skill's guardrail — expected behavior |
| Dirty working tree warning | Uncommitted changes exist | `git stash` or commit, then retry |
| Classification result is empty | Nothing to review in the diff | Expected — the skill only handles fresh reviews |
| Replies not grouped into a thread | Posting line comments in step 4 failed | Check PR permissions (write required) |

---

## 8. Relationship to other skills

| Skill | Role |
|---|---|
| **autofix-pr** | Starts **from a fresh review** → classify → apply/reply |
| `review-feedback` | Responds to **existing bot/human review comments** (apply or answer) |
| `pr-review-toolkit:review-pr` | Analysis only (no code-fix/reply automation) |

You can use both on the same PR. Typical flow:

1. Create PR → bot reviews (Gemini/CodeRabbit, etc.) posted automatically
2. `/autofix-pr <PR number>` → fresh Claude review + apply
3. `/review-feedback <PR number>` → respond to the existing bot reviews too

---

## 9. File layout

```
~/.claude/skills/autofix-pr/
├── SKILL.md      # Skill definition (Claude reads and runs it directly)
└── README.md     # This document (usage guide for teammates)
```

The `description` field in `SKILL.md`'s frontmatter is used by Claude to match and select skills, so don't shorten it carelessly.

---

## 10. Changes / contributing

To change the skill's behavior, edit `SKILL.md` and open a PR to the team skill repo. Main change points:

- **Classification criteria** — the High/Medium/Low definitions in section 2
- **Commit convention** — the commit message template in section 5
- **Reply tone** — the body templates in section 6
- **Guardrails** — add project-specific forbidden actions

You may need to restart the `claude` CLI after editing.
