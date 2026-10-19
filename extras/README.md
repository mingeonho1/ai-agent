# Extras

Optional general-purpose subagents. Not installed by `scripts/install.py`; copy the ones you want.

- `agents/diff-code-reviewer.md`: reviews only the diff of recent changes (Sonnet 5.5, read-only tools) to keep review focused and cheap.
- `agents/skill-evaluator.md`: strict reviewer for one `SKILL.md`; returns PASS/REVISE on four axes with minimal fixes (Sonnet 5.5).

```bash
cp extras/agents/*.md ~/.claude/agents/   # or .claude/agents/ in a project
```
