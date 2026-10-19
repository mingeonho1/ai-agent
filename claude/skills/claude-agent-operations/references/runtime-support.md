# Runtime environment

Claude Fable 5.1 is the official model `claude-fable-5-1`, not an Opus alias.
Fable 5.1 requires Claude Code v2.1.257 or later; for Opus 5.5 (`claude-opus-5-5`) and
Sonnet 5.5 (`claude-sonnet-5-5`), update to the latest Claude Code (`claude update`).
Aliases resolve as `opus`→Opus 5.5, `sonnet`→Sonnet 5.5, `fable`→Fable 5.1.
On Bedrock and Vertex, aliases resolve differently, so use full model IDs.

```sh
claude --model claude-fable-5-1 --effort high
```

`CLAUDE_CODE_EFFORT_LEVEL` takes precedence over the effort in agent frontmatter.
The subagent model is resolved in this order: specified at call time → frontmatter `model` →
`CLAUDE_CODE_SUBAGENT_MODEL` environment variable → main conversation model. `/fast` (Fast mode) works on Opus 5.5.
Forced model settings or organization model/effort limits can also affect actual runs.
If it differs from the requested setup, report it and do not change the user's environment variables on your own.
File validation in this package is not evidence of per-account model access or actual model runs.

The default config root for a user install is `~/.claude/`. If a non-empty
`CLAUDE_CONFIG_DIR` is set, that path is the config root; if the variable is unset or
an empty string, it falls back to the default. User agents install into the config root's `agents/`,
and skills into `skills/claude-agent-operations/` and `skills/agent-evaluation-loop/`.
Project installs use `.claude/agents/` and `.claude/skills/`.
Native Claude config does not need `agents/openai.yaml`.

This package's `hooks/compact-reminder.json` is optional. When explicitly installed, it puts only
a short static reminder into context on the `SessionStart` `compact` event.
It does not search handoff files, read conversation history, ask for approval, or call a model.
It does not overwrite existing hooks; the installer merges the entry.

Official sources:

- [Model and effort configuration](https://code.claude.com/docs/en/model-config)
- [Subagent files and independent context](https://code.claude.com/docs/en/sub-agents)
- [Skill install locations](https://code.claude.com/docs/en/skills)
- [SessionStart hook](https://code.claude.com/docs/en/hooks#sessionstart)
- [Fable 5.1](https://platform.claude.com/docs/en/models/fable-5-1/overview)
- [Effort guide](https://platform.claude.com/docs/en/build-with-claude/effort)
- [Best practices](https://code.claude.com/docs/en/best-practices)
