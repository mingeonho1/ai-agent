# fable switch loader (source it from ~/.zshrc etc.)
# fable 스위치 로더 (~/.zshrc 등에서 source)
# When the switch is on, injects model remapping when launching claude:
#   sonnet tier → Opus 5.5    (promotes plugin agents pinned to sonnet)
#   haiku tier  → Sonnet 5.5  (promotes chore agents pinned to haiku)
# 스위치가 on이면 claude 실행 시 모델 리매핑을 주입한다:
#   sonnet 등급 → Opus 5.5  (플러그인의 sonnet 고정 실행 에이전트 승격)
#   haiku 등급  → Sonnet 5.5  (haiku 고정 잡무 에이전트 승격)
#
# The state file resolves to ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/.fable-state.
# 상태 파일은 ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/.fable-state 로 해석한다.

_fable_state_file() { printf '%s/.fable-state' "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"; }

_fable_on() { [ "$(cat "$(_fable_state_file)" 2>/dev/null)" = "on" ]; }

_fable_run() {
  if _fable_on; then
    ANTHROPIC_DEFAULT_SONNET_MODEL="claude-opus-5-5" \
    ANTHROPIC_DEFAULT_HAIKU_MODEL="claude-sonnet-5-5" \
    "$@"
  else
    "$@"
  fi
}

# Non-interactive shells (scripts, hooks, tool shells) may not have _fable_run
# defined, so claude() is self-contained and does not depend on the helper.
# 비대화형 셸(스크립트·훅·툴 셸)에서는 _fable_run 이 정의돼 있지 않을 수 있으므로
# claude() 는 헬퍼에 의존하지 않고 스스로 완결되게 정의한다.
claude() {
  if [ "$(cat "$(_fable_state_file)" 2>/dev/null)" = "on" ]; then
    ANTHROPIC_DEFAULT_SONNET_MODEL="claude-opus-5-5" \
    ANTHROPIC_DEFAULT_HAIKU_MODEL="claude-sonnet-5-5" \
    command claude "$@"
  else
    command claude "$@"
  fi
}
