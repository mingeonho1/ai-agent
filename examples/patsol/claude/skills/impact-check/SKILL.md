---
name: impact-check
description: Before writing any code, produce a read-only briefing for a task — restate the exact problem, pinpoint what will change and why, state what the change resolves, and map the blast radius (every other backend/lambda/service that calls the affected function and whether it is impacted). Investigation only, no edits. Respond in the user's language (match the language the user writes in).
---

# impact-check

Pre-work briefing. Given a task, make the user understand **what** is changing and **what it ripples into** before a single line is written. Read-only — never edits, commits, or runs mutating commands.

## Input

`/impact-check <task | {{JIRA_PROJECT_KEY}}-XXX | function/file>` — a task description, a Jira key, or a symbol/path.
- If given a `{{JIRA_PROJECT_KEY}}-XXX` key, fetch the ticket gist via the Atlassian MCP; if the MCP isn't connected, ask the user to paste the gist instead.
- If the target is ambiguous, ask one or two clarifying questions before investigating.

## Flow

### 1. Frame the problem
Restate the problem in 1-2 lines and confirm understanding — the precise symptom and the expected behavior.

### 2. Locate the target
Find the function/endpoint/module to change. Read it in full plus its immediate collaborators. Use Glob/Grep — never read whole trees. If the target can't be pinned down (typo, deleted symbol, wrong key), stop and ask — don't guess.

**Always run `python3 ~/.claude/skills/jev-scope/jev.py scope --task "<task>"` first** — even when the target looks obvious — to get a ranked shortlist, then read those files first. Treat the output as a hint to verify with grep/read, not truth. Don't pre-judge key presence from `$TYPESAFE_API_KEY`: the key may live in the `~/.config/jev/api_key` file, and if it's missing jev.py exits non-zero to tell you. Skip only on jev.py non-zero exit (no key / API error); then print `Jev skipped — <reason>` and continue with grep/read as usual.

### 3. Pinpoint the change
The approach is assumed already chosen. If it isn't, stop and route the user to `decide-approach` first — don't weigh alternatives here. Cite the chosen change, locate exactly where it lands (`path:line`), and state what it resolves.

### 4. Map the blast radius
Find every consumer of the affected symbol/route/event:
- **In-repo**: grep the symbol, route path, event/topic name, exported names. List each call site as `path:line`.
- **Cross-service**: other backends, lambdas, queues (SQS/SNS), shared contracts/schemas — these often live in other repos. Search the current tree for references and known integration points; for anything outside cwd, **flag it as "needs checking"** rather than assuming it is safe.
- For wide searches, delegate to the Explore subagent to keep this context lean.

Classify each consumer: **impacted / safe** with a one-line reason (signature/behavior/contract change → impacted).

### 5. Brief the user
```
## Problem
## Cause
## Proposed change (the change to apply)
## What this change resolves
## Impact scope
- Impacted: <path:line> — <reason>
- Safe:     <path:line> — <reason>
## Needs checking (outside cwd / external repos)
- <consumer> — manual check needed
🔎 Jev scope: used (N candidates) | skipped — <reason>
```
End by asking whether to proceed to implementation.

## Dependencies
`git`, ripgrep/grep, repo at cwd. Optional: sibling service repos checked out locally for cross-service verification.

## Example
```
User: /impact-check {{JIRA_PROJECT_KEY}}-123 extend login token expiry
→ Problem: access token 30m → too short, frequent re-logins
→ Proposed change: auth/token.py issue_access_token() exp 30m→2h (1 line)
→ Impact scope: gw/verify.py:88 expiry check — safe, refresh logic — safe
→ Needs checking: other-service (separate repo) token verification — manual check
→ Proceed?
```
