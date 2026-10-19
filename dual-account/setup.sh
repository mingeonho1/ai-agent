#!/usr/bin/env bash
# 두 번째 Claude 계정 프로필을 만든다. 로그인만 분리하고 세션·설정·에이전트·스킬은 ~/.claude 와 공유한다.
#
#   bash dual-account/setup.sh            # 설치
#   bash dual-account/setup.sh --dry-run  # 할 일만 출력
#
# 설치 후: 새 셸에서 `claude2` 실행 → `/login` 으로 서브 계정 로그인.
set -euo pipefail

MAIN="$HOME/.claude"
ALT="${CLAUDE_ALT_DIR:-$HOME/.claude-alt}"
HERE="$(cd "$(dirname "$0")" && pwd)"
case "${SHELL##*/}" in bash) RC="$HOME/.bashrc" ;; *) RC="${ZDOTDIR:-$HOME}/.zshrc" ;; esac
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
run() { if [ $DRY = 1 ]; then echo "+ $*"; else "$@"; fi; }

# 공유 항목. 로그인 정보(.claude.json·키체인)와 세션 런타임 상태는 공유하지 않는다.
SHARED=(CLAUDE.md settings.json agents skills commands plugins projects history.jsonl file-history)

run mkdir -p "$ALT"
for item in "${SHARED[@]}"; do
  [ -e "$MAIN/$item" ] && run ln -sfn "$MAIN/$item" "$ALT/$item"
done

# 사용자 범위 MCP 서버 설정만 복사(계정 정보는 복사하지 않음).
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

# 두 번째 Claude 계정 프로필 (세션·설정·스킬은 ~/.claude 공유, 로그인만 분리)
claude2() { CLAUDE_CONFIG_DIR="$ALT" claude "\$@"; }
EOF
  fi
fi

echo "완료: 새 셸에서 'claude2' 실행 후 /login 으로 서브 계정에 로그인하세요."
