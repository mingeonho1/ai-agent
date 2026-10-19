---
name: jev-scope
description: Rank which repo files are relevant to a coding task using the Jev API (TypeSafe "System One" decision model) — the "code scope" shortlist of files to read or edit. Use when the user asks "작업 범위 파일 찾아줘", "어떤 파일 건드려야 해", "jev로 범위", or runs /jev-scope. Jev output is a hint to verify with grep/read, not truth. Respond in the user's language (match the language the user writes in).
---

# jev-scope

Given a coding task, ask Jev (TypeSafe System One) which files are in scope — the files you would need to edit or closely read. Jev scores each file independently; the result is a ranked shortlist, **a hint to verify, never the final answer**.

Requires a Jev key: env `TYPESAFE_API_KEY`, else `~/.config/jev/api_key` (`chmod 600`). If missing, the script prints how to set it — relay that and stop.

## Input

`/jev-scope <task | {{JIRA_PROJECT_KEY}}-XXX>` — a task description or a Jira key.
- For a `{{JIRA_PROJECT_KEY}}-XXX` key, fetch the ticket gist via the Atlassian MCP and use it as the task text. If the MCP isn't connected, ask the user to paste the gist.
- Default repo is cwd; pass `--repo DIR` for another.

## Flow

### 1. Get the task text
A sentence or two describing what to implement. Resolve a `{{JIRA_PROJECT_KEY}}-XXX` key to its ticket gist first.

### 2. Run the script
```
python3 ~/.claude/skills/jev-scope/jev.py scope --task "<task>" [--repo DIR] [--top 15] [--min 0.3]
```
Output is an aligned table, highest probability first:
```
0.92  src/auth/token.py
0.78  src/gw/verify.py
# 234 candidates · 12,345 input tokens
```
Add `--json` for machine-readable output — it also reports `unscored` (candidate files that got no score) and `failed_batches` (count of batches that errored). If `failed_batches` > 0 the ranking may be missing files, so grep the `unscored` paths to be sure. Lower `--min` to widen recall; raise `--top` to see more. Calls are effectively free, so prefer recall.

### 3. Verify the top files
Read only the top-ranked files. **Confirm with grep/read before relying on the ranking** — Jev scores from a path + symbol descriptor, so it can miss or over-rate a file. Grep the task's key symbols/routes across the repo to catch anything Jev ranked low.

### 4. Report the scope
```
## Work scope (Jev + verification)
- `path/to/file.py` — <why it needs touching, verification result>
- `path/to/other.ts` — <reason>

## Surprisingly low-ranked files (found via grep)
- `path/missed.py` — Jev score was low but included in scope due to a <symbol/route> reference
```
State clearly that the ranking is a hint you verified, and list any file grep found that Jev under-ranked. If nothing was missed, drop that section.

## Generic helper: `jev.py call`

`jev.py call` is a thin primitive other skills can reuse. It reads `{"state":..., "questions":{...}}` from stdin, adds `"model":"jev-latest"`, and prints the response. Question ids are your own keys (not sent to the model).

Write the request JSON to a temp file (the Write tool, or `mktemp`) and pipe it in via stdin — `call` reads stdin. Prefer a file over an inline heredoc: quotes, backticks and `$` in embedded code excerpts/diffs break the heredoc and its JSON escaping.
```
# write the request JSON to "$f" (Write tool / mktemp), then:
python3 ~/.claude/skills/jev-scope/jev.py call < "$f"
```
Three question types:
```
# noul (yes/no probability, 0..1): {"type":"noul","instructions":"<yes/no question>"}
# choice: {"type":"choice","instructions":...,"criteria":{"optA":"desc",...}}
# score: {"type":"score","instructions":...,"criteria":["lvl1","lvl2",...]}  (2–10 levels)
```
Answers: noul → `{"noul":0..1}`; choice → `{"choice":..,"probabilities":..,"confidence":..}`; score → `{"score":..,"legend":..,"probabilities":..,"confidence":..}`. Jev is text-only (no generation); retries 429/529 automatically.

## Dependencies

`git`, Python 3 (stdlib only). Jev key as above. Optional: Atlassian MCP for `{{JIRA_PROJECT_KEY}}-XXX` lookup, `JEV_BASE_URL` to point at a gateway.

## Example
```
User: /jev-scope {{JIRA_PROJECT_KEY}}-123 extend login token expiry
→ (fetch {{JIRA_PROJECT_KEY}}-123 gist via Atlassian MCP)
→ python3 ~/.claude/skills/jev-scope/jev.py scope --task "access token expiry 30m→2h"
→ 0.94 auth/token.py  0.71 gw/verify.py  ...
→ (read top files, grep issue_access_token)
→ ## Work scope: auth/token.py — exp constant, gw/verify.py — expiry check (verified)
→ ## Surprisingly low: config/settings.py — Jev 0.2, holds the token TTL default
```
