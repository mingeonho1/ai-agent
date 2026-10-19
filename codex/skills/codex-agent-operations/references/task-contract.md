# Task contract

Before calling multiple roles, create a per-task contract in the following format. Each contract describes only one task path, not global progress.

```text
Goal: [one-sentence outcome]
Original requirements: [reviewable original text or an exact summary]
Acceptance criteria: [observable conditions]
Inputs: [needed files, diff, facts]
Assigned role: [ai_planner | ai_builder | ai_runner | ai_reviewer]
Owned paths: [paths that may be read or written]
Work: [bounded judgment, implementation, command, or review]
Output: [patch, verification result, or list of findings]
Stop: [completion or blocking condition to report]
```

## Split and join

- Different files, independent investigations, and independent verifications can be assigned in parallel.
- Do not give the same file to two writers. The runner and reviewer are not source writers.
- At most 3 roles can run concurrently, and the reviewer counts toward this number.
- Join parallel results once and reflect them in the acceptance criteria. Send only conflicting judgments back to the planner.

## Review contract

Right before completing substantive work, send the stabilized files to a fresh, non-inherited `ai_reviewer` instance. In Codex CLI, create a new thread with `spawn_agent` for every review, and do not resume a previous reviewer thread with `resume_agent` or `send_input`. When using Responses API multi-agent directly, do not inherit the conversation via `fork_turns`. If you cannot confirm a fresh, non-inherited context, report independent verification as incomplete and do not mark the work complete.

```text
Original requirements: [original text or exact summary]
Acceptance criteria: [completion conditions]
Fixed evaluation rubric/checklist files: [actual file paths and version when using the evaluation loop]
Current diff: [review target]
Current files: [final-state paths]
Verification evidence: [commands and results]
Request: report bugs, regressions, omissions, and wrong assumptions with impact, evidence, and path
```

Do not include or inherit the builder's or orchestrator's conversation, reasoning, or conclusions, or previous scores and iteration records. After fixing findings, do not resume the previous reviewer thread with `resume_agent`; use yet another fresh, non-inherited review instance. Re-reviews also get the original requirements, acceptance criteria, and the same fixed rubric, along with the changed diff, affected current files, and updated verification evidence. Limit re-review scope to the fixes and their impact. When the designated reviewer model is unavailable, do not silently substitute a lighter model.

## Evaluation round contract

When using the evaluation loop, set an in-project lessons path. The default is `evals/lessons/`. Before a new baseline, the planner or `ai_loop` reads lessons whose scope and conditions match and whose status is `current`, and turns them into current required checks. Then fix the required criteria and rubric and make `ai_loop` the single writer of the per-task JSONL record. Give `ai_loop` the absolute paths of the installed evaluation tool, rubric, and per-task ledger. Each round's new reviewer returns raw scores and evidence per dimension, required-criteria results, and findings with severity and confidence kept separate. Pass `ai_loop` only this scorecard, the task/candidate/evidence fingerprints, the actual model/effort, and measured token/run info. Do not record private conversations or private reasoning. In the next round, pass the original requirements and the actual file paths of the same rubric, and hide previous scores.

For confirmed and fixed defects, record in the project lessons: scope and conditions, the verified failure, the fix principle, reproduction and expected result, evidence, and `current` or `superseded` status. Do not include scores or the approval process, and do not copy them into global personal memory. Pass a new reviewer not the lesson file but only the current fixed checks derived from it.

## Handoff

```text
Task path: [path]
Result: [decision, change, or observation]
Verification: [if applicable]
Open items: [none, or one specific item]
```
