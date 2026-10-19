---
name: decide-approach
description: Decide WHICH approach to take for a task and justify it — not just follow the order. Weighs performance/cost/security/maintainability across the viable options and commits to one. Clear best → take it; real trade-off → break the tie with the operator's fixed stance, consistently. (Distinct from impact-check, which maps the blast radius of an already-chosen change.) Proposal only, no code until approved. Respond in the user's language (match the language the user writes in).
---

# decide-approach

Turn "do X" into "here's how I'd do X, and why." Analyze the task, commit to a direction, state the rationale — applying a **consistent stance** so recommendations don't drift run to run.

## Stance profile
The operator's defaults. Applied **only when a real trade-off exists** — if one option is strictly best, take it and say so. (These values are subjective; each user retunes them — see README.)
1. **Priority: performance & scalability** — comparable options → favor better latency/throughput/scaling headroom, even at some added complexity.
2. **Change scope: minimal change (pinpoint)** — smallest sound change for the requested problem; deeper refactors are noted as optional follow-ups, not bundled.
3. **Adopting new tech: case-by-case** — adopt a new lib/pattern only when the benefit is clear; else use what the team already runs. State which side this case lands on.

## Input
`/decide-approach <task>` — what's being asked. If the goal is ambiguous, ask one or two questions first.

## Flow

### 1. Restate the ask
One line: the request and its success criteria.

### 2. Weigh the options
Identify the 2-3 viable approaches. For each, weigh only the dimensions that matter here: performance/scalability, cost, security, maintainability, change scope. Don't pad with irrelevant dimensions.

### 3. Decide
- Clear winner → recommend it, name why it dominates.
- Real trade-off → apply the stance profile **in order** and say which rule broke the tie.

### 4. Report
```
## Request
## Options
- A: … (pros / cons)
- B: … (pros / cons)
## Conclusion: <chosen direction>
## Rationale
- <why it's best / which trade-off was broken by which rule>
- Applied rule (only when there's a trade-off): performance first / minimal change / tech adoption (adopt or not + reason)
## Next step
- <one line on the stage to enter after the direction is confirmed — e.g. confirm impact scope with impact-check, then implement. Don't write concrete implementation steps here>
```
End by asking to proceed.

## Guardrails
- **Don't blindly comply** — if the requested approach has a meaningful downside, say so and offer the better path.
- **Proposal only** — no Edit/Write/commit until the direction is approved.
- **Stance yields to hard requirements and explicit user instructions** — note the override.
- Keep it tight — decisive conclusion, no exhaustive matrices.

## Dependencies
None beyond repo context. Pairs with `impact-check` **after** the direction is chosen — run impact-check before implementation, not before this skill.

## Example
```
User: /decide-approach add caching to the read API
→ Request: reduce GET /reports response latency
→ Options: A) in-memory LRU (fast & simple, inconsistent across instances) B) Redis (consistent & scalable, adds one piece of infra)
→ Conclusion: Redis (session Redis is already running → not a new dependency)
→ Rationale: performance & scalability first + case-by-case adoption (reuses existing infra, so low cost), a minimal change adding only the cache key
→ Next step: once confirmed, check impact scope with impact-check, then implement
→ Proceed?
```
