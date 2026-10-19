---
name: codex-agent-operations
description: Use for substantive work that needs parallel investigation, code changes, tests, and independent review. Splits implementation and verification across Codex's model-specific planner, builder, runner, and independent reviewer.
---

# Codex Agent Operations

Select this skill automatically per task and use only the roles needed. You do not need to call every role, but substantive work with meaningful changes to code, config, or deliverables goes through independent review by `ai_reviewer` before completion.

## Roles

| Role | Model | Effort | Responsibility |
| --- | --- | --- | --- |
| `ai_planner` | `gpt-6-astra` | high | Design decisions that need judgment and completion criteria |
| `ai_builder` | `gpt-6-sol` | medium | Own small patches and directly related tests |
| `ai_runner` | `gpt-6-luna` | high | Run bounded commands and report observations |
| `ai_reviewer` | `gpt-6-astra` | xhigh | Independent review against the original requirements |
| `ai_loop` | `gpt-6-sol` | medium | Record independent scorecards and propose the next improvement action |

The planner and reviewer are read-only. The runner has workspace write access to produce test output but does not modify source. Only the builder writes assigned source files. If a designated model is unavailable, do not silently substitute a lighter model; report it.

## Operating rules

1. Before dispatch, set the deliverable, original requirements, acceptance criteria, input paths, writer per file, and stop condition. For the concrete contract, read [task-contract.md](references/task-contract.md).
2. Independent files or tasks may run in parallel. Keep only one writer per file.
3. At most 3 workers run concurrently, including the reviewer. You can also enforce this in config with `[agents] max_concurrent_threads_per_session = 3` (see the repository's `codex/config.example.toml`). No role spawns further sub-agents.
4. Between roles, hand off only the task path and the needed facts, briefly, instead of the full conversation or global state.
5. After the builder's files and related verification are stable, bring in a fresh, non-inherited review instance. In Codex CLI, create a new thread with `spawn_agent` for every review, and do not resume a previous reviewer thread with `resume_agent` or `send_input`. When using Responses API multi-agent directly, do not inherit the conversation via `fork_turns`. If there is no way to confirm a fresh, non-inherited context, report independent verification as incomplete and do not pass the work.
6. Limit reviewer input to the original requirements, acceptance criteria, current diff, current files, and verification evidence. Do not pass or inherit the builder's or orchestrator's conversation, reasoning, or conclusions.
7. After fixing review findings, still do not resume the previous reviewer thread with `resume_agent`. A new review instance under the same isolation re-reviews only the changed scope and its impact. Finish when all acceptance criteria are met.

## Evaluation-driven improvement

For work that needs repeated evaluation, also use the installed `$agent-evaluation-loop`. Before implementation, fix the original requirements, required criteria, and dimensions, weights, anchors, and pass criteria. Each round, run `ai_reviewer` as a new, non-inherited instance; give it the original requirements and the actual file paths of the fixed rubric/checklist, but do not show previous scores or iteration records.

Pass only the reviewer's structured scorecard to `ai_loop` to aggregate and record deterministically. `ai_loop` proposes only one evidence-based next fix or evidence addition, and does not call sub-agents, modify source, or create scores. At most 3 rounds including baseline; if 2 consecutive rounds bring no defect resolution or new evidence, stop with `STOP_NOT_COMPLETE`. Retrying to raise numbers, loosening criteria, or removing tests is not allowed. A rubric change starts a new version with a new baseline.

Use Codex's default agent lifecycle and file contracts. Do not additionally require Codex hooks (`~/.codex/hooks.json`). Do not add API settings or experimental flags by guesswork.

For a personal install, put this skill folder in `~/.agents/skills/codex-agent-operations` and the role TOMLs in `${CODEX_HOME:-~/.codex}/agents`.
