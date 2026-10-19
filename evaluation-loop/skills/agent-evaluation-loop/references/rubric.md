# Default evaluation rubric

This rubric is this repository's uncalibrated default, not an official standard. Until you confirm that grader results match owner-judged pass/fail examples, treat it as provisional and do not estimate calibration statistics. You may add required criteria to fit the requirements before starting work, but after the baseline do not change the dimensions, weights, anchors, or pass criteria for the same `evaluation_id`. If a change is needed, bump the rubric version and create a new baseline.

| Dimension | Weight | 0 | 1 | 2 | 3 | 4 |
| --- | ---: | --- | --- | --- | --- | --- |
| Intent (`intent`) | 30 | Unrelated to the request | Most core requirements missing | Partly met, important gaps | Requirements met, minor limits | Requirements and boundaries fully met |
| Correctness (`correctness`) | 30 | Does not work / critical defect | Main path fails | Partly works / significant defect | Main path correct, minor risk | Confirmed with evidence down to edge conditions |
| Verification (`verification`) | 20 | No verification | Low relevance or hides failures | Only part of the core path checked | Relevant verification passes, limits stated | Failure paths and regressions sufficiently checked |
| Clarity (`clarity`) | 10 | Cannot be understood or reviewed | Confusing structure and explanation | Needs extra interpretation | Change and rationale are clear | Concise, traceable, no ambiguity |
| Efficiency (`efficiency`) | 10 | Unnecessary cost/scope dominates | Major duplication/excess | Some duplication/excess | Appropriate scope and cost | Solved with minimal scope, reusably |

The score is the sum of each `score / 4 * weight`. If even one dimension has insufficient evidence, do not estimate its score; leave it `null`, and the total is also `null`.

## Default gates

- Total score 85 or higher
- Every dimension 3 or higher
- All required criteria are `true`
- No unresolved `high` or `medium` findings
- Required model/effort matches the actual review model/effort
- Fresh, non-inherited review context confirmed

Reproducible fatal/high defects and required-criteria failures block PASS regardless of the total. Do not pass by weakening the rubric or tests. Model judgments require clear anchors and evidence, and deterministic checks are combined separately. Do not claim scores not calibrated against human judgment as absolute quality figures.

## Sources

- [OpenAI Evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices): clear rubrics and anchors, pass/fail gates, strong judges, calibration against human judgment, position and verbosity bias
- [OpenAI Graders](https://developers.openai.com/api/docs/guides/graders): combining deterministic and model graders, checking for reward hacking
- [Trustworthy third-party evaluations](https://openai.com/index/trustworthy-third-party-evaluations-foundations/): recording model, harness, and budget, verifying the claim itself, preventing broken criteria and reward hacking
- [Anthropic, Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents): outcome evidence, clear weighted/binary/mixed grading, grader calibration, regression cases
- [Anthropic, Harness design for long-running apps](https://www.anthropic.com/engineering/harness-design-long-running-apps): score anchor examples, separating implementation and evaluation roles, iterative improvement
- The OpenAI Evals dashboard and API go read-only on 2026-10-31 and are scheduled to shut down on 2026-11-30 ([notice](https://developers.openai.com/api/docs/deprecations)). This loop does not call that API and only borrows the methodology; the successor tool is [Datasets](https://developers.openai.com/api/docs/guides/evaluation-getting-started).
