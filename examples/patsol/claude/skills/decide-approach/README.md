# decide-approach

A skill that, instead of just doing a task as told, **decides which direction to take first and gives the rationale**. It weighs performance/cost/security/maintainability, commits to one direction, and when trade-offs diverge, decides consistently by a fixed set of criteria.

## When to use
- When you get "do A" and, before touching anything, want to lay out "here's how I'll do it and here's why".
- When there are several options and you want to apply consistent criteria so the judgment doesn't waver each time.

## Usage
```
/decide-approach <task>
```
A proposal in the form `Request / Options / Conclusion / Rationale / How to proceed`. Respond in the user's language (match the language the user writes in). It **only proposes** and writes no code before approval.

## Stance (decision criteria) — these are subjective, so adapt them for yourself
The three lines of `Stance profile` in SKILL.md are **the author's personal defaults**. They apply only when a real trade-off exists; when there's an obvious best, it just takes that. Edit them directly in SKILL.md to match your own leanings.

Current defaults:
1. **Priority: performance & scalability** — when options are comparable, the side with better latency/throughput/scaling headroom
2. **Change scope: minimal change (pinpoint)** — only the requested problem, minimally; deep refactoring as a separate follow-up
3. **Adopting new tech: case-by-case** — adopt only when the benefit is clear, otherwise use the existing approach

> At runtime only SKILL.md is loaded, so the applied values themselves live in SKILL.md. This README only explains "that those values are subjective and how to change them".

## Good to use alongside
After deciding the direction, checking that change's impact scope with `impact-check` follows naturally.
