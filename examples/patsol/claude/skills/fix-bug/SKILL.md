---
name: fix-bug
description: End-to-end bug-fix pipeline — reproduce, run impact-check + decide-approach in parallel (subagents), validate the chosen fix on real data, implement the minimal change, verify end-to-end, trace the bug's git origin (flag any dead code for the user, don't bundle its removal), then make a clean commit and PR. Mirrors new-task's staged flow but for fixing reported bugs. Respond in the user's language (match the language the user writes in).
---

# fix-bug

A standard pipeline that closes out a reported bug through **reproduction, verification, and git tracing** rather than guesswork. It proceeds in stages like `new-task`, stopping only where user input is required. Respond in the user's language (match the language the user writes in).

## Input

`/fix-bug <bug description | {{JIRA_PROJECT_KEY}}-XXX | attachment path>` — a symptom description, a Jira key, or an attachment (Excel/image/log) path.
- e.g. `/fix-bug {{JIRA_PROJECT_KEY}}-123`, `/fix-bug 500 error on /api/users ~/Downloads/error.log`, `/fix-bug createdAt field missing from search response`
- If a `{{JIRA_PROJECT_KEY}}-XXX` key is given, fetch the ticket gist via the Atlassian MCP. If the MCP isn't connected, ask the user for the gist/attachment.
- If the target is ambiguous, ask only one or two clarifying questions before investigating.

## Core principles

- **No guessing**: "no problem / no impact" is proven with git history and real-data verification.
- **Minimal change**: the smallest sound fix for the requested problem. Mention any deeper refactor only as an optional follow-up.
- **Clean commit**: never mix in unrelated uncommitted changes from the working tree.

## Stages (in order, no stopping except where blocked)

### 1. Reproduce & understand
- Start with the attached file/image/error message. Error text (e.g. `ValueError: ...`) is a direct clue.
- Delegate code-location searches to subagents in parallel. Get the key function, the response-serialization point, and the data-parsing point as `file:line`.
- When possible, **reproduce** the bug with real data to pin down the cause first.

### 2. impact-check + decide-approach parallel orchestration
- Spawn **two subagents at once in the same message**:
  - one from the `/impact-check` angle — an exhaustive sweep of call sites, response-contract dependencies, latent bugs of the same pattern, test coverage, and "contracts you must not touch / regression risk."
  - one from the `/decide-approach` angle — compare the fix options, then commit to option 1 + rationale.
- At the top of each subagent prompt, state the facts confirmed in stage 1 (cause, file:line, reproduction result) and make clear they are not up for re-investigation, to prevent duplicate work.

### 3. Pre-fix verification
- **Before implementing**, run the decide-approach recommendation against real data first — write a verification script that carries only the patch logic to the **scratchpad directory** and run it (without modifying the source).
- If it **passes**, go to stage 4. If it **fails**, don't implement; revisit the decide-approach decision, or if stuck, report the result to the user and stop.

### 4. Minimal fix + end-to-end re-verification
- Apply the minimal fix per the recommendation.
- Verify by calling the actual function/endpoint directly: required response keys / contract satisfied, the original error resolved, no regression. Report the result in a table.
- The **bootstrap method** varies per project, so don't guess — grep first: check the test/run commands and the settings module in `pytest.ini`/`manage.py`/`Makefile`/`README`/`package.json`, then start it that way.

### 5. git tracing (when, who, whether dead code)
- Confirm the bug-introducing commit, author, and time with `git log -S'<needle>'` (pickaxe) / `git blame`.
- If a ruff/format commit obscures blame, find the real author/time with `git log -L <start>,<end>:<file>`.
- If legacy code is **suspected to be dead code** (= there is no actual path in the entire history where it would match/run), confirm the producer/call path with grep and present the evidence. **Removal itself is not this skill's responsibility** — keep it separate from the bug fix, get the user's confirmation, and handle it in a separate commit if they agree.

### 6. Completion gate (Jev, required — skip only when the call fails)
Just before committing, cross-check the fix's completeness once more with a Jev `noul` judgment. **Claude's own end-to-end verification (stage 4) is primary**; this is an auxiliary gate. **Always run `jev.py`** — don't skip it even if the fix looks simple. Don't pre-judge whether the key exists from `$TYPESAFE_API_KEY` (the key may live in the `~/.config/jev/api_key` file, and if it's absent jev.py tells you by exiting non-zero).
- Put in the state: the bug report (symptom + expected behavior), the reproduction result (**before fix / after fix**), `git diff --stat` + the key hunk.
- Send the four questions at once — `root` (does it fix the root cause, not just the symptom), `minimal` (is it a minimal change with no unrelated edits), `repro` (does the after-fix reproduction show the expected behavior), `callers` (could it break callers outside the diff — **inverted meaning**: higher is worse). The JSON piped via stdin:
  ```json
  {
    "state": "<bug report (symptom + expected) · reproduction before/after fix · git diff --stat + key hunk>",
    "questions": {
      "root":    {"type": "noul", "instructions": "Does this diff fix the reported bug's root cause rather than just its symptom?", "criteria": {"true": "Addresses the underlying cause of the reported bug.", "false": "Only hides or patches the symptom."}},
      "minimal": {"type": "noul", "instructions": "Is the change minimal and focused, with no unrelated edits?", "criteria": {"true": "Only what the fix needs is changed.", "false": "Includes unrelated edits or scope creep."}},
      "repro":   {"type": "noul", "instructions": "Does the after-fix reproduction show the expected behavior?", "criteria": {"true": "After the fix the reproduction matches the expected result.", "false": "After the fix it still fails or diverges."}},
      "callers": {"type": "noul", "instructions": "Could this change break callers or code paths outside the diff?", "criteria": {"true": "Risks breaking callers/behavior outside the diff.", "false": "Callers outside the diff are unaffected."}}
    }
  }
  ```
  Run: write the JSON above to a temp file `$f` (Write tool recommended, or `mktemp`), then `python3 ~/.claude/skills/jev-scope/jev.py call < "$f"` → `{"answers":{"root":{"noul":..},...}}`. Quotes, backticks, and `$` in the state's diff/hunk break an inline heredoc/echo, so pass it via a temp file.
- Gate: if any of `root`/`minimal`/`repro` is **< 0.6**, or `callers` is **> 0.5** → **stop**, show the probabilities, and ask the user whether to continue. Otherwise print the probabilities in one line and proceed to stage 7:
  `Jev completion gate: root=0.87 minimal=0.91 repro=0.88 callers=0.12 → pass`
- Skipping is allowed only on a jev.py non-zero exit (no key / API error). In that case, print one line `Jev skipped — <reason>` so it isn't mistaken for a pass, then proceed with the existing flow as-is. The stage 2 impact-check already runs Jev scope, so don't repeat the scope computation here.

### 7. Clean commit
- Check for unrelated uncommitted changes with `git status`, then commit after `git add`-ing **only the files you fixed**.
- Put the ticket number in the commit message only (never in code comments). Follow the project commit style (`[fix]: {{JIRA_PROJECT_KEY}}-XXXX ...`). Branch convention `f-{{JIRA_PROJECT_KEY}}-XXXX/desc`.
- If a pre-commit hook fails, don't bypass it — fix the root cause and commit again.

### 8. Push + PR
- Confirm the user-specified base branch (hotfix/develop, etc.), then push & `gh pr create`.
- Include problem / cause (+ dead-code tracing result) / changes / verification table / impact scope in the PR body.
- In the final report (so it stays in the parent report even when run as a subagent), leave one line with the completion-gate result: `🔎 Jev: pass root=.. minimal=.. repro=.. callers=.. | stopped | skipped — <reason>`

## Points to stop and ask
- When the target is ambiguous (before stage 1)
- When a real trade-off remains that not even the operator's stance can settle in decide-approach
- When the completion gate (stage 6) hits a threshold (`root`/`minimal`/`repro` < 0.6 or `callers` > 0.5)
- Commit/push/PR base branch — confirm if not explicitly specified
- How to handle unrelated uncommitted changes
