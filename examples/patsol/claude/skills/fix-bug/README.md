# fix-bug

A standard pipeline that closes out a reported bug **through reproduction, verification, and git tracing** rather than guesswork. It proceeds in stages like `new-task`, and never stops except where user input is required.

## Usage

```
/fix-bug <bug description | {{JIRA_PROJECT_KEY}}-XXX | attachment path>
```

- Give it a `{{JIRA_PROJECT_KEY}}-XXX` and it fetches the ticket gist via the Atlassian MCP (if not connected, it asks for the gist/attachment).
- If the target is ambiguous, it asks only one or two questions before investigating.

## Flow

1. **Reproduce & understand** — check the attachment/error message, delegate code-location searches to subagents in parallel, reproduce the bug with real data.
2. **impact-check + decide-approach in parallel** — spawn two subagents at once to get the impact scope (call sites, contracts, latent bugs, tests) and the fix approach (compare options, then commit to option 1).
3. **Pre-fix verification** — simulate the recommendation against real data before implementing.
4. **Minimal fix + end-to-end re-verification** — call the actual function/endpoint directly to confirm the contract is satisfied, the error is resolved, and there's no regression.
5. **git tracing** — confirm the bug-introducing commit, author, and time with `git log -S`/`blame`/`-L`. If dead code is suspected, present the evidence, get the user's confirmation, and split it into a separate commit (don't bundle it into the bug fix).
6. **Clean commit** — don't mix in unrelated uncommitted changes; stage only the fixed files. Put the ticket number in the commit/PR message only.
7. **Push + PR** — confirm the specified base branch (hotfix/develop, etc.), then create it. The body includes problem / cause / changes / verification table / impact scope.

## Points where it stops to ask

- When the target is ambiguous / when a real trade-off remains / when the commit/push/PR base branch isn't specified / handling unrelated uncommitted changes.

## Related skills

- [impact-check](../impact-check/), [decide-approach](../decide-approach/) — parallel orchestration in stage 2.
- [jira-sync](../jira-sync/) — sync ticket status after the fix is merged.
