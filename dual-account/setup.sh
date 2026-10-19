#!/usr/bin/env bash
# Create a second Claude account profile. Only login is separated; sessions, settings, agents, and skills are shared with ~/.claude.
# 두 번째 Claude 계정 프로필 생성 (로그인만 분리, 나머지는 ~/.claude 공유).
#
#   bash dual-account/setup.sh            # install
#   bash dual-account/setup.sh --dry-run  # print actions only
#
# After install: run `claude2` in a new shell → `/login` with the second account.
set -euo pipefail

MAIN="$HOME/.claude"
ALT="${CLAUDE_ALT_DIR:-$HOME/.claude-alt}"
HERE="$(cd "$(dirname "$0")" && pwd)"
case "${SHELL##*/}" in bash) RC="$HOME/.bashrc" ;; *) RC="${ZDOTDIR:-$HOME}/.zshrc" ;; esac
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
run() { if [ $DRY = 1 ]; then echo "+ $*"; else "$@"; fi; }

# Shared items. Login data (.claude.json, keychain) and session runtime state are not shared.
SHARED=(CLAUDE.md settings.json agents skills commands plugins projects history.jsonl file-history)

run mkdir -p "$ALT"
for item in "${SHARED[@]}"; do
  [ -e "$MAIN/$item" ] && run ln -sfn "$MAIN/$item" "$ALT/$item"
done

# Copy only user-scope MCP server settings (no account data).
if [ -f "$HOME/.claude.json" ] && [ ! -f "$ALT/.claude.json" ]; then
  if [ $DRY = 1 ]; then echo "+ copy mcpServers -> $ALT/.claude.json"; else
    python3 -I -c '
import json, sys
src = json.load(open(sys.argv[1]))
json.dump({"mcpServers": src.get("mcpServers", {})}, open(sys.argv[2], "w"), indent=2, ensure_ascii=False)
' "$HOME/.claude.json" "$ALT/.claude.json"
    chmod 600 "$ALT/.claude.json"
  fi
fi

run mkdir -p "$MAIN/bin"
run install -m 755 "$HERE/bin/alt-agent" "$MAIN/bin/alt-agent"

if ! grep -q 'claude2()' "$RC" 2>/dev/null; then
  if [ $DRY = 1 ]; then echo "+ append claude2() to $RC"; else
    cat >> "$RC" <<EOF

# Second Claude account profile (sessions, settings, skills shared with ~/.claude; login only is separate)
claude2() { CLAUDE_CONFIG_DIR="$ALT" claude "\$@"; }
EOF
  fi
fi

echo "Done: open a new shell, run 'claude2', and /login with the second account."
