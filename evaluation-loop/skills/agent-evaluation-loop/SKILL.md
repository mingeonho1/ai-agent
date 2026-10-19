---
name: agent-evaluation-loop
description: Use when implementation quality needs repeated evaluation or evidence-based stop conditions for improvement. Validates and aggregates independent review scorecards against a fixed rubric and manages up to 3 rounds of improvement records.
---

# Agent Evaluation Loop

The main orchestrator uses this skill. The builder and independent reviewer run in their existing roles, and `ai-loop` records the review scorecard and proposes only one next fix or evidence addition. `ai-loop` does not call sub-agents, modify source, or create scores.

## Order

1. Before a new baseline, the planner or `ai-loop` reads the project's current lessons that match this scope and conditions and turns them into required criteria for the current task. Then fix the original requirements, required criteria, and the dimensions, weights, anchors, and pass criteria from [rubric.md](references/rubric.md). To change them, restart with a new `evaluation_id` and a round-1 baseline.
2. After the builder produces a candidate and freezes verification evidence, run the top-tier independent reviewer in a fresh, non-inherited context. Give the reviewer only the original requirements, required criteria, the actual file paths of the fixed rubric/checklist, and the current candidate and evidence; do not show previous scores or iteration records.
3. The reviewer returns `0..4` or `null` per dimension, evidence, required-criteria results, and findings. Mark a finding `needs_evidence` only when evidence essential to a rubric or required-criteria judgment is missing. Do not put optional hypotheses or further exploration ideas in this status. Leave unknown scores as `null` and treat them as `NEEDS_EVIDENCE`.
4. `ai-loop` builds the input JSON and validates, aggregates, and appends the record with the tool below. The tool does not call an LLM or the network.

```sh
python3 <agent-evaluation-loop-dir>/scripts/evaluate.py --input round.json --history evaluation-history.jsonl
```

5. If not PASS, choose only one evidence-based fix or evidence addition from the record's `decision` and `fix_targets`. Retrying to raise numbers, loosening pass criteria, and removing tests are forbidden.
6. Evaluate at most 3 rounds, including baseline. If 2 consecutive rounds bring no defect resolution or new evidence, stop immediately with `STOP_NOT_COMPLETE`. If the limit is used up without passing, do not report it as complete.
7. Promote defects confirmed by independent review and fixed into regression tests or evaluation cases with a minimal reproduction input and expected result, and also record them in the project lessons below. If this goes beyond the current task scope, record it as a follow-up item; do not change the same evaluation's fixed rubric.

## Project lessons

The default path is the project's `evals/lessons/`, and the task contract can set another in-project path. Lessons use the [lesson.template.md](templates/lesson.template.md) format and record only these facts.

- Scope and trigger conditions
- Verified failure and evidence
- Fix principle
- Minimal reproduction steps and expected result
- `current` or `superseded` status and validity conditions

Do not record scores, the approval process, conversations, or private reasoning. Lessons stay within that task/project and are not copied into global personal memory. At a new baseline, pick only the relevant `current` lessons and turn them into current required checks. Give the new independent reviewer only the current requirements, the fixed checks built this way, and the current candidate and evidence; do not pass the lesson records themselves or past scores and iteration history.

## Pass and records

Default PASS requires all of: total score 85 or higher, every known dimension 3 or higher, all required criteria passing, no unresolved high/medium findings, and confirmed review isolation and model routing. Even with a high total, a required-criteria failure or an unresolved high/medium finding blocks passing.

Each JSONL record keeps the task/candidate/evidence fingerprints, rubric version, actual model and effort, evidence, raw scores, decision, fix targets, and measured tokens, run time, and cost. Use `null` for unmeasured values. Private reasoning is not collected. The same round of the same evaluation is rejected rather than overwritten.

Use [round-input.template.json](templates/round-input.template.json) for the input structure and [reviewer-scorecard.md](templates/reviewer-scorecard.md) for the review output format. [synthetic-baseline.json](examples/synthetic-baseline.json) is a synthetic example to illustrate behavior, not a measured result.
