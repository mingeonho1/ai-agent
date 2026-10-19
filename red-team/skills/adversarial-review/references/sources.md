# Evidence and scope

Reference check date: 2026-09-29. Below are review techniques taken from maintained official and primary sources. This skill does not install those frameworks, and it is not an official skill or an officially endorsed implementation.

## Anthropic: agent evaluation

- [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents), 2026-01-09: check the final state rather than verbal completion claims, calibrate model grading against human judgment, and watch regression evals and grading bypasses together. That is why this skill requires actual results, test evidence, and falsifiable criteria.
- [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps), 2026-03-24: referenced for separating implementer and evaluator roles, concrete rubric criteria, and a design that limits costly iterations. The article's iteration counts and budgets are the example's defaults, not obligations of this skill.

## Inspect Petri and Bloom

- [Inspect Petri](https://github.com/meridianlabs-ai/inspect_petri) separates auditor, target, and judge and grades transcripts with a consistent rubric. The [results docs](https://meridianlabs-ai.github.io/inspect_petri/using/results.html) tie judgment evidence to specific messages and advise not to mistake a failed audit for a conclusion about the target.
- Petri moved from `safety-research/petri` to [meridianlabs-ai/inspect_petri](https://github.com/meridianlabs-ai/inspect_petri). The current release in the [changelog](https://github.com/meridianlabs-ai/inspect_petri/blob/main/CHANGELOG.md) is 3.1.0, 2026-07-22.
- Petri's proven scope is AI behavior auditing. Do not treat it as evidence of performance for general code or product design review. This skill borrows only the techniques of role isolation and evidence linking.
- [Bloom repository](https://github.com/safety-research/bloom) and [Anthropic's introduction](https://www.anthropic.com/research/bloom), 2025-12-19: the idea of evaluating the same behavior across realistic, varied scenarios is applied to counterexample design. Do not call it a tool newly released in 2026.

## Risk rating and evaluation reporting

- [OWASP Risk Rating Methodology](https://community.owasp.org/OWASP_Risk_Rating_Methodology): referenced for the principle of splitting risk into likelihood and impact and fitting it to the organization's business context. This skill's high/medium/low definitions are its own 3-level impact classification, not an official unified OWASP scale.
- [OpenAI: A shared playbook for trustworthy third party evaluations](https://openai.com/index/trustworthy-third-party-evaluations-foundations/), 2026-05-29: make the claim under test explicit, report the model, harness, tools, and budget, and check for broken evaluation conditions such as reward hacking, wrong answer keys, ambiguous criteria, and missing files.
- [OpenAI: Red teaming](https://developers.openai.com/api/docs/guides/red-teaming): cites the distinction that evals check whether a system behaves as intended, while red teaming checks how it behaves under adversarial or unexpected input. This skill does not install tools like Promptfoo; it borrows only the role separation and counterexample design perspective.

Do not claim popularity, stars, or market position without measured data. State that generalizations not directly proven by a source are this skill's design choices.
