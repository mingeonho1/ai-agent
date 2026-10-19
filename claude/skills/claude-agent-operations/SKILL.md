---
name: claude-agent-operations
description: Coordinates planning, implementation, command execution, and independent review as separate roles in Claude Code. Use when the user asks for this role setup or when a task needs parallel delegation of independent work.
---

# Claude Agent Operations

Run this skill in the main conversation. The main agent manages the task contract,
file ownership, and result synthesis, and delegates by naming the custom agents below.

| Role | Agent | Model | Effort |
| --- | --- | --- | --- |
| Planning and judgment | ai-planner | Claude Fable 5.1 (`claude-fable-5-1`) | high |
| Implementation and edits | ai-builder | Claude Opus 5.5 (`claude-opus-5-5`) | medium |
| Lookups and commands | ai-runner | Claude Sonnet 5.5 (`claude-sonnet-5-5`) | medium |
| Independent review | ai-reviewer | Claude Fable 5.1 (`claude-fable-5-1`) | xhigh |
| Evaluation records and next action | ai-loop | Claude Opus 5.5 (`claude-opus-5-5`) | medium |

To run the main agent on Fable 5.1 high as well, start the session with that model and effort.
Each agent's `model` and `effort` follow its installed definition. If an agent is missing or
its designated model cannot run, stop that step and report the cause. Do not substitute a
general agent or another model, and do not treat a review that never ran as passed.
If you need to check environment variables or versions, read [runtime-support.md](references/runtime-support.md).

## Flow

1. Set the goal, completion criteria, input paths, and owned files. On first delegation and
   when resuming, use the contract and handoff formats in [task-contract.md](references/task-contract.md).
2. Send only the parts that need judgment to ai-planner. Do not add a separate planning call
   for simple work. The main agent finalizes the contract and sets dependency order.
3. Give ai-builder responsibility for edits and ai-runner responsibility for commands and output.
   Run only independent work in parallel, with at most 3 concurrent workers.
   Each file has one writer. Agents do not re-delegate.
   This concurrency limit and the no-re-delegation rule are this harness's operating rules.
4. Workers return only key results, evidence paths, and open items as a summary within 1–2k tokens.
   The main agent updates the contract and handoff. Do not pass long logs or full conversation history to the next agent.
5. After implementation and related verification are done and all writers have stopped, freeze the
   current change list and diff. Without Git, provide before/after files and changed paths. ai-runner
   may save the diff and command results to designated evidence files.
6. **Always run ai-reviewer as a new instance.** Do not resume a previous reviewer or use the
   `fork` type that inherits conversation history. Pass only the requirements, the frozen diff,
   current file paths, and test evidence. Exclude the builder's explanations and reasoning.
7. On REJECT, ai-builder fixes only the flagged scope and reruns related verification.
   On NEEDS_EVIDENCE, obtain the needed evidence. In both cases, stabilize files and then hand the
   review to a new reviewer. If the same failure repeats, do not retry endlessly; report the
   unresolved cause and the decision needed.
8. After confirming PASS on the latest change state and the completion criteria, report the
   deliverables, verification results, and remaining limits. If files change after a review,
   that review no longer counts as evidence of completion.

## Evaluation-driven improvement

For work that needs repeated evaluation, also use the installed `$agent-evaluation-loop`.
Of the four official loop exit gates (in-prompt checks, `/goal`, Stop hook,
verification subagent), this corresponds to the "verification subagent": a new reviewer
judges so the agent that did the work does not grade itself. `/goal` and the Stop hook are
optional (source: https://code.claude.com/docs/en/best-practices).
Before implementation, fix the original requirements, required criteria, and dimensions, weights,
anchors, and pass criteria.
Each round, run ai-reviewer as a new, non-inherited instance; give it the original requirements and
the actual file paths of the fixed rubric/checklist, but do not show previous scores or iteration
records. Pass only the reviewer's structured scorecard to ai-loop to aggregate and record
deterministically; ai-loop proposes only one evidence-based next fix or evidence addition.
ai-loop does not call agents, modify source, or create scores.

At most 3 rounds including baseline; if 2 consecutive rounds bring no defect resolution or new
evidence, stop with `STOP_NOT_COMPLETE`. Retrying to raise numbers, loosening pass criteria, or
removing tests is not allowed. A rubric change starts a new version with a new baseline.

Do not give the read-only reviewer Bash, Edit, Write, or Agent. For independence, the reviewer
does not preload skills or memory.
Since it reviews changes in the same checkout, automatic worktree creation is not needed.
Existing user rules and permission scope stay in place; this skill itself does not authorize
push, PRs, or external transmission.
