# impact-check

A skill that gives a read-only briefing of a task's impact scope **before** you touch any code.

## When to use
- When you want to confirm, before starting work, "if I fix this, what else gets affected?"
- When you want to check the impact on other backends/lambdas/services before changing a function/endpoint/event.

## Usage
```
/impact-check <task description | {{JIRA_PROJECT_KEY}}-XXX | function/file>
```
- Give a `{{JIRA_PROJECT_KEY}}-XXX` and it fetches the ticket gist via the Atlassian MCP (if not connected, enter the gist directly).
- If the target is ambiguous, it first asks one or two questions.

## Output
A briefing in the form `Problem / Cause / Proposed change (minimal change) / What it resolves / Impact scope (impacted · safe) / Needs checking (external repos)`. Respond in the user's language (match the language the user writes in).

## Operating principles
- It is **read-only**. It only investigates — no editing/committing/merging. Implementation is a separate, explicit step.
- It never assumes consumers outside cwd (other repos) are "safe"; it always marks them "needs checking".
- It delegates broad searches to the Explore subagent to conserve the main context.

## Dependencies
`git`, ripgrep/grep, the repo at cwd. Checking out sibling repos locally makes cross-service checks more accurate.
