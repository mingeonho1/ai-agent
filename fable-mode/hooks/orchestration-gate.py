#!/usr/bin/env python3
# fable/hooks/orchestration-gate.py — fable enforcement gate (PreToolUse)
# fable/hooks/orchestration-gate.py — fable 강제 게이트 (PreToolUse)
#
# Lets the main agent directly edit at most 2 code files per turn (prompt_id); from
# the 3rd on it denies and returns delegation instructions. Code-file edits via Bash
# are always denied. Subagents (agent_id/agent_type in the payload) always pass —
# delegation is the execution path.
# 메인 에이전트가 한 턴(prompt_id)에 코드 파일을 2개까지만 직접 수정하게 허용하고,
# 3개째부터 차단하며 위임 지시를 돌려준다. Bash 를 통한 코드 파일 수정은 항상 차단.
# 서브에이전트(payload 에 agent_id/agent_type 존재)는 전부 통과 — 위임이 실행 경로다.
#
# When fable is off (<config>/.fable-state != on) it passes immediately. It is
# registered once in settings.json (loader); the switch decides whether it acts.
# Fail-open on error — a gate bug must never paralyze the session.
# fable off 상태(<config>/.fable-state != on)면 즉시 통과. 등록은 settings.json 에
# 1회(로딩 코드), 동작 여부는 스위치가 지배한다.
# 오류 시 fail-open(통과) — 게이트 버그가 세션을 마비시키지 않게 한다.
#
# The config dir resolves to ${CLAUDE_CONFIG_DIR:-~/.claude} (stdlib only).
# 설정 디렉터리는 ${CLAUDE_CONFIG_DIR:-~/.claude} 로 해석한다 (표준 라이브러리만).

import json
import os
import re
import sys
import time

LIMIT = 2
CONFIG_DIR = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
STATE_FILE = os.path.join(CONFIG_DIR, ".fable-state")
GATE_STATE_DIR = os.path.join(CONFIG_DIR, "fable", "state")
CODE_EXTS = {
    "ts", "tsx", "js", "jsx", "mjs", "cjs", "py", "go", "rs", "java", "kt",
    "kts", "swift", "c", "h", "cc", "cpp", "hpp", "cs", "rb", "php", "vue",
    "svelte", "astro", "css", "scss", "sass", "less", "html", "sh", "bash",
    "zsh", "sql", "lua", "dart", "scala", "ex", "exs", "zig", "ipynb",
}
EXT_RE = "|".join(sorted(CODE_EXTS))

# Whether the text right before a quote is a redirect operator (> >> tee [-flags]) —
# such a quote is the redirect target, so keep it instead of blanking it.
# 따옴표 바로 앞이 리다이렉트 연산자(> >> tee [-flags])인지 — 그 따옴표는 리다이렉트
# 대상이므로 비우지 않고 남긴다.
_REDIR_OP_END = re.compile(r"(?:>|\btee\b(?:\s+-\w+)*)\s*$")

# Heredoc body (data) up to its terminator. The header line (group 1) is kept so
# `cat <<EOF > x.py` is still caught; the body is dropped so text like "> a.py"
# inside it is not mistaken for a redirect.
# heredoc 본문(데이터)부터 종결자까지. 헤더 줄(group 1)은 남겨 `cat <<EOF > x.py`
# 는 계속 잡고, 본문은 지워 그 안의 "> a.py" 같은 텍스트를 리다이렉트로 오인하지 않는다.
HEREDOC_BODY = re.compile(
    r"(<<-?[ \t]*(['\"]?)(\w+)\2[^\n]*\n)(?:.*?\n)?[ \t]*\3[ \t]*(?=\n|$)", re.S)


def strip_inner_quotes(cmd):
    """Blank out quoted string literals with same-length spaces — except redirect
    targets (quotes preceded by > or tee). This keeps a > or code filename inside a
    string, as in `echo "a > b.py"`, from being mistaken for a redirect write.
    따옴표 문자열 리터럴을 같은 길이의 공백으로 비운다 — 단, 리다이렉트 대상
    (바로 앞이 > 나 tee 인 따옴표)은 그대로 남긴다. 이렇게 하면 `echo "a > b.py"`
    처럼 문자열 안에 든 > 나 코드 파일명을 리다이렉트 쓰기로 오인하지 않는다."""
    if "'" not in cmd and '"' not in cmd:
        return cmd
    out = []
    i = 0
    while i < len(cmd):
        ch = cmd[i]
        if ch in "\"'":
            j = cmd.find(ch, i + 1)
            if j == -1:                        # unmatched quote — keep the rest / 짝 없는 따옴표 — 남은 부분은 그대로
                out.append(cmd[i:])
                break
            span = cmd[i:j + 1]
            if _REDIR_OP_END.search(cmd[:i]):  # redirect target → keep / 리다이렉트 대상 → 유지
                out.append(span)
            else:                              # plain literal → blank / 일반 문자열 리터럴 → 비움
                out.append(" " * len(span))
            i = j + 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def allow():
    sys.exit(0)


def deny(msg):
    sys.stderr.write(msg)
    sys.exit(2)


def is_code(path):
    return path.rsplit(".", 1)[-1].lower() in CODE_EXTS if "." in path else False


def main():
    try:
        state = open(STATE_FILE).read().strip()
    except OSError:
        state = "off"
    if state != "on":
        allow()

    data = json.load(sys.stdin)

    if data.get("agent_id") or data.get("agent_type"):
        allow()  # subagents are not gated / 서브에이전트는 게이트 대상이 아님

    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input") or {}

    if tool == "Bash":
        # Drop heredoc bodies, then blank non-redirect-target quoted spans, so a >
        # or code filename inside data/string literals is not mistaken for a redirect.
        # heredoc 본문을 지우고 리다이렉트 대상이 아닌 따옴표 구간을 비운 뒤 스캔한다 —
        # 데이터·문자열 리터럴 안의 > / 코드 파일명을 리다이렉트로 오인하지 않도록.
        cmd = HEREDOC_BODY.sub(lambda m: m.group(1), tool_input.get("command", ""))
        cmd = strip_inner_quotes(cmd)
        writes_inplace = re.search(r"\b(sed|perl)\s+[^|;&]*-\w*i", cmd)
        # Deny if a redirect (> >> tee) target is a code file. Also catches quoted
        # targets (with spaces): > "my file.py" / > 'a b.ts' / > plain.py.
        # 리다이렉트(> >> tee) 대상이 코드 파일이면 차단. 따옴표로 감싼(공백 포함)
        # 대상도 잡는다: > "my file.py" / > 'a b.ts' / > plain.py.
        redirect_target = (
            r'"[^"]*\.(?:%s)"'          # "my file.py"
            r"|'[^']*\.(?:%s)'"          # 'a b.ts'
            r"|[^\s'\"|;&<>]+\.(?:%s)\b"  # plain.py
        ) % (EXT_RE, EXT_RE, EXT_RE)
        writes_redirect = re.search(
            r"(?:>>?|\btee\b(?:\s+-\w+)*)\s*(?:%s)" % redirect_target, cmd
        )
        touches_code = re.search(r"\.(?:%s)\b" % EXT_RE, cmd)
        if writes_redirect or (writes_inplace and touches_code):
            deny((
                "[fable gate] The main agent cannot modify code files via Bash. "
                "Edit code with the Edit/Write tools (up to %d files per turn) or delegate to a subagent: "
                "general implementation/edits → executor (Opus 5.5, xhigh), deep reasoning/design → "
                "deep-reasoner (Opus 5.5, max), simple chores → runner (Sonnet 5.5, medium)."
            ) % LIMIT)
        allow()

    if tool not in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
        allow()

    path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not path or not is_code(path):
        allow()  # non-code files (config, docs) may be edited directly / 설정·문서 등 비코드 파일은 직접 수정 허용

    session = re.sub(r"[^a-zA-Z0-9-]", "", data.get("session_id", "nosession"))
    prompt = data.get("prompt_id", "")
    if not prompt:
        # No/empty prompt_id → turn boundary unknown, so don't accumulate across the session (fail-open).
        # prompt_id 없음/빈값 → 턴 경계를 모르니 세션 전체로 누적하지 않는다(fail-open).
        allow()
    os.makedirs(GATE_STATE_DIR, exist_ok=True)
    gate_file = os.path.join(GATE_STATE_DIR, session + ".json")

    gate = {"prompt_id": prompt, "files": []}
    try:
        saved = json.load(open(gate_file))
        if saved.get("prompt_id") == prompt:
            gate = saved
        else:  # new turn — reset counter + prune stale session state / 새 턴 — 카운터 리셋 + 오래된 세션 상태 정리
            now = time.time()
            for fn in os.listdir(GATE_STATE_DIR):
                p = os.path.join(GATE_STATE_DIR, fn)
                if now - os.path.getmtime(p) > 86400:
                    os.remove(p)
    except (OSError, ValueError):
        pass

    if path in gate["files"]:
        allow()  # re-editing the same file is not counted / 같은 파일 재수정은 개수에 안 침

    if len(gate["files"]) < LIMIT:
        gate["files"].append(path)
        # Atomic write (avoids partial writes from concurrent hooks).
        # 원자적 쓰기(동시 훅의 부분기록 방지).
        tmp = gate_file + ".tmp"
        with open(tmp, "w") as f:
            json.dump(gate, f)
        os.replace(tmp, gate_file)
        allow()

    deny((
        "[fable gate] The main agent has already directly edited %d code files this turn (%s). "
        "Further code edits must be delegated to a subagent: general implementation/edits/tests/review → "
        "executor (Opus 5.5, xhigh), deep reasoning/design/root-cause analysis → deep-reasoner "
        "(Opus 5.5, max), simple commands/lookups → runner (Sonnet 5.5, medium). "
        "Delegate the edit you were about to make (%s) via the Agent tool with clear instructions."
    ) % (LIMIT, ", ".join(gate["files"]), path))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # fail-open
