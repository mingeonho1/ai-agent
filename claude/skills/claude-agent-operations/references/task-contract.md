# Task contract and handoff

For each task, set a unique ID and an absolute path for the handoff file. The main agent is
the only writer of this file and tells every worker the path on first delegation.
Do not load another task's file by guessing from modification time or name.
When resuming without a path, first confirm the task named in the current conversation.

## Delegation contract

```text
Task ID:
Requirements / deliverables:
Completion criteria:
Absolute paths of input files and evidence:
Assigned agent / question or command / working directory:
Owned files and allowed artifact paths:
Dependencies / start condition:
Verification command / expected observation:
Stop condition:
Results to return and evidence file paths:
Absolute path of the handoff file:
```

If a worker needs an edit outside its ownership, it tells the main agent. Command artifacts
also count toward file ownership. Do not run implementation, build output, and review on the
same file at the same time.

## State the main agent keeps

```text
Task ID / current request:
Current step / next action:
Settled decisions and constraints:
Owned files per worker / running or not:
Completed changes / changes still needed:
Current diff and changed file paths:
Verification command / when run / result / evidence path:
Review target state / reviewer result / open items:
```

Do not omit staged, unstaged, or new files from the diff. When reviewing a commit range,
record the base and target commits; for uncommitted changes, freeze the change list and
content at review time. Confirm the evidence came from the actual review target state.

## Reviewer input

Pass the original requirements and completion criteria, required criteria, the actual file paths of the fixed evaluation rubric/checklist, the current diff, current files, and test commands with results.
Do not pass approval conclusions, the intended answer, the builder's explanations, the main
conversation's or past reviewers' reasoning, or previous rounds' scores and iteration records. Use absolute paths so the reviewer can check directly.
The reviewer starts in a fresh context without `memory` or preloaded skills.

The main agent asks for verification instead of asking for PASS. The reviewer returns one of
PASS, REJECT, or NEEDS_EVIDENCE with its evidence. After fixes or evidence additions, a
new reviewer judges the latest state again.

## Evaluation round contract

When using repeated evaluation, set an in-project lessons path. The default is
`evals/lessons/`. Before a new baseline, the planner or ai-loop reads lessons whose scope and
conditions match and whose status is current, and turns them into current required checks. Then
fix the rubric and required criteria and make ai-loop the single writer of the per-task
evaluation record path. Give ai-loop the absolute paths of the installed evaluation tool, rubric,
and per-task ledger. Each round's new reviewer returns raw scores and evidence per dimension,
required-criteria results, and findings with severity and confidence kept separate.
Pass ai-loop only this scorecard and the fingerprint, the actual model/effort, and measured token/run info.
Do not record private conversations or private reasoning. In the next round, pass the original
requirements and the same rubric, and hide previous scores.

For confirmed and fixed defects, record in the project lessons: scope and conditions, the verified
failure, the fix principle, reproduction and expected result, evidence, and current or superseded status.
Do not include scores or the approval process, and do not copy them into global personal memory. Pass a new
reviewer not the lesson file but only the current fixed checks derived from it.
