# Review checklist

## Common preparation

- Use the original requirements and user-approved changes as the primary baseline.
- Read the current files and the stable diff, and fix the review scope.
- For claimed test passes, check that the command, environment, and result exist.
- For current facts, record the official primary source, publish/change date, and check date.
- Separate observation from inference. Without evidence, it is `needs_evidence`.
- Group symptoms of the same defect into one, and do not pad the number of findings.

## Product mode

- What problem do users actually face?
- Who are the target users, and is another group's need being measured in their place by mistake?
- Are there observations, interviews, or behavioral data supporting demand for the problem?
- Is the success metric a real outcome, or a proxy metric that easily looks good?
- Are cost, time, policy, accessibility, or operational limits missing?
- Can the same problem be solved with a simpler alternative?
- What observation would prove a core assumption false?
- Alongside the intended benefit, are there counterexamples of misuse, adverse selection, or reward hacking?

## Code mode

- Map the original requirements to the current stable diff item by item.
- Check not just the happy path but empty values, boundary values, invalid input, and partial failure.
- Check error handling, retries, recovery after interruption, and observability.
- Check concurrency, shared state, caches, ordering dependencies, and idempotency.
- Check trust boundaries for files, network, processes, and user input.
- Check compatibility with existing behavior, regression tests, and fail-then-pass tests.
- For "tests pass" claims, check the actual command and exit status. If it cannot be run, request evidence.
- Check that tests do not merely pin implementation details or grade a bypassable proxy condition.

## Severity and status

Severity is a 3-level impact classification tailored to this project. Do not call it an equivalent scale from an official standard.

- `high`: The core user goal becomes impossible, or broad/serious data loss, unauthorized access, or security damage occurs.
- `medium`: Requirements or constraints are not met for some users or conditions, but impact is limited and a workaround or mitigation is possible. A missing constraint in the plan or a functional regression on a specific path can fall here.
- `low`: Limited, non-blocking impact such as wording, maintainability, or narrow edge cases.

For each verdict, explain realistic likelihood and blast radius in a sentence. Mark the evidence level as a separate confidence.

- `confirmed`: With current material, the condition and impact are reproduced or directly proven.
- `needs_evidence`: A possible counterexample, but observation or execution evidence is lacking.
- `refuted`: On checking, the hypothesis does not hold.

## Exit conditions

- If there are no concrete findings, write "No findings within the checked scope."
- Write the unchecked scope and remaining evidence requests.
- Do not give assurances beyond scope, such as "it is safe," "it is perfect," or "there are no problems."
