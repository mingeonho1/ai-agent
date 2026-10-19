# challenge-pr

A challenge-review skill that questions a PR's **design decisions** head-on from a Toss senior engineer's perspective. It's neither a bug hunt nor a bot-comment triage — it digs into "why was this decision made this way".

## Why a separate skill

`review-feedback` only judges **whether comments bots posted are correct** (validity check → apply/skip/defer → reply). But even when every bot comment is handled correctly, nobody asks **whether the PR's design itself is good**. This skill covers that axis. The two skills have different responsibilities, so they're kept separate, and the challenge logic is isolated in the `toss-senior-challenger` subagent so both can share it.

Running it right after `review-feedback` triage keeps the review from becoming a rubber stamp.

## 1. Prerequisites

- `gh` CLI authenticated (repo access)
- `git`
- The `toss-senior-challenger.md` subagent linked into `~/.claude/agents/`

## 2. Install

Rendering the `patsol` example (`examples/patsol/` in the ai-agent repo) installs this skill into `~/.claude/skills/challenge-pr/` and the `toss-senior-challenger` subagent into `~/.claude/agents/`.

## 3. Usage

```
/challenge-pr 12      # specify a PR number
/challenge-pr         # auto-find the current branch's open PR (if none, asks whether to proceed with the branch diff)
```

## 4. How it works

1. Get the target diff (read-only — no checkout, no edits)
2. The `toss-senior-challenger` subagent picks the 3-5 most contentious design decisions and writes strongly opposing questions
3. Show the question list to the user (PR and code unchanged)

Question format:

```
[label] path:line — <the decision being challenged>
  Why did you do it this way? <objection>
  (I'd probably have gone with <alternative>, because <why it's better>.)
```

Labels: `[question]` (confirm intent) / `[suggestion]` (better way) / `[nit]` / `[fyi]`

## 5. Principles

- **Questions only** — no code edits, commits, or PR comments (to apply, use `autofix-pr`/`review-feedback`)
- **No style nitpicks** — indentation, naming, and formatting are the linter's/CI's job. Only design, architecture, trade-offs, and business impact
- **Every objection needs an alternative** — objection without an alternative is a complaint
- **No padding the count** — if only 3 are worth raising, give 3

## 6. File layout

```
challenge-pr/
├── SKILL.md                    # skill definition
├── README.md                   # this document
└── toss-senior-challenger.md   # challenge-review subagent (linked into ~/.claude/agents/)
```
