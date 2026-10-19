# Why only the necessary harness

Official docs checked: 2026-09-29. Model roles and effort values are operating settings chosen by the user. Below are the official docs consulted while implementing those settings and how far each was applied. Nothing was added just because it appears in the docs.

## Claude Code

| Official source · section | Applied as |
| --- | --- |
| [Models overview](https://platform.claude.com/docs/en/models/overview), model IDs | Distinguish Fable 5.1 `claude-fable-5-1`, Opus 5.5 `claude-opus-5-5`, and Sonnet 5.5 `claude-sonnet-5-5` (Opus 5 · Sonnet 5 are legacy) |
| [Effort](https://platform.claude.com/docs/en/build-with-claude/effort), supported levels | Planning high, builder/execution medium, verification xhigh. Chosen to match official guidance (Fable default high, Sonnet 5.5 agentic start at medium, Opus 5.5 default medium); top effort is not applied to every stage |
| [Model configuration](https://code.claude.com/docs/en/model-config), effort precedence | Install docs note when a global environment variable overrides per-role settings |
| [Subagents](https://code.claude.com/docs/en/sub-agents), custom subagents | Roles are registered as Markdown files. The verifier starts in a fresh context with only Read/Grep/Glob. Frontmatter `effort` overrides session effort and `skills` preloads rubrics/checklists |
| [Skills](https://code.claude.com/docs/en/skills), skill locations | Installed in Claude-only `.claude/skills`. The main Skill coordinates the roles |
| [Settings](https://code.claude.com/docs/en/settings#find-or-create-your-settings-files), user settings path | If `CLAUDE_CONFIG_DIR` is set, user install goes into that folder |
| [Hooks](https://code.claude.com/docs/en/hooks), events and handler types | Events like Stop, PostCompact, and SubagentStop and command/prompt/agent hook types exist, but this repo ships only a SessionStart `compact` reminder; no per-tool-call hooks or automatic model-review loops |
| [Best practices](https://code.claude.com/docs/en/best-practices), loop-exit gates | Of the four gates — in-prompt checks, `/goal`, Stop hook, verification subagent — the verification subagent is core and the rest are optional |

From Anthropic's [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps) we took **separating builder and evaluator**, **observable done criteria**, and **handoff through files**. That article is a 2026-03-24 experiment, so its per-model results are not presented as Fable 5.1 measurements. Its repeated design-score iteration experiments were not adopted as defaults either.

The 2026-04-08 [Scaling Managed Agents](https://www.anthropic.com/engineering/managed-agents) explains that as models improve, older compensating mechanisms can become unnecessary. So there is no mechanism that force-resets the session every N tokens. **Independent evaluation and red-team contexts are kept separate**, and long tasks continue through small handoff documents.

From the [Fable 5.1 prompting guide](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-1), three points went into the builder and review instructions: edit only what is needed instead of rewriting everything; report out-of-scope problems found during work as follow-ups rather than fixing them; finish remaining incomplete work before ending the turn. Following the [general prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices), emphatic wording like "must, always, CRITICAL" was toned down to plain statements to reduce over-triggering. Independence, ownership, and safety rules were kept as is.

## Codex

| Official source · section | Applied as |
| --- | --- |
| [Model list](https://developers.openai.com/api/docs/models), model IDs | Astra / Sol / Luna fixed to distinct roles |
| [GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra), reasoning support | Planning high → verification xhigh, one level up |
| [Subagents](https://learn.chatgpt.com/codex/agent-configuration/subagents), Custom agents | Standalone TOML with `name`, `description`, `developer_instructions` and per-role effort; concurrency capped with `[agents] max_concurrent_threads_per_session` |
| [Build skills](https://learn.chatgpt.com/codex/build-skills), local search paths | Skills installed in `.agents/skills`, agents in `.codex/agents`, separately |
| [Hooks](https://learn.chatgpt.com/codex/hooks), events and handler types | Hooks exist and run only command / mcp_tool. This repo adds no default hooks and does not copy the Claude settings as is |
| [Config reference](https://learn.chatgpt.com/codex/config-file/config-reference), `review_model` · profiles | `review_model` sets the `/review` model; profiles use the file form `~/.codex/<name>.config.toml` + `--profile` (since 0.134.0) |

From the 2026-09-11 [Rethinking skills and prompts for GPT-6 Astra](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra) we applied **Better skills**, **Up-to-date AGENTS.md**, and **Persistence**. Astra gets the issues to judge and the done criteria rather than a full list of documents to read and steps to follow. Skill descriptions stay short and detailed contracts are read when needed. The Sol builder gets concrete files to edit, inputs/outputs, and verification commands. Luna handles only predefined searches and command runs.

Checks needed to complete verification run to the end, but once they pass, the same tests and reviews are not repeated without reason. This also draws on **Subagent delegation / Testing and verification** in the [Astra model guide](https://developers.openai.com/api/docs/guides/latest-model).

## Shared operating choices

1. Record each request as a task ID with observable done criteria. Handoffs name that task's path.
2. Parallelize only independent research or builds that write different files. The default is at most 3 concurrent workers — this repo's choice, not a platform limit.
3. The verifier reads user requirements, the stable diff, current files, and run evidence. The full conversation and the builder's persuasive text are not passed along.
4. If more information is needed, request specific files or checks. Context separation does not mean hiding needed evidence.
5. If the verification model is unavailable, report that. Do not substitute self-review for independent verification.

A Skill is a set of run rules for the model; role files are the runtime's model and effort settings. Even with hooks, this is not a system that externally enforces that a review happened. Installing does not claim that real model calls were verified.

Evaluation records and iterative improvement are in [Evaluation loop](evaluation.md); counterexample search for plans and code is in [Red team](../red-team/README.md). Score computation and iteration limits are checked by scripts, but whether evidence is genuine and whether runs were actually independent must be confirmed by the reviewer and orchestrator.
