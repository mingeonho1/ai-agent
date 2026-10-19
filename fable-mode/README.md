# Fable orchestration mode (fable-mode)

> 한국어: 메인 에이전트는 기획·분배만, 실행은 서브에이전트로 넘기는 선택형 모드.

An optional mode where the main agent only plans, routes, and synthesizes results, and hands execution (writing, editing, testing code) to subagents. Copy it in only if you want it.

- `fable.md`: instructions for the main agent. Execution goes to `deep-reasoner` (Opus 5.5, max), `executor` (Opus 5.5, xhigh), and `runner` (Sonnet 5.5, medium).
- `hooks/orchestration-gate.py`: PreToolUse gate. The main agent may directly edit at most 2 code files per turn, and writing code files via Bash (`sed -i`, `> x.py`, `tee`, etc.) is blocked. Subagents are not gated. Heredoc bodies are treated as data and skipped.
- `bin/fable on|off|status`: turns the mode on and off. It swaps `active.md` for `fable.md` or `empty.md`; the gate only acts while `.fable-state` is `on`.
- `env.sh`: while the mode is on, launching `claude` remaps the sonnet tier to Opus 5.5 and the haiku tier to Sonnet 5.5, so plugin agents pinned to a model run one tier up.

## How it differs from the role-model modes (standard/eco)

standard/eco are configurations where `scripts/install.py` fixes the model and effort for each role file (`ai-*`). The main agent still decides when to call which role. Fable mode uses a hook to stop the main agent from doing execution itself, and switches on and off with one command. Role names do not overlap, so both can be installed together.

## Install

If you use `CLAUDE_CONFIG_DIR`, replace `~/.claude` below with that path. Move any existing files with the same names out of the way first.

```bash
mkdir -p ~/.claude/fable ~/.claude/agents ~/.local/bin
cp -R fable-mode/{fable.md,empty.md,env.sh,bin,hooks} ~/.claude/fable/
cp fable-mode/agents/*.md ~/.claude/agents/
ln -s ~/.claude/fable/bin/fable ~/.local/bin/fable
```

Add this line to `~/.claude/CLAUDE.md`:

```
@~/.claude/fable/active.md
```

Register the gate under `hooks` in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit|NotebookEdit|MultiEdit|Bash",
        "hooks": [
          { "type": "command", "command": "python3 \"$HOME/.claude/fable/hooks/orchestration-gate.py\"" }
        ]
      }
    ]
  }
}
```

Add `source ~/.claude/fable/env.sh` to `~/.zshrc`, then run `fable on` in a new shell. Check the state with `fable status`. Sessions that do not go through the shell (e.g. IDE extensions) get no model remapping.

## Removal

`fable off` alone stops both the instructions and the gate. To remove it completely, delete the CLAUDE.md import line, the settings.json hook entry, and the `.zshrc` source line, then run:

```bash
rm -rf ~/.claude/fable ~/.claude/.fable-state ~/.local/bin/fable
rm ~/.claude/agents/{deep-reasoner,executor,runner}.md
```

## Cost

Execution agents run Opus 5.5 at high effort and the remapping raises model tiers, so this mode uses more tokens. Pair it with [dual-account](../dual-account/) to offload execution cost to a second account.

## Tests

```bash
python3 -m unittest discover -s fable-mode/tests
```
