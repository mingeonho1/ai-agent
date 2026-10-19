# Using scores as an improvement record

Official docs checked: 2026-09-29. Evaluation in this repo is an operating tool for finding weaknesses in output. It is not a benchmark that proves general model performance or token savings.

## What we took from official sources

| Source · section | Applied as |
| --- | --- |
| [OpenAI Evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices), Design your eval process / LLM-as-a-judge | Define per-task criteria first with observable score examples. Calibrate against human-judged examples and use scores together with pass conditions. |
| [OpenAI Graders](https://developers.openai.com/api/docs/guides/graders), Grader hacking | Separate model judgment from deterministic computation. Weakening checks or criteria to raise a score does not count as improvement. |
| [OpenAI Trace grading](https://developers.openai.com/api/docs/guides/trace-grading), structured scores and labels | Record the failed step, check, and evidence path to find what to fix. This does not adopt the API or full-transcript collection. |
| [OpenAI independent evaluation guidance](https://openai.com/index/trustworthy-third-party-evaluations-foundations/), 2026-05-29, harness / validity / reporting | Record which claim was tested and the model, effort, tools, and budget. Check for broken tasks, evaluation bypasses, and changed comparison conditions. |
| [Anthropic Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents), 2026-01-09 | Check actual outcomes rather than the agent's claim of completion. Combine deterministic checks with judgment-based evaluation and keep failures as regression checks. |
| [Anthropic Harness design](https://www.anthropic.com/engineering/harness-design-long-running-apps), 2026-03-24, evaluator / iteration | Separate building from evaluation. Use evaluation examples and per-dimension thresholds, and compare iteration results. The article's run counts and performance numbers were not adopted. |
| [OpenAI Evals deprecation notice](https://developers.openai.com/api/docs/deprecations) | The Evals dashboard and API go read-only on 2026-10-31 and shut down on 2026-11-30. This repo does not call that API and only borrows the method; the successor is [Datasets](https://developers.openai.com/api/docs/guides/evaluation-getting-started). |
| [OpenAI Agent evals](https://developers.openai.com/api/docs/guides/agent-evals) | Borrows the view of checking an agent run's final state and trajectory. This repo's loop aggregates with local scripts and does not call this API. |

## Platform-specific application

Claude uses the `model`, `effort`, and `tools` of Markdown named subagents. The evaluator is a fresh Fable 5.1 xhigh; recording and improvement proposals use Opus 5.5 medium. No per-call evaluation hook is added beyond the existing optional `SessionStart` hook.

Codex uses TOML role settings. A fresh Astra xhigh evaluates against fixed criteria, and Sol medium handles records and the next fix scope. Collecting run evidence can go to Luna high. No separate runtime hook is used for loop control.

On both platforms the loop agent does not create other agents itself. The main agent keeps file ownership and calls fixes and re-evaluations. The scoring script calls no network or model, so running the script alone does not mean a real model review happened.

## Rules that hold across iterations

- Criteria and weights are fixed before the task starts. If requirements change, create a new evaluation version and do not compare directly with earlier scores.
- Re-evaluation reads the original requirements and current evidence in a fresh context. Previous scores and PASS verdicts are not shown first.
- A total score does not offset a failed required check or a confirmed serious defect. Missing evidence is kept as its own status.
- A longer model explanation or a higher score alone is not recorded as improvement. Confirm which failure was resolved.
- Stop on pass. When the default limits are hit — 3 runs including the first evaluation, or 2 consecutive stalls — report the remaining problems. Hitting a limit is not success.
- Record model, effort, install mode (`standard`/`eco`), criteria version, output identifier, and run evidence. If tokens, cost, or time were not measured, leave them `null`. Private reasoning is not collected.
- Lessons from verified failures are kept in the project's `evals/lessons/` or the path set in the contract. The next task's planning/loop owner checks applicability and validity and adds them as new checks; the reviewer receives only the current criteria and evidence.

Weights, pass bar, iteration limits, and hiding previous scores are this repo's operating choices, not settings enforced by the official docs. Example records are fictional data that show the format and are not presented as real quality gains or model run results.
