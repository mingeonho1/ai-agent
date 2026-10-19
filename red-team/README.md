# Red-team bundle

A read-only Skill that checks a plan's premises and code's failure conditions from the opposing side. It borrows Petri's and Bloom's role separation and counterexample design, and can be registered separately from the existing operations agents.

Claude uses Fable 5.1 xhigh and Codex uses Astra xhigh. High/medium/low is the impact grade of a found problem and does not change the model's reasoning setting.

## Install

Run from the repository root.

```bash
python3 scripts/install.py claude --user --package red-team
python3 scripts/install.py codex --user --package red-team
```

To install into a specific project, use `--project PATH` instead of `--user`.

```bash
python3 scripts/install.py claude --project PATH --package red-team
python3 scripts/install.py codex --project PATH --package red-team
```

Invoke it with `/adversarial-review` in Claude and `$adversarial-review` in Codex. The main agent calls the installed `ai-red-team` (Codex config name `ai_red_team`) once as a fresh, non-inherited read-only instance, and obtains any needed execution or web research evidence itself or through a separate runner. If it cannot confirm a fresh instance, it reports the independent review as incomplete.

This bundle reads local material to find counterexamples and missing evidence. It does not attack or scan external systems and does not change files.
