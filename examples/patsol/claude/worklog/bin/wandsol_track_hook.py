#!/usr/bin/env python3
"""WandSol automatic time-tracking guidance hook (UserPromptSubmit).

English:
Once per session, on the first user prompt only, inject classification
guidance on how to use WandSol MCP time-tracking as additionalContext
(hookSpecificOutput).
- A marker file (~/.claude/worklog/wandsol_sessions/<session_id>) guarantees once per session.
- Markers older than 7 days are cleaned up.
- Scheduled sessions are not injected (detected via enforce/sessionkind).
- Automatic/subagent calls with an empty prompt are not injected.
- Always exit 0 quickly so a prompt is never blocked under any circumstance.

한국어:
세션당 첫 사용자 프롬프트에 한 번만, WandSol MCP 시간추적을 어떻게 쓸지
분류 지침을 additionalContext(hookSpecificOutput)로 주입한다.
- 마커 파일(~/.claude/worklog/wandsol_sessions/<session_id>)로 세션당 1회 보장.
- 7일 초과 마커는 정리.
- 예약(스케줄) 세션에는 주입하지 않음(enforce/sessionkind 로 판별).
- 프롬프트가 비어있는 자동/서브에이전트 호출에는 주입하지 않음.
- 어떤 경우에도 프롬프트를 막지 않도록 항상 빠르게 exit 0.
"""
import json
import os
import re
import sys
import time
from datetime import datetime


def _claudi_lang():
    # English: resolve output language — env CLAUDI_LANG, then
    # <CLAUDE_CONFIG_DIR or ~/.claude>/claudi/config.json {"lang"} (both optional;
    # only present with the claudi kit), else "en".
    # 한국어: 출력 언어 결정 — 환경변수 CLAUDI_LANG → claudi/config.json의 "lang" → 기본 "en".
    import os, json
    lang = os.environ.get("CLAUDI_LANG")
    if lang:
        return lang.strip().lower()
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    try:
        with open(os.path.join(base, "claudi", "config.json"), encoding="utf-8") as f:
            v = json.load(f).get("lang")
            if v:
                return str(v).strip().lower()
    except (OSError, ValueError):
        pass
    return "en"


def t(en, ko):
    # English: pick the string for the active output language (default English).
    # 한국어: 활성 출력 언어에 맞는 문자열 선택 (기본 영어).
    return ko if _claudi_lang() == "ko" else en


# Config directory: $CLAUDE_CONFIG_DIR or ~/.claude (do not hardcode paths).
# 설정 디렉터리: $CLAUDE_CONFIG_DIR 또는 ~/.claude (경로 하드코딩 금지).
CONFIG_DIR = os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude")
MARKER_DIR = os.path.join(CONFIG_DIR, "worklog", "wandsol_sessions")
MAX_AGE_SECONDS = 7 * 24 * 60 * 60

LOGDIR = os.path.join(CONFIG_DIR, "worklog", "logs")
LOGFILE = os.path.join(LOGDIR, "worklog.log")


def log(msg):
    """Write one line to worklog.log (the logger itself swallows any exception).
    worklog.log 에 한 줄 남긴다(로거 자체는 어떤 예외도 삼킨다)."""
    try:
        os.makedirs(LOGDIR, exist_ok=True)
        stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOGFILE, "a", encoding="utf-8") as f:
            f.write("%s wandsol_hook %s\n" % (stamp, msg))
    except Exception:
        pass


# Optionally reuse the enforce/sessionkind module (from the claudi kit) to detect scheduled sessions.
# 예약(스케줄) 세션 판별에 enforce/sessionkind 모듈(claudi 키트)을 선택적으로 재사용한다.
# Standalone: without that module the import fails, which is fine — it logs the cause (inject conservatively when detection is impossible).
# import 실패해도 동작하되 원인은 로그로 남긴다(판별 불가 시 보수적으로 주입 진행).
ENFORCE_BIN = os.path.join(CONFIG_DIR, "enforce", "bin")
if ENFORCE_BIN not in sys.path:
    sys.path.insert(0, ENFORCE_BIN)
try:
    import sessionkind
except Exception as e:
    sessionkind = None
    log("sessionkind import failed: %s: %s" % (type(e).__name__, e))

# English: additionalContext text that Claude reads — routed through t() so it follows the
# output language (English default, Korean second arg). {{JIRA_PROJECT_KEY}} placeholders preserved.
# 한국어: Claude 가 읽는 additionalContext 텍스트 — 출력 언어에 맞게 t() 로 라우팅(기본 영어,
# 두 번째 인자 한국어). {{JIRA_PROJECT_KEY}} 플레이스홀더는 그대로 유지.
INSTRUCTION = t(
    """[WandSol time-tracking — one-time guidance on the session's first prompt]

First classify the nature of this session's work, then use the WandSol MCP (time-tracking) tools per the rules below. This guidance is injected only once per session.

1) Company (PatSol) work with a clear Jira ticket — if a ticket key like '{{JIRA_PROJECT_KEY}}-<number>' appears in the branch name or the prompt, immediately start time-tracking for that ticket via WandSol MCP and announce it in a single line only, like "⏱ {{JIRA_PROJECT_KEY}}-123 time-tracking started". In this case, do not ask the user again.

2) Company work but the ticket is unclear, or the work is unrelated to the company, or its nature is ambiguous — do not start arbitrarily; ask the user exactly once, "Should I time-track this work? (tell me which ticket if needed)", and follow their answer. Do not ask again in the same session.

3) If the work switches to a different ticket mid-session, stop tracking the previous ticket and start the new one. When the work is done, stop tracking or mark it complete.

4) If the WandSol time-tracking tools are not loaded in this session, silently ignore this entire guidance (do not mention it to the user).

5) Perform the actual start/stop/complete only when the user's intent is clear. When unsure, ask first.""",
    """[WandSol 시간추적 — 세션 첫 프롬프트 1회 안내]

이 세션의 작업 성격을 먼저 분류하고, WandSol MCP(시간추적) 도구를 아래 규칙대로 사용하라. 이 안내는 세션당 한 번만 주입된다.

1) 회사(PatSol) 작업이고 Jira 티켓이 명확한 경우 — 브랜치명 또는 프롬프트에 '{{JIRA_PROJECT_KEY}}-숫자' 같은 티켓 키가 드러나면, WandSol MCP로 그 티켓의 시간추적을 바로 시작하고 "⏱ {{JIRA_PROJECT_KEY}}-123 시간추적 시작"처럼 한 줄로만 알린다. 이때는 사용자에게 다시 묻지 않는다.

2) 회사 작업이지만 티켓이 불명확하거나, 회사와 무관한 작업이거나, 성격이 애매하면 — 임의로 시작하지 말고 사용자에게 딱 한 번 "이 작업을 시간추적할까요? (필요하면 어느 티켓인지 알려주세요)"라고 물어 그 답에 따른다. 같은 세션에서는 다시 묻지 않는다.

3) 세션 도중 작업이 다른 티켓으로 전환되면, 이전 티켓의 추적을 멈추고 새 티켓으로 시작한다. 작업이 끝나면 추적을 멈추거나 완료 처리한다.

4) WandSol 시간추적 도구가 이 세션에 로드돼 있지 않으면, 이 안내 전체를 조용히 무시한다(사용자에게 언급하지 말 것).

5) 실제 시작/멈춤/완료는 사용자 의도가 분명할 때만 수행한다. 확신이 없으면 먼저 묻는다.""",
)


def cleanup_old_markers():
    try:
        now = time.time()
        for name in os.listdir(MARKER_DIR):
            path = os.path.join(MARKER_DIR, name)
            try:
                if os.path.isfile(path) and now - os.path.getmtime(path) > MAX_AGE_SECONDS:
                    os.remove(path)
            except OSError:
                pass
    except OSError:
        pass


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        return
    data = json.loads(raw)

    event = data.get("hook_event_name") or ""
    if event and event != "UserPromptSubmit":
        return

    # Do not inject for automatic/subagent calls with an empty prompt.
    # 프롬프트가 비어있는 자동/서브에이전트 호출은 주입하지 않는다.
    # (A scheduled run's first prompt is a non-empty <scheduled-task> wrapper, so it is filtered by sessionkind below.)
    # (예약 실행의 첫 프롬프트는 비어있지 않은 <scheduled-task> 래퍼이므로 아래 sessionkind 로 거른다.)
    prompt = data.get("prompt") or ""
    if not prompt.strip():
        return

    # Scheduled task session: not a target for guidance injection, and no marker is created.
    # 예약(스케줄) 작업 세션: 안내 주입 대상이 아니며 마커도 만들지 않는다.
    if sessionkind is not None and sessionkind.is_scheduled_task(data):
        return

    session_id = data.get("session_id") or ""
    sid = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id).strip("._")
    if not sid:
        return

    os.makedirs(MARKER_DIR, exist_ok=True)

    marker = os.path.join(MARKER_DIR, sid)
    if os.path.exists(marker):
        # Already guided in this session → do not re-inject.
        # 이미 이 세션에서 안내함 → 재주입하지 않음
        return

    cleanup_old_markers()

    # Handle only the first prompt (race conditions are atomically guaranteed by O_EXCL).
    # 첫 프롬프트만 처리 (경쟁 조건은 O_EXCL로 원자적 보장)
    try:
        fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        os.write(fd, str(int(time.time())).encode("utf-8"))
        os.close(fd)
    except FileExistsError:
        return

    out = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": INSTRUCTION,
        }
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Swallow hook failures so a prompt is never blocked (no blocking), logging only the cause.
        # 훅 실패가 프롬프트를 막지 않도록 삼키되(차단 금지), 원인만 로그로 남긴다.
        log("exception: %s: %s" % (type(e).__name__, e))
    sys.exit(0)
