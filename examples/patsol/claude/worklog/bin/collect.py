#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Work-journal collector.

From Claude Code transcripts (~/.claude/projects/**/*.jsonl) and local git commits,
extract only "facts Claude can know on its own" and print a one-day (or range) summary
as JSON.

Core model: "session" = one Claude Code session (the main transcript file plus the
subagent agent-*.jsonl sidechain files sharing its sessionId). Aggregation is per
session (group), not per file.

Session-to-ticket linking (strict):
  - A session is linked to a ticket only if the ticket key appears in at least one of
    (1) the git branch name, (2) the session title (custom-title), (3) a non-sidechain
    prompt typed by the human, or (4) the message/branch of a commit made within the
    session's span.
  - Tickets appearing only in sidechain (subagent) prompts, or only in tool results,
    auto-injected text or a skill's Jira lookup text are not linked (= reference-only).
  - Sessions that meet no linking criterion are classified as title-based "non-ticket work".

Three time metrics are distinguished:
  - Total time (total, union): active time over the union of all message timestamps of
    the session (group). "Actual elapsed work time" (1x even if parallel). Basis for
    sorting/filtering work units.
  - Claude workload (parallel): plain sum of per-file active time within the group. Can
    exceed total/wall time when parallel subagents overlap ("parallel sum").
  - My time (human): active time reconstructed from timestamps of human-typed prompts.

Start-date floor: dates before tracking_start_date in config.json are ignored.

Standard library only. Python 3.8+.

Usage:
    python3 collect.py                      # previous weekday
    python3 collect.py --date 2026-10-08    # specific date (local timezone)
    python3 collect.py --date 2026-10-08 --pretty
    python3 collect.py --range 2026-10-08:2026-10-14   # range sum (weekly, etc.)

Output (JSON, stdout): date, timezone, sessions[], commits[], tickets{}, human{},
                       human_events[], metrics{}, non_ticket[], totals{} ...

---
업무 일지 자동 수집기 (work-journal collector)

Claude Code transcript(~/.claude/projects/**/*.jsonl)와 로컬 git 커밋에서
"Claude가 스스로 알 수 있는 사실"만 뽑아 하루치(또는 기간) 요약을 JSON으로 출력한다.

핵심 모델: "세션" = 하나의 Claude Code 세션(메인 transcript 파일 + 같은 sessionId를
공유하는 서브에이전트 agent-*.jsonl 사이드체인 파일들의 묶음). 파일 단위가 아니라
세션(그룹) 단위로 집계한다.

세션↔티켓 연결 기준(엄격):
  - 티켓 키가 (1) git 브랜치명, (2) 세션 제목(custom-title), (3) 세션 본인(사람)이 직접
    친 비(非)사이드체인 프롬프트, (4) 세션 구간 안에 찍힌 커밋의 메시지/브랜치 중
    하나라도 있을 때만 그 세션을 티켓에 연결한다.
  - 사이드체인(서브에이전트) 프롬프트에만 등장하거나, 도구결과·자동주입·스킬의 Jira
    조회 텍스트에만 등장하는 티켓은 연결하지 않는다(= 참고용 언급으로 간주).
  - 연결 기준을 충족하지 못한 세션은 세션 제목 기반 "티켓 외 작업"으로 분류한다.

세 가지 시간 지표를 구분한다:
  - 총 시간(total, union): 세션(그룹)의 모든 메시지 타임스탬프 합집합 활성시간. "실제로
    흐른 작업 시간"(병렬이어도 1배). 작업 단위 정렬·필터의 기준.
  - Claude 작업량(parallel): 그룹 내 파일별 활성시간의 단순 합. 병렬 서브에이전트가
    겹치면 총 시간/벽시계를 초과할 수 있다("병렬 합산").
  - 내 시간(human): 사람이 직접 친 프롬프트 타임스탬프로 복원한 활성시간.

수집 시작일 하한: config.json 의 tracking_start_date 이전 날짜는 무시한다.

표준 라이브러리만 사용. Python 3.8+.

사용법:
    python3 collect.py                      # 직전 평일
    python3 collect.py --date 2026-10-08    # 특정 날짜(로컬 타임존 기준)
    python3 collect.py --date 2026-10-08 --pretty
    python3 collect.py --range 2026-10-08:2026-10-14   # 기간 합산(weekly 등)

출력(JSON, stdout): date, timezone, sessions[], commits[], tickets{}, human{},
                    human_events[], metrics{}, non_ticket[], totals{} ...
"""

import argparse
import bisect
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, date as date_cls

# Optional shared language helper (only present if the claudi kit is installed:
# <CLAUDE_CONFIG_DIR or ~/.claude>/claudi/lib). Fail-safe: absent -> English.
# 선택적 공용 언어 헬퍼(claudi 설치 시에만 존재). 없으면 영어 폴백.
_LIB = os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"),
                    "claudi", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
try:
    from claudi_i18n import t
except Exception:
    def t(en, ko):  # fail-safe fallback: English / 폴백: 영어
        return en

# ──────────────────────────────────────────────────────────────────────────
# Settings (edit only here if needed)
# 설정 (필요시 여기만 수정)
# ──────────────────────────────────────────────────────────────────────────
# Config directory: $CLAUDE_CONFIG_DIR or ~/.claude (do not hardcode paths).
# 설정 디렉터리: $CLAUDE_CONFIG_DIR 또는 ~/.claude (경로 하드코딩 금지).
CONFIG_DIR = os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude")
PROJECTS_DIR = os.path.join(CONFIG_DIR, "projects")
CONFIG_PATH = os.path.join(CONFIG_DIR, "worklog", "config.json")

# Codex (user's direct sessions) collection sources. Excludes guardian subagents (source=dict/subagent)
# Codex(사용자 직접 세션) 수집 소스. guardian 서브에이전트(source=dict/subagent)와
# and Claude session imports (imported_thread_id in external_agent_session_imports.json).
# Claude 세션 임포트(external_agent_session_imports.json의 imported_thread_id)는 제외한다.
CODEX_SESSIONS_DIRS = [
    os.path.expanduser("~/.codex/sessions"),
    os.path.expanduser("~/.codex/archived_sessions"),
]
CODEX_IMPORTS_PATH = os.path.expanduser("~/.codex/external_agent_session_imports.json")
# Originators of Codex sessions the user launched directly (GUI/CLI). Others (e.g. 'Claude Code') are excluded.
# 사용자가 직접 띄운 Codex 세션의 originator(화면/CLI). 그 외(예: 'Claude Code')는 제외.
CODEX_DIRECT_ORIGINATORS = {
    "Codex Desktop", "codex_work_desktop", "codex-tui", "codex_cli", "codex_exec",
}
# Prefixes of Codex user messages not typed by a human (auto-injected). Compared lowercase.
# Codex user 메시지 중 사람이 직접 친 게 아닌(자동주입) 접두사. 소문자 비교.
CODEX_INJECT_PREFIXES = (
    "<", "# agents.md", "# files mentioned by the user", "# environment",
    "<environment_context", "<user_instructions",
)

# Debug log for swallowed exceptions (same pattern as launchd-check.py log()). Never writes to stdout
# 예외 침묵 디버그 로그. launchd-check.py log() 패턴 복제. stdout 에는 절대 쓰지 않는다
# (the skill parses collect.py stdout as JSON). The logger swallows its own exceptions too.
# (collect.py stdout 은 스킬이 JSON 으로 파싱하므로). 로거 자체 예외도 삼킨다.
WORKLOG_LOGDIR = os.path.join(CONFIG_DIR, "worklog", "logs")
WORKLOG_LOGFILE = os.path.join(WORKLOG_LOGDIR, "worklog.log")


def _log(msg):
    try:
        os.makedirs(WORKLOG_LOGDIR, exist_ok=True)
        stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        with open(WORKLOG_LOGFILE, "a", encoding="utf-8") as f:
            f.write("%s collect %s\n" % (stamp, msg))
    except Exception:
        pass


# Reuse the enforce/sessionkind module to detect scheduled sessions. If missing, scheduled=False.
# 예약(스케줄) 세션 판별은 enforce/sessionkind 모듈을 재사용한다. 없으면 scheduled=False.
sys.path.insert(0, os.path.join(CONFIG_DIR, "enforce", "bin"))
try:
    import sessionkind  # type: ignore
except Exception as e:
    sessionkind = None
    _log("sessionkind import failed -> scheduled-session exclusion disabled: %r" % e)

# Roots to search for git commits. Repos under these roots are scanned to link tickets to commits.
# git 커밋을 뒤질 루트들. 티켓-커밋 연결을 위해 이 루트들 아래의 repo 를 스캔한다.
# The template default is just {{REPO_ROOT}}, but a non-empty repo_roots (list) in config.json
# 템플릿 기본값은 {{REPO_ROOT}} 하나지만, config.json 의 repo_roots(리스트)가 비어있지
# takes precedence — if work repos are spread across directories, add them to config.json.
# 않으면 그걸 우선한다 — 작업 repo 가 여러 디렉터리에 흩어져 있으면 config.json 에 추가한다.
DEFAULT_REPO_ROOTS = [
    os.path.expanduser("{{REPO_ROOT}}"),
]


def load_repo_roots():
    """Read and expand repo_roots (list) from config.json; default if empty or on failure.
    config.json 의 repo_roots(리스트)를 읽어 확장. 비었거나 실패하면 기본값."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f) or {}
        roots = cfg.get("repo_roots")
        if isinstance(roots, list):
            expanded = [os.path.expanduser(r) for r in roots
                        if isinstance(r, str) and r.strip()]
            if expanded:
                return expanded
    except Exception as e:  # noqa: BLE001
        _log("load_repo_roots failed (%s): %r" % (CONFIG_PATH, e))
    return list(DEFAULT_REPO_ROOTS)


REPO_ROOTS = load_repo_roots()

# Author match (git log --author regex). Both email and name contain '{{GIT_AUTHOR}}', so this covers both.
# 작성자 매칭(git log --author 정규식). 이메일/이름 모두 '{{GIT_AUTHOR}}' 를 포함하므로 이걸로 커버.
GIT_AUTHOR = "{{GIT_AUTHOR}}"

# Break threshold (min): a gap between messages larger than this counts as a "break" and is excluded from active time
# 휴식 판정 임계값(분): 메시지 간 간격이 이보다 크면 "휴식"으로 보고 활성시간에서 제외
GAP_THRESHOLD_MIN = 15

# Human activity span: prompts whose gap is <= IDLE_GAP (min) are joined into one activity span.
# 사람 활동 구간: 사람 프롬프트 사이 간격이 IDLE_GAP(분) 이하면 한 활동구간으로 잇는다.
IDLE_GAP_MIN = 15
# Minimum activity unit (min) credited per human prompt = ticket attribution time-slot size.
# 사람 프롬프트 1건에 부여하는 최소 활동 단위(분) = 티켓 귀속 시간 슬롯 크기.
HUMAN_SLOT_MIN = 5

# Mixed-session candidate: many human prompts plus a long wall clock marks the session as one that
# 혼합 세션 후보 판정: 사람 프롬프트가 많고 벽시계가 길면 "여러 주제가 섞였을 수"
# "may mix several topics" (mixed_candidate). Whether it is mixed, its main topic and topic list are
# 있는 세션(mixed_candidate)으로 표시한다. 최종 혼합 여부·대표 주제·주제 나열은 요약
# decided by Claude at the summary step from the human prompts (see the SKILL's mixed-session section).
# 단계에서 Claude가 사람 프롬프트를 보고 판단한다(SKILL "혼합 세션 판단" 참조).
MIXED_PROMPT_MIN = 10
MIXED_WALL_MIN = 120

# Ticket key pattern: PROJ-123. Common technical tokens (false positives) are excluded via DENY_PREFIXES.
# 티켓 키 패턴: PROJ-123 형태. 흔한 기술 토큰 오탐은 DENY_PREFIXES로 제외.
TICKET_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,9})-(\d+)\b")
DENY_PREFIXES = {
    "UTF", "SHA", "ISO", "RFC", "CVE", "BASE", "HTTP", "HTTPS", "MD", "CRC",
    "UTC", "GMT", "IPV4", "IPV6", "GPT", "CLAUDE", "OPUS", "SONNET", "HAIKU",
    "H", "W", "X", "Y", "Z", "P", "T", "AM", "PM", "EC2", "S3", "RGBA", "RGB",
    "ES", "ES6", "CSS", "HTML5", "VPC", "API", "URL", "URI", "JSON", "JWT",
    "I18N", "L10N", "OAUTH", "OAUTH2", "K8S", "PR", "CI", "CD",
}

TEXT_SNIPPET_LEN = 300

# Bucket key for work with no ticket. Kept in Korean on purpose: it is a data key shared
# with aggregate.py and the Korean Notion workspace schema, not a display string.
# 티켓 없는 작업 묶음 키. aggregate.py·Notion 스키마와 공유하는 데이터 키라 한국어 유지.
ETC_KEY = "기타"
# Fallback label for a session without a title (user-facing, follows output language).
# 제목 없는 세션의 대체 라벨(사용자에게 보이므로 출력 언어를 따른다).
UNTITLED = t("(untitled)", "(제목 없음)")

# Prefixes of user messages that are not human prompts (auto-injected). Compared lowercase.
# 사람 프롬프트가 아닌(자동 주입) user 메시지의 접두사. 소문자로 비교.
INJECT_PREFIXES = (
    "<local-command-stdout", "<command-", "<scheduled-task",
    "<system-reminder", "<task-notification", "caveat:",
)

# ──────────────────────────────────────────────────────────────────────────
# Utilities
# 유틸
# ──────────────────────────────────────────────────────────────────────────

def load_tracking_start():
    """tracking_start_date (YYYY-MM-DD) from config.json, or None.
    config.json 의 tracking_start_date(YYYY-MM-DD). 없으면 None."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return (json.load(f) or {}).get("tracking_start_date")
    except Exception as e:
        _log("load_tracking_start failed (%s): %r" % (CONFIG_PATH, e))
        return None


def parse_ts(ts):
    """ISO8601 (…Z) string -> local-timezone aware datetime; None on failure.
    ISO8601(…Z) 문자열 → 로컬 타임존 aware datetime. 실패 시 None."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.astimezone()  # convert to system local timezone / 시스템 로컬 타임존으로 변환
    except Exception:
        return None


def previous_weekday(d):
    """Previous weekday (Mon-Fri) before date d.
    d(날짜) 기준 직전 평일(월~금)."""
    cur = d - timedelta(days=1)
    while cur.weekday() >= 5:  # 5=Sat,6=Sun / 5=토,6=일
        cur -= timedelta(days=1)
    return cur


def extract_tickets(*texts):
    """Extract the set of ticket keys from several texts (sorted list).
    여러 텍스트에서 티켓 키 집합을 추출(정렬된 리스트)."""
    found = set()
    for t in texts:
        if not t:
            continue
        for m in TICKET_RE.finditer(t):
            prefix = m.group(1)
            if prefix in DENY_PREFIXES:
                continue
            found.add(f"{prefix}-{m.group(2)}")
    return sorted(found)


def msg_text(content):
    """Extract only human-readable text from message.content (str or list of blocks).
    message.content(str 또는 블록 리스트)에서 사람이 읽을 텍스트만 추출."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                parts.append(b.get("text", ""))
        return "\n".join(parts)
    return ""


def is_tool_result(content):
    if isinstance(content, list):
        return any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)
    return False


def is_real_user_text(o):
    """Whether this is real user input (typed by a human). Excludes tool results/meta/image meta.
    (Broad detection — includes sidechain subagent prompts. Used only for commit-session matching.)
    실제 사용자 입력(사람이 친 것)인지. 도구결과/메타/이미지메타 제외.
    (broad 탐지용 — 사이드체인 subagent 프롬프트까지 넓게 본다. 커밋-세션 매칭에만 사용.)"""
    if o.get("type") != "user":
        return False
    if o.get("isMeta"):
        return False
    m = o.get("message") or {}
    c = m.get("content")
    if is_tool_result(c):
        return False
    txt = msg_text(c).strip()
    if not txt:
        return False
    if txt.startswith("<local-command-stdout>") or txt.startswith("<command-"):
        return False
    return True


def is_human_prompt(o):
    """Whether this is a prompt typed directly by the human (for human time and strict ticket links).
    Stricter than is_real_user_text: also excludes sidechains (subagents), task-notification,
    scheduled wrappers, system-reminder and caveat.
    사람이 직접 입력한 프롬프트인지(사람 시간·엄격 티켓 연결용). is_real_user_text 보다
    엄격: 사이드체인(서브에이전트)·task-notification·예약 래퍼·system-reminder·caveat 도 제외."""
    if o.get("type") != "user":
        return False
    if o.get("isMeta") or o.get("isSidechain"):
        return False
    m = o.get("message") or {}
    c = m.get("content")
    if is_tool_result(c):
        return False
    txt = msg_text(c).strip()
    if not txt:
        return False
    low = txt.lower()
    if any(low.startswith(p) for p in INJECT_PREFIXES):
        return False
    return True


def clip(s, n=TEXT_SNIPPET_LEN):
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s[:n]


def active_minutes_from_times(times):
    """Sorted datetime list -> estimated active minutes (sums only gaps <= threshold).
    정렬된 datetime 리스트 → 활성 추정 분(간격 ≤ 임계값인 구간만 합산)."""
    if len(times) < 2:
        return 0.0
    times = sorted(times)
    total = 0.0
    thresh = GAP_THRESHOLD_MIN * 60
    for a, b in zip(times, times[1:]):
        gap = (b - a).total_seconds()
        if 0 < gap <= thresh:
            total += gap
    return round(total / 60.0, 1)


def slot_active_minutes(times, idle_gap_min=IDLE_GAP_MIN, slot_min=HUMAN_SLOT_MIN):
    """Human prompt timestamps -> slot-method active minutes (same rule as compute_human).
    Joins prompts within idle_gap into segments, extends each segment by slot_min after its
    last prompt and credits it on a slot_min grid (at least slot_min per prompt).
    사람 프롬프트 타임스탬프 → slot 방식 활성 분(compute_human 과 동일 규칙).
    프롬프트를 idle_gap 이내로 세그먼트로 잇고, 각 세그먼트에 마지막 프롬프트 이후
    slot_min 을 더한 구간을 slot_min 격자로 크레딧한다(프롬프트 1건당 최소 slot_min)."""
    times = sorted(t for t in times if t is not None)
    if not times:
        return 0.0
    gap = timedelta(minutes=idle_gap_min)
    slot = timedelta(minutes=slot_min)
    segs = []
    seg_start = seg_last = times[0]
    for t in times[1:]:
        if t - seg_last <= gap:
            seg_last = t
        else:
            segs.append((seg_start, seg_last))
            seg_start = seg_last = t
    segs.append((seg_start, seg_last))
    total = 0.0
    for a, b in segs:
        end = b + slot
        s = a
        while s < end:
            total += min(float(slot_min), (end - s).total_seconds() / 60.0)
            s = s + slot
    return round(total, 1)


def minutes_to_hhmm(mins):
    mins = int(round(mins))
    return f"{mins // 60}:{mins % 60:02d}"


def session_is_scheduled(session_id, fp):
    """True if this session is a scheduled run. Conservatively False without sessionkind.
    이 세션이 예약(스케줄) 실행이면 True. sessionkind 없으면 보수적으로 False."""
    if sessionkind is None:
        return False
    try:
        return bool(sessionkind.is_scheduled_task(
            {"session_id": session_id, "transcript_path": fp}))
    except Exception as e:
        _log("session_is_scheduled failed (%s): %r" % (session_id, e))
        return False


def read_git_head(cwd):
    """Current branch name of cwd (if possible); None on failure.
    cwd의 현재 브랜치명(가능하면). 실패 시 None."""
    head = os.path.join(cwd, ".git", "HEAD")
    try:
        with open(head, "r", encoding="utf-8") as f:
            data = f.read().strip()
        if data.startswith("ref: refs/heads/"):
            return data[len("ref: refs/heads/"):]
    except Exception:
        pass
    return None


# ──────────────────────────────────────────────────────────────────────────
# Transcript collection (raw per-file records)
# transcript 수집 (파일 단위 원시 레코드)
# ──────────────────────────────────────────────────────────────────────────

def collect_file_records(target_dates):
    """
    target_dates: set of 'YYYY-MM-DD' (local). Each (file, date) pair becomes a raw record.
    Returns: {date: [raw_record, ...]}  (raw_record keeps its datetime list as-is)
    target_dates: set of 'YYYY-MM-DD' (로컬). 각 (파일,날짜) 조합을 원시 레코드로 만든다.
    반환: {date: [raw_record, ...]}  (raw_record 는 datetime 리스트를 그대로 들고 있음)
    """
    results = {d: [] for d in target_dates}
    files = glob.glob(os.path.join(PROJECTS_DIR, "**", "*.jsonl"), recursive=True)

    for fp in files:
        per_date = {}  # d -> accumulator
        file_custom_title = None  # session title (custom) / 세션 제목(커스텀)
        try:
            fh = open(fp, "r", encoding="utf-8", errors="replace")
        except Exception:
            continue
        with fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                t = o.get("type")
                if t == "custom-title":
                    ct = o.get("customTitle")
                    if ct:
                        file_custom_title = ct
                    continue
                if t not in ("user", "assistant", "system"):
                    continue
                dt = parse_ts(o.get("timestamp"))
                if dt is None:
                    continue
                d = dt.strftime("%Y-%m-%d")
                if d not in target_dates:
                    continue
                acc = per_date.get(d)
                if acc is None:
                    acc = {
                        "times": [], "cwd": None, "branch": None,
                        "session_id": o.get("sessionId"),
                        "is_sidechain": False,
                        "user_texts": [], "first_user": None, "last_asst": None,
                        "user_count": 0, "asst_count": 0, "msg_count": 0,
                        "human_times": [], "human_texts": [],
                        "tok_in": 0, "tok_out": 0, "tok_cc": 0, "tok_cr": 0,
                        "reaction_delays": [], "last_asst_ts": None,
                    }
                    per_date[d] = acc
                acc["times"].append(dt)
                acc["msg_count"] += 1
                if o.get("cwd"):
                    acc["cwd"] = o["cwd"]
                if o.get("gitBranch"):
                    acc["branch"] = o["gitBranch"]
                if o.get("sessionId"):
                    acc["session_id"] = o["sessionId"]
                if o.get("isSidechain"):
                    acc["is_sidechain"] = True
                if t == "user":
                    if is_human_prompt(o):
                        acc["human_times"].append(dt)
                        la = acc.get("last_asst_ts")
                        if la is not None:
                            gap = (dt - la).total_seconds()
                            if 0 < gap <= GAP_THRESHOLD_MIN * 60:
                                acc["reaction_delays"].append(round(gap / 60.0, 2))
                            acc["last_asst_ts"] = None
                        htxt = clip(msg_text((o.get("message") or {}).get("content")), 500)
                        if htxt:
                            acc["human_texts"].append(htxt)
                    if is_real_user_text(o):
                        acc["user_count"] += 1
                        txt = clip(msg_text((o.get("message") or {}).get("content")), 500)
                        if txt:
                            acc["user_texts"].append(txt)
                            if acc["first_user"] is None:
                                acc["first_user"] = txt
                elif t == "assistant":
                    acc["asst_count"] += 1
                    acc["last_asst_ts"] = dt
                    u = (o.get("message") or {}).get("usage") or {}
                    acc["tok_in"] += u.get("input_tokens") or 0
                    acc["tok_out"] += u.get("output_tokens") or 0
                    acc["tok_cc"] += u.get("cache_creation_input_tokens") or 0
                    acc["tok_cr"] += u.get("cache_read_input_tokens") or 0
                    txt = msg_text((o.get("message") or {}).get("content")).strip()
                    if txt:
                        acc["last_asst"] = clip(txt, 400)

        sid_from_name = os.path.splitext(os.path.basename(fp))[0]
        for d, acc in per_date.items():
            if not acc["times"]:
                continue
            branch = acc["branch"]
            if not branch and acc["cwd"]:
                branch = read_git_head(acc["cwd"])
            acc["branch"] = branch
            acc["file"] = fp
            acc["session_id"] = acc["session_id"] or sid_from_name
            acc["custom_title"] = file_custom_title
            acc["active_minutes"] = active_minutes_from_times(acc["times"])
            results[d].append(acc)

    return results


# ──────────────────────────────────────────────────────────────────────────
# Session (group) assembly: bundle files sharing a sessionId into one session.
# 세션(그룹) 조립: 같은 sessionId 의 파일들을 하나의 세션으로 묶는다.
# ──────────────────────────────────────────────────────────────────────────

def build_session(members):
    """File records with the same (sessionId, date) -> one session dict.
    같은 (sessionId, date) 파일 레코드들 → 하나의 세션 dict."""
    members = sorted(members, key=lambda r: min(r["times"]))
    # Prefer the main (non-sidechain) file; otherwise the first file overall.
    # 메인 파일(비 사이드체인) 우선, 없으면 전체 중 첫 파일.
    mains = [r for r in members if not r["is_sidechain"]]
    main = mains[0] if mains else members[0]

    branch = None
    for r in members:
        b = r.get("branch")
        if b and b != "HEAD":
            branch = b
            break
    if not branch:
        branch = main.get("branch")

    title = None
    for r in members:
        if r.get("custom_title"):
            title = r["custom_title"]
            break

    all_times = []
    human_times = []
    human_texts = []
    user_texts = []
    tok_in = tok_out = tok_cc = tok_cr = 0
    reaction_delays = []
    active_parallel = 0.0
    first_user = None
    last_asst = None
    msg_count = user_count = asst_count = 0
    cwd = main.get("cwd")
    project = os.path.basename(cwd.rstrip("/")) if cwd else None
    for r in members:
        all_times.extend(r["times"])
        human_times.extend(r["human_times"])
        human_texts.extend(r["human_texts"])
        user_texts.extend(r["user_texts"])
        tok_in += r["tok_in"]; tok_out += r["tok_out"]
        tok_cc += r["tok_cc"]; tok_cr += r["tok_cr"]
        reaction_delays.extend(r["reaction_delays"])
        active_parallel += r["active_minutes"]
        msg_count += r["msg_count"]; user_count += r["user_count"]; asst_count += r["asst_count"]
        if first_user is None and r.get("first_user"):
            first_user = r["first_user"]
        if r.get("last_asst"):
            last_asst = r["last_asst"]

    all_times.sort()
    human_times.sort()

    # Total time (union) uses only main (non-sidechain) file timestamps. Subagent (sidechain)
    # 총 시간(합집합)은 메인(비사이드체인) 파일 타임스탬프만 쓴다. 서브에이전트(사이드체인)
    # active time counts only toward Claude workload (parallel sum), not "actual elapsed work time".
    # 활성시간은 Claude 작업량(병렬 합산)에만 기여하고 "실제로 흐른 작업 시간"에는 넣지 않는다.
    main_times = sorted(t for r in members if not r["is_sidechain"] for t in r["times"])
    if not main_times:
        main_times = all_times

    # Strict tickets: branch + session title + human (non-sidechain) prompts
    # 엄격 티켓: 브랜치 + 세션 제목 + 사람(비사이드체인) 프롬프트
    strict_tickets = extract_tickets(branch or "", title or "", "\n".join(human_texts))
    # All content (incl. sidechains) — used only for commit-to-session owner matching
    # 내용 전반(사이드체인 포함) — 커밋-세션 소유자 매칭에만 사용
    content_tickets = extract_tickets(branch or "", title or "", "\n".join(user_texts))

    # Per-ticket link basis (branch/session title/prompt). Commit basis is added in attribute_commits.
    # 티켓별 연결 근거(브랜치/세션 제목/프롬프트). 커밋 근거는 attribute_commits 에서 추가.
    branch_tks = set(extract_tickets(branch or ""))
    title_tks = set(extract_tickets(title or ""))
    prompt_tks = set(extract_tickets("\n".join(human_texts)))
    ticket_basis = {}
    for t in strict_tickets:
        bs = []
        if t in branch_tks:
            bs.append("branch")
        if t in title_tks:
            bs.append("title")
        if t in prompt_tks:
            bs.append("prompt")
        ticket_basis[t] = bs
    # Summary material: human prompt excerpts (max 3). For mixed_candidate judgment and topic listing,
    # 요약 작성용 재료: 사람 프롬프트 발췌(최대 3개). mixed_candidate 판단·주제 나열용으로
    # more excerpts (max 12) are exposed as well.
    # 더 많은 발췌(최대 12개)도 함께 노출한다.
    human_samples = [clip(x, 200) for x in human_texts[:3]]
    human_samples_more = [clip(x, 120) for x in human_texts[:12]]

    wall_minutes = round((all_times[-1] - all_times[0]).total_seconds() / 60.0, 1)
    mixed_candidate = (len(human_times) >= MIXED_PROMPT_MIN and wall_minutes >= MIXED_WALL_MIN)

    is_scheduled = session_is_scheduled(main["session_id"], main["file"])

    sess = {
        "session_id": main["session_id"],
        "files": [r["file"] for r in members],
        "file_count": len(members),
        "cwd": cwd,
        "project": project,
        "git_branch": branch,
        "is_scheduled": is_scheduled,
        "start": all_times[0].strftime("%H:%M"),
        "end": all_times[-1].strftime("%H:%M"),
        "start_ts": all_times[0].isoformat(),
        "end_ts": all_times[-1].isoformat(),
        "wall_minutes": wall_minutes,
        "tool": "Claude",
        # The three metrics
        # 세 지표
        "active_minutes": active_parallel,                        # Claude workload (parallel sum) / Claude 작업량(병렬 합산)
        "total_minutes": active_minutes_from_times(main_times),   # total time (union, main only) / 총 시간(합집합, 메인만)
        "human_active_minutes": slot_active_minutes(human_times),  # my time (slot method) / 내 시간(slot 방식)
        "tokens": {
            "input": tok_in, "output": tok_out,
            "cache": tok_cc + tok_cr,
            "total": tok_in + tok_out + tok_cc + tok_cr,
        },
        "reaction_delays": reaction_delays,
        "reaction_delay_sum": round(sum(reaction_delays), 2),
        "custom_title": title,
        "label": (title
                  or clip((human_texts[0] if human_texts else first_user) or "", 60)
                  or UNTITLED),
        "message_count": msg_count,
        "user_message_count": user_count,
        "assistant_message_count": asst_count,
        "human_prompt_count": len(human_times),
        "human_times": [t.isoformat() for t in human_times],
        "tickets": strict_tickets,            # strict links (augmented after commit-owner matching) / 엄격 연결(커밋 소유자 매칭 후 보강됨)
        "strict_tickets": list(strict_tickets),
        "content_tickets": content_tickets,
        "ticket_basis": ticket_basis,          # {ticket: [branch/title/prompt/commit]} / {티켓: [branch/title/prompt/commit]}
        "human_samples": human_samples,        # summary material (human prompt excerpts) / 요약 재료(사람 프롬프트 발췌)
        "human_samples_more": human_samples_more,  # excerpts for mixed-session topic judgment (max 12) / 혼합 세션 주제 판단용 발췌(최대 12)
        "mixed_candidate": mixed_candidate,    # candidate that may mix topics (confirmed at summary step) / 여러 주제가 섞였을 수 있는 후보(요약 단계서 확정)
        "first_user_request": clip(first_user or "", TEXT_SNIPPET_LEN),
        "last_result": clip(last_asst or "", TEXT_SNIPPET_LEN),
        "_start_dt": all_times[0],
        "_end_dt": all_times[-1],
    }
    return sess


def collect_sessions(target_dates):
    """{date: [session_group_dict, ...]} — per-session units with files grouped by sessionId.
    {date: [session_group_dict, ...]} — 파일을 sessionId 로 묶은 세션 단위."""
    recs_by_date = collect_file_records(target_dates)
    out = {d: [] for d in target_dates}
    for d, recs in recs_by_date.items():
        groups = {}
        for r in recs:
            groups.setdefault(r["session_id"], []).append(r)
        sessions = [build_session(members) for members in groups.values()]
        sessions.sort(key=lambda s: s["start_ts"])
        out[d] = sessions
    return out


# ──────────────────────────────────────────────────────────────────────────
# Codex session collection (user's direct sessions only; excludes subagents and Claude imports)
# Codex 세션 수집 (사용자 직접 세션만; subagent·Claude 임포트 제외)
# ──────────────────────────────────────────────────────────────────────────

def load_codex_imported_ids():
    """Set of imported_thread_id from external_agent_session_imports.json. Sessions created by
    importing Claude sessions into Codex would be double counted, so they are excluded via this set.
    external_agent_session_imports.json 의 imported_thread_id 집합. Claude 세션을
    Codex 로 임포트해 생긴 세션은 이중계상되므로 이 집합으로 제외한다."""
    try:
        with open(CODEX_IMPORTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        return {r.get("imported_thread_id") for r in (data.get("records") or [])
                if r.get("imported_thread_id")}
    except FileNotFoundError:
        return set()
    except Exception as e:
        _log("load_codex_imported_ids failed (%s): %r" % (CODEX_IMPORTS_PATH, e))
        return set()


def _codex_user_text(content):
    """Codex response_item message content -> human-readable text.
    Codex response_item 메시지 content → 사람이 읽는 텍스트."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") in ("input_text", "text", "output_text"):
                parts.append(b.get("text", ""))
        return "\n".join(parts)
    return ""


def _is_codex_human_prompt(txt):
    """Whether a Codex user message is a human-typed prompt (excludes auto-injection, commands, file-attachment notes).
    Codex user 메시지가 사람이 직접 친 프롬프트인지(자동주입·명령·파일첨부 메모 제외)."""
    t = (txt or "").strip()
    if not t:
        return False
    low = t.lower()
    for p in CODEX_INJECT_PREFIXES:
        if low.startswith(p):
            return False
    return True


def _build_codex_session(sid, fp, cwd, branch, dstr, acc):
    """Codex per-(session, date) accumulator -> session dict with the Claude session schema (tool='Codex').
    No sidechains, so Claude workload (active) = total time (total). Reaction delay is not aggregated.
    Codex per-(세션,날짜) 누적 → Claude 세션과 같은 스키마의 세션 dict(tool='Codex').
    사이드체인이 없으므로 Claude 작업량(active)=총 시간(total). 반응지연은 집계 안 함."""
    times = sorted(acc["times"])
    human_times = sorted(acc["human_times"])
    human_texts = acc["human_texts"]
    project = os.path.basename(cwd.rstrip("/")) if cwd else None
    total = active_minutes_from_times(times)
    wall = round((times[-1] - times[0]).total_seconds() / 60.0, 1) if len(times) > 1 else 0.0
    label = clip((human_texts[0] if human_texts else acc.get("first_user")) or "", 60) or UNTITLED
    strict_tickets = extract_tickets(branch or "", "\n".join(human_texts))
    branch_tks = set(extract_tickets(branch or ""))
    prompt_tks = set(extract_tickets("\n".join(human_texts)))
    ticket_basis = {}
    for t in strict_tickets:
        bs = []
        if t in branch_tks:
            bs.append("branch")
        if t in prompt_tks:
            bs.append("prompt")
        ticket_basis[t] = bs
    tok_total = acc["tok_in"] + acc["tok_out"] + acc["tok_cc"]
    return {
        "session_id": sid,
        "files": [fp],
        "file_count": 1,
        "cwd": cwd,
        "project": project,
        "git_branch": branch,
        "is_scheduled": False,
        "tool": "Codex",
        "start": times[0].strftime("%H:%M"),
        "end": times[-1].strftime("%H:%M"),
        "start_ts": times[0].isoformat(),
        "end_ts": times[-1].isoformat(),
        "wall_minutes": wall,
        "active_minutes": total,            # Codex agent work (no sidechains) / Codex 에이전트 작업(사이드체인 없음)
        "total_minutes": total,             # total time (union) / 총 시간(합집합)
        "human_active_minutes": slot_active_minutes(human_times),  # my time (slot) / 내 시간(slot)
        "tokens": {"input": acc["tok_in"], "output": acc["tok_out"],
                   "cache": acc["tok_cc"], "total": tok_total},
        "reaction_delays": [],
        "reaction_delay_sum": 0.0,
        "custom_title": None,
        "label": label,
        "message_count": len(times),
        "user_message_count": len(human_times),
        "assistant_message_count": 0,
        "human_prompt_count": len(human_times),
        "human_times": [t.isoformat() for t in human_times],
        "tickets": strict_tickets,
        "strict_tickets": list(strict_tickets),
        "content_tickets": list(strict_tickets),
        "ticket_basis": ticket_basis,
        "human_samples": [clip(x, 200) for x in human_texts[:3]],
        "human_samples_more": [clip(x, 120) for x in human_texts[:12]],
        "mixed_candidate": (len(human_times) >= MIXED_PROMPT_MIN and wall >= MIXED_WALL_MIN),
        "first_user_request": clip(acc.get("first_user") or "", TEXT_SNIPPET_LEN),
        "last_result": clip(acc.get("last_asst") or "", TEXT_SNIPPET_LEN),
        "_start_dt": times[0],
        "_end_dt": times[-1],
    }


def collect_codex_sessions(target_dates):
    """Collect the user's direct Codex sessions into per-date session groups (KST). Excludes: dict
    source (guardian subagent), imported_thread_id (Claude session import), non-direct originators.
    Returns: {date: [session_dict(tool='Codex'), ...]}
    사용자 직접 Codex 세션을 날짜별 세션 그룹으로 수집한다(KST). 제외: source 가 dict
    (guardian 서브에이전트), imported_thread_id(Claude 세션 임포트), 비직접 originator.
    반환: {date: [session_dict(tool='Codex'), ...]}"""
    out = {d: [] for d in target_dates}
    imported = load_codex_imported_ids()
    files = []
    for root in CODEX_SESSIONS_DIRS:
        if not os.path.isdir(root):
            continue
        files += glob.glob(os.path.join(root, "**", "rollout-*.jsonl"), recursive=True)
        files += glob.glob(os.path.join(root, "rollout-*.jsonl"))
    for fp in sorted(set(files)):
        try:
            fh = open(fp, "r", encoding="utf-8", errors="replace")
        except Exception:
            continue
        with fh:
            first = fh.readline().strip()
            if not first:
                continue
            try:
                o = json.loads(first)
            except Exception:
                continue
            if o.get("type") != "session_meta":
                continue
            meta = o.get("payload") or {}
            src = meta.get("source")
            sid = meta.get("session_id")
            if isinstance(src, dict):          # guardian subagent / guardian 서브에이전트
                continue
            if sid in imported:                # Claude session import (avoid double counting) / Claude 세션 임포트(이중계상 방지)
                continue
            if meta.get("originator") not in CODEX_DIRECT_ORIGINATORS:
                continue
            cwd = meta.get("cwd")
            g = meta.get("git")
            branch = (g or {}).get("branch") if isinstance(g, dict) else None
            per_date = {}
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                dt = parse_ts(r.get("timestamp"))
                if dt is None:
                    continue
                d = dt.strftime("%Y-%m-%d")
                if d not in target_dates:
                    continue
                acc = per_date.get(d)
                if acc is None:
                    acc = {"times": [], "human_times": [], "human_texts": [],
                           "first_user": None, "last_asst": None,
                           "tok_in": 0, "tok_out": 0, "tok_cc": 0}
                    per_date[d] = acc
                acc["times"].append(dt)
                t = r.get("type")
                p = r.get("payload") or {}
                if t == "response_item" and p.get("type") == "message":
                    role = p.get("role")
                    if role == "user":
                        txt = _codex_user_text(p.get("content")).strip()
                        if _is_codex_human_prompt(txt):
                            acc["human_times"].append(dt)
                            acc["human_texts"].append(clip(txt, 500))
                            if acc["first_user"] is None:
                                acc["first_user"] = clip(txt, 500)
                    elif role == "assistant":
                        atxt = _codex_user_text(p.get("content")).strip()
                        if atxt:
                            acc["last_asst"] = clip(atxt, 400)
                elif t == "event_msg" and p.get("type") == "token_count":
                    tu = (p.get("info") or {}).get("total_token_usage") or {}
                    if tu:
                        acc["tok_in"] = tu.get("input_tokens", acc["tok_in"])
                        acc["tok_out"] = tu.get("output_tokens", acc["tok_out"])
                        acc["tok_cc"] = ((tu.get("cached_input_tokens") or 0)
                                         + (tu.get("cache_write_input_tokens") or 0)) or acc["tok_cc"]
        for d, acc in per_date.items():
            if not acc["times"]:
                continue
            out[d].append(_build_codex_session(sid, fp, cwd, branch, d, acc))
    for d in out:
        out[d].sort(key=lambda s: s["start_ts"])
    return out


def primary_human_ticket(session):
    """The 'representative ticket' to attribute human attention time to. Strict tickets
    (branch > title > human prompt) first, else ETC_KEY. Also considers commit-augmented tickets.
    사람 주의 시간을 귀속할 '대표 티켓'. 엄격 티켓(브랜치>제목>사람프롬프트) 우선,
    없으면 '기타'. 커밋으로 보강된 tickets 도 참고(브랜치/커밋 기반 작업)."""
    bt = extract_tickets(session.get("git_branch") or "")
    if bt:
        return bt[0]
    st = session.get("strict_tickets") or []
    if st:
        return st[0]
    tk = session.get("tickets") or []
    if tk:
        return tk[0]
    return ETC_KEY


# ──────────────────────────────────────────────────────────────────────────
# Git commit collection
# git 커밋 수집
# ──────────────────────────────────────────────────────────────────────────

def find_repos():
    repos = []
    for root in REPO_ROOTS:
        if not os.path.isdir(root):
            continue
        try:
            for name in sorted(os.listdir(root)):
                p = os.path.join(root, name)
                if os.path.isdir(os.path.join(p, ".git")):
                    repos.append(p)
        except Exception:
            continue
    return repos


def collect_commits(target_dates):
    """Returns: {date: [commit_dict, ...]}
    반환: {date: [commit_dict, ...]}"""
    out = {d: [] for d in target_dates}
    dates_sorted = sorted(target_dates)
    since = dates_sorted[0] + " 00:00:00"
    until = dates_sorted[-1] + " 23:59:59"
    SEP = "\x1f"
    fmt = SEP.join(["%H", "%cI", "%an", "%ae", "%s", "%D"])
    for repo in find_repos():
        cur_branch = None
        try:
            r = subprocess.run(
                ["git", "-C", repo, "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                cur_branch = r.stdout.strip()
        except Exception:
            pass
        try:
            r = subprocess.run(
                ["git", "-C", repo, "log", "--all", "--no-merges",
                 "--author=" + GIT_AUTHOR,
                 "--since=" + since, "--until=" + until,
                 "--pretty=format:" + fmt],
                capture_output=True, text=True, timeout=30,
            )
        except Exception as e:
            _log("collect_commits git log failed (%s): %r" % (repo, e))
            continue
        if r.returncode != 0:
            continue
        seen = set()
        for line in r.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split(SEP)
            if len(parts) < 6:
                continue
            h, ciso, an, ae, subj, decor = parts[:6]
            if h in seen:
                continue
            seen.add(h)
            dt = parse_ts(ciso)
            if dt is None:
                continue
            d = dt.strftime("%Y-%m-%d")
            if d not in target_dates:
                continue
            branch = cur_branch
            if decor:
                for tok in [x.strip() for x in decor.split(",")]:
                    tok = tok.replace("HEAD -> ", "").strip()
                    if tok and not tok.startswith("tag:") and not tok.startswith("origin/"):
                        branch = tok
                        break
            tickets = extract_tickets(subj, branch or "", decor or "")
            out[d].append({
                "repo": os.path.basename(repo),
                "repo_path": repo,
                "hash": h[:10],
                "time": dt.strftime("%H:%M"),
                "ts": dt.isoformat(),
                "_dt": dt,
                "author": an,
                "email": ae,
                "message": clip(subj, 200),
                "branch": branch,
                "tickets": tickets,
            })
    for d in out:
        out[d].sort(key=lambda c: c["ts"])
    return out


def attribute_commits(sessions, commits):
    """Attribute commits to sessions (groups): the owner is a session whose span contains the commit
    time and whose content mentions the ticket (or repo). The commit ticket is added to the owner's
    tickets (= that session's time also counts toward it). Returns the (modified) session list.
    커밋을 세션(그룹)에 귀속시킨다: 세션 구간이 커밋 시각을 포함하고, 그 세션 내용에
    해당 티켓(또는 repo)이 언급된 세션을 소유자로 본다. 소유 세션의 tickets 에 커밋
    티켓을 보강(= 그 세션 시간이 커밋 티켓으로도 집계됨). 반환: 세션 리스트(수정됨)."""
    ns = [s for s in sessions if not s.get("is_scheduled")]
    for c in commits:
        cdt = c.get("_dt")
        if cdt is None:
            cdt = parse_ts(c.get("ts"))
        ctks = c.get("tickets") or []
        if not ctks or cdt is None:
            continue
        repo = (c.get("repo") or "").lower()
        candidates = []
        for s in ns:
            if s["_start_dt"] <= cdt <= s["_end_dt"]:
                candidates.append(s)
        if not candidates:
            continue

        def score(s):
            content = set(s.get("content_tickets") or [])
            ticket_hit = len([t for t in ctks if t in content])
            proj = (s.get("project") or "").lower()
            repo_hit = 1 if (repo and proj and (repo in proj or proj in repo)) else 0
            span = (s["_end_dt"] - s["_start_dt"]).total_seconds()
            # More ticket mentions > repo match > shorter span (more specific)
            # 티켓 언급 많은 세션 > repo 일치 > 구간 짧은 세션(더 특정적)
            return (ticket_hit, repo_hit, -span)

        owner = max(candidates, key=score)
        # If no session matches the ticket or repo at all, do not attribute (protects reference-only mentions)
        # 티켓 또는 repo 가 전혀 안 걸리는 세션뿐이면 귀속하지 않음(참고용 보호)
        content = set(owner.get("content_tickets") or [])
        proj = (owner.get("project") or "").lower()
        if not any(t in content for t in ctks) and not (repo and proj and (repo in proj or proj in repo)):
            continue
        merged = sorted(set(owner["tickets"]) | set(ctks))
        owner["tickets"] = merged
        tb = owner.setdefault("ticket_basis", {})
        for t in ctks:
            tb.setdefault(t, [])
            if "commit" not in tb[t]:
                tb[t].append("commit")
    return sessions


# ──────────────────────────────────────────────────────────────────────────
# Ticket aggregation (per session group; scheduled sessions are excluded by the caller)
# 티켓 집계 (세션 그룹 단위, 예약 세션 제외는 호출부에서)
# ──────────────────────────────────────────────────────────────────────────

def aggregate_tickets(sessions, commits):
    """Group sessions (groups)/commits by ticket. No ticket -> ETC_KEY.
    세션(그룹)/커밋을 티켓별로 묶는다. 티켓 없으면 '기타'."""
    agg = {}

    def ensure(key):
        if key not in agg:
            agg[key] = {
                "ticket": key,
                "session_count": 0,
                "active_minutes": 0.0,     # Claude workload (parallel sum) / Claude 작업량(병렬 합산)
                "total_minutes": 0.0,      # total time (union) / 총 시간(합집합)
                "human_minutes": 0.0,      # my time (overwritten by compute_human) / 내 시간(compute_human 으로 덮어씀)
                "tokens_total": 0.0,
                "reaction_sum": 0.0,
                "commit_count": 0,
                "commit_messages": [],
                "branches": set(),
                "projects": set(),
                "cwds": set(),
                "sample_requests": [],
                "session_ids": [],
                "basis": set(),          # union of link basis (branch/title/prompt/commit) / 연결 근거 합집합(branch/title/prompt/commit)
                "shared_with": set(),    # other tickets sharing the same session (double counted) / 같은 세션을 공유한 다른 티켓(중복 계상)
                "tools": set(),          # tools that contributed to this ticket (Claude/Codex) / 이 티켓에 기여한 도구(Claude/Codex)
                "titles": set(),         # summary material: session titles / 요약 재료: 세션 제목들
                "prompts": [],           # summary material: human prompt excerpts / 요약 재료: 사람 프롬프트 발췌
            }
        return agg[key]

    for s in sessions:
        keys = s["tickets"] if s["tickets"] else [ETC_KEY]
        for k in keys:
            a = ensure(k)
            a["session_count"] += 1
            a["active_minutes"] += s["active_minutes"]
            a["total_minutes"] += s["total_minutes"]
            a["tokens_total"] += (s.get("tokens") or {}).get("total", 0)
            a["reaction_sum"] += s.get("reaction_delay_sum", 0.0)
            if s["git_branch"]:
                a["branches"].add(s["git_branch"])
            if s["project"]:
                a["projects"].add(s["project"])
            if s["cwd"]:
                a["cwds"].add(s["cwd"])
            if s["first_user_request"] and len(a["sample_requests"]) < 3:
                a["sample_requests"].append(s["first_user_request"])
            if s["session_id"]:
                a["session_ids"].append(s["session_id"])
            a["tools"].add(s.get("tool") or "Claude")
            for b in (s.get("ticket_basis") or {}).get(k, []):
                a["basis"].add(b)
            if len(keys) > 1:
                for other in keys:
                    if other != k:
                        a["shared_with"].add(other)
            if s.get("custom_title"):
                a["titles"].add(s["custom_title"])
            for hp in (s.get("human_samples") or []):
                if hp and hp not in a["prompts"] and len(a["prompts"]) < 5:
                    a["prompts"].append(hp)

    for c in commits:
        keys = c["tickets"] if c["tickets"] else [ETC_KEY]
        for k in keys:
            a = ensure(k)
            a["commit_count"] += 1
            if len(a["commit_messages"]) < 10:
                a["commit_messages"].append(c["message"])
            if c["branch"]:
                a["branches"].add(c["branch"])

    for k, a in agg.items():
        a["branches"] = sorted(a["branches"])
        a["projects"] = sorted(a["projects"])
        a["cwds"] = sorted(a["cwds"])
        a["basis"] = sorted(a["basis"])
        a["shared_with"] = sorted(x for x in a["shared_with"] if x != k)
        a["tools"] = sorted(a["tools"])
        a["titles"] = sorted(a["titles"])
        a["active_minutes"] = round(a["active_minutes"], 1)
        a["total_minutes"] = round(a["total_minutes"], 1)
        a["tokens_total"] = int(a["tokens_total"])
        a["reaction_sum"] = round(a["reaction_sum"], 1)
    return agg


def _ticket_stub(key, human_min):
    """Minimal entry for tickets that appear only in human.by_ticket.
    human.by_ticket 에만 등장하는 티켓을 위한 최소 엔트리."""
    return {
        "ticket": key, "session_count": 0, "active_minutes": 0.0,
        "total_minutes": 0.0, "human_minutes": round(human_min, 1),
        "tokens_total": 0, "reaction_sum": 0.0, "commit_count": 0,
        "commit_messages": [], "branches": [], "projects": [], "cwds": [],
        "sample_requests": [], "session_ids": [],
    }


# ──────────────────────────────────────────────────────────────────────────
# Estimate the human's ({{USER_DISPLAY_NAME}}) actual working time
# 사람({{USER_DISPLAY_NAME}}) 실제 작업 시간 추정
# ──────────────────────────────────────────────────────────────────────────

def _max_concurrent(intervals):
    evs = []
    for a, b in intervals:
        evs.append((a, 1))
        evs.append((b, -1))
    evs.sort(key=lambda x: (x[0], -x[1]))
    cur = mx = 0
    for _, delta in evs:
        cur += delta
        if cur > mx:
            mx = cur
    return mx


def _union_minutes(intervals):
    if not intervals:
        return 0.0
    ivs = sorted(intervals)
    total = 0.0
    cs, ce = ivs[0]
    for a, b in ivs[1:]:
        if a <= ce:
            if b > ce:
                ce = b
        else:
            total += (ce - cs).total_seconds()
            cs, ce = a, b
    total += (ce - cs).total_seconds()
    return total / 60.0


def compute_human(sessions, idle_gap_min, slot_min):
    """From human prompt timestamps compute 'actual worked time', work start/end, per-ticket human
    time, context switches, concurrent session count and the union of open sessions. Scheduled
    sessions excluded. (sessions are session groups, so concurrency counts real Claude Code sessions.)
    사람 프롬프트 타임스탬프로부터 '실제 일한 시간'·근무 시작/종료·티켓별 사람 시간·
    컨텍스트 스위칭·동시 세션 수·세션 열림 합집합을 계산한다. 예약 세션 제외.
    (sessions 는 세션 그룹 단위이므로 동시 세션 수가 실제 Claude Code 세션 기준이다.)"""
    ns = [s for s in sessions if not s.get("is_scheduled")]

    events = []
    for s in ns:
        tk = primary_human_ticket(s)
        for iso in s.get("human_times", []):
            dt = parse_ts(iso)
            if dt:
                events.append({"ts": dt, "session_id": s["session_id"], "ticket": tk})
    events.sort(key=lambda e: e["ts"])

    base = {
        "idle_gap_min": idle_gap_min, "slot_min": slot_min,
        "prompt_count": len(events),
        "active_minutes": 0.0, "active_hhmm": "0:00",
        "work_start": None, "work_end": None,
        "first_ts": None, "last_ts": None, "span_minutes": 0.0,
        "session_switch": 0, "ticket_switch": 0,
        "switches_per_hour": 0.0, "ticket_switches_per_hour": 0.0,
        "max_concurrent_sessions": 0, "avg_concurrent_sessions": 0.0,
        "session_open_union_minutes": 0.0, "wall_sum_minutes": 0.0,
        "by_ticket": {}, "timeline": {}, "events": [],
    }

    intervals = []
    for s in ns:
        a = parse_ts(s.get("start_ts"))
        b = parse_ts(s.get("end_ts"))
        if a and b and b >= a:
            intervals.append((a, b))
    base["max_concurrent_sessions"] = _max_concurrent(intervals)
    union = _union_minutes(intervals)
    base["session_open_union_minutes"] = round(union, 1)
    base["session_open_union_hhmm"] = minutes_to_hhmm(union)
    wall_sum = sum((b - a).total_seconds() for a, b in intervals) / 60.0
    base["wall_sum_minutes"] = round(wall_sum, 1)
    base["avg_concurrent_sessions"] = round(wall_sum / union, 2) if union > 0 else 0.0

    if not events:
        return base

    slot = timedelta(minutes=slot_min)
    gap = timedelta(minutes=idle_gap_min)

    segs = []
    seg_start = events[0]["ts"]
    seg_last = events[0]["ts"]
    for e in events[1:]:
        if e["ts"] - seg_last <= gap:
            seg_last = e["ts"]
        else:
            segs.append((seg_start, seg_last))
            seg_start = e["ts"]
            seg_last = e["ts"]
    segs.append((seg_start, seg_last))

    ev_ts = [e["ts"] for e in events]

    def ticket_at(t):
        i = bisect.bisect_right(ev_ts, t) - 1
        return events[i]["ticket"] if i >= 0 else ETC_KEY

    by_ticket = {}
    timeline = {}
    total = 0.0
    for (a, b) in segs:
        end = b + slot
        s = a
        while s < end:
            cred = min(float(slot_min), (end - s).total_seconds() / 60.0)
            tk = ticket_at(s)
            by_ticket[tk] = by_ticket.get(tk, 0.0) + cred
            hr = s.strftime("%H")
            timeline.setdefault(hr, {})
            timeline[hr][tk] = timeline[hr].get(tk, 0.0) + cred
            total += cred
            s = s + slot

    sess_sw = tk_sw = 0
    for p, q in zip(events, events[1:]):
        if q["ts"] - p["ts"] <= gap:
            if q["session_id"] != p["session_id"]:
                sess_sw += 1
            if q["ticket"] != p["ticket"]:
                tk_sw += 1

    first = events[0]["ts"]
    last = events[-1]["ts"]
    hrs = total / 60.0 if total > 0 else 0.0

    base.update({
        "active_minutes": round(total, 1),
        "active_hhmm": minutes_to_hhmm(total),
        "work_start": first.strftime("%H:%M"),
        "work_end": last.strftime("%H:%M"),
        "first_ts": first.isoformat(),
        "last_ts": last.isoformat(),
        "span_minutes": round((last - first).total_seconds() / 60.0, 1),
        "span_hhmm": minutes_to_hhmm((last - first).total_seconds() / 60.0),
        "session_switch": sess_sw,
        "ticket_switch": tk_sw,
        "switches_per_hour": round(sess_sw / hrs, 1) if hrs else 0.0,
        "ticket_switches_per_hour": round(tk_sw / hrs, 1) if hrs else 0.0,
        "by_ticket": {k: round(v, 1) for k, v in by_ticket.items()},
        "timeline": {h: {k: round(v, 1) for k, v in dd.items()}
                     for h, dd in timeline.items()},
        "events": [{"ts": e["ts"].isoformat(), "session_id": e["session_id"],
                    "ticket": e["ticket"]} for e in events],
    })
    return base


# ──────────────────────────────────────────────────────────────────────────
# Main
# 메인
# ──────────────────────────────────────────────────────────────────────────

def _median(xs):
    if not xs:
        return 0.0
    ys = sorted(xs)
    n = len(ys)
    m = n // 2
    return round(ys[m] if n % 2 else (ys[m - 1] + ys[m]) / 2, 2)


def _strip_internal(s):
    """Remove non-serializable/internal-only keys from a session dict.
    세션 dict 에서 직렬화 불가/내부 전용 키 제거."""
    s = dict(s)
    s.pop("_start_dt", None)
    s.pop("_end_dt", None)
    return s


def build_report(target_dates, label_date):
    tracking_start = load_tracking_start()
    if tracking_start:
        target_dates = {d for d in target_dates if d >= tracking_start}
    if not target_dates:
        return {
            "date": label_date, "dates": [], "tracking_start_date": tracking_start,
            "note": t(f"dates before tracking_start_date({tracking_start}) are ignored",
                      f"tracking_start_date({tracking_start}) 이전 날짜는 무시됨"),
            "sessions": [], "commits": [], "tickets": {},
            "human": compute_human([], IDLE_GAP_MIN, HUMAN_SLOT_MIN), "human_events": [],
            "metrics": {"tokens": {"input": 0, "output": 0, "cache": 0, "total": 0},
                        "reaction_delay_sum_min": 0.0, "reaction_delay_count": 0,
                        "reaction_delay_median_min": 0.0, "reaction_delays": [],
                        "non_ticket_active_minutes": 0.0, "non_ticket_session_count": 0},
            "non_ticket": [],
            "totals": {"session_count": 0, "scheduled_session_count": 0,
                       "active_minutes": 0.0, "active_hhmm": "0:00",
                       "commit_count": 0, "ticket_count": 0, "ticket_keys": []},
        }

    sess_by_date = collect_sessions(target_dates)
    codex_by_date = collect_codex_sessions(target_dates)
    commits_by_date = collect_commits(target_dates)

    # Merge Claude sessions and the user's direct Codex sessions into one list for the same pipeline.
    # Claude 세션 + 사용자 직접 Codex 세션을 하나의 세션 리스트로 합쳐 동일 파이프라인에 태운다.
    all_sessions = [s for d in target_dates for s in sess_by_date.get(d, [])]
    all_sessions += [s for d in target_dates for s in codex_by_date.get(d, [])]
    all_sessions.sort(key=lambda s: s["start_ts"])
    all_commits = [c for d in target_dates for c in commits_by_date.get(d, [])]

    # Attribute commits to sessions (so session time also counts toward commit tickets)
    # 커밋을 세션에 귀속(커밋 티켓으로 세션 시간도 집계되게 보강)
    attribute_commits(all_sessions, all_commits)

    # Scheduled-run sessions are excluded from all totals.
    # 예약 실행 세션은 모든 합계에서 제외.
    non_sched = [s for s in all_sessions if not s.get("is_scheduled")]
    tickets = aggregate_tickets(non_sched, all_commits)

    total_active = round(sum(s["active_minutes"] for s in non_sched), 1)

    human = compute_human(all_sessions, IDLE_GAP_MIN, HUMAN_SLOT_MIN)
    for k, mins in human.get("by_ticket", {}).items():
        if k in tickets:
            tickets[k]["human_minutes"] = round(mins, 1)
        else:
            tickets[k] = _ticket_stub(k, mins)
    human_events = human.pop("events", [])

    # Transcript-based metrics: tokens, reaction delay, non-ticket work (scheduled sessions excluded)
    # transcript 기반 지표: 토큰·반응지연·티켓 외 작업(예약 세션 제외)
    tok = {"input": 0, "output": 0, "cache": 0}
    delays = []
    for s in non_sched:
        tks = s.get("tokens") or {}
        tok["input"] += tks.get("input", 0)
        tok["output"] += tks.get("output", 0)
        tok["cache"] += tks.get("cache", 0)
        delays.extend(s.get("reaction_delays") or [])
    tok["total"] = tok["input"] + tok["output"] + tok["cache"]

    non_ticket = []
    for s in non_sched:
        if s["tickets"] or s.get("human_prompt_count", 0) <= 0:
            continue
        sdt = parse_ts(s.get("start_ts"))
        non_ticket.append({
            "label": s.get("label") or UNTITLED,
            "session_id": s["session_id"],
            "tool": s.get("tool") or "Claude",
            "date": sdt.strftime("%Y-%m-%d") if sdt else label_date,
            "total_minutes": s["total_minutes"],
            "claude_minutes": s["active_minutes"],
            "human_minutes": s.get("human_active_minutes", 0.0),
            "wall_minutes": s["wall_minutes"],
            "tokens_total": (s.get("tokens") or {}).get("total", 0),
            "reaction_sum": s.get("reaction_delay_sum", 0.0),
            "start": s["start"], "end": s["end"],
            "mixed_candidate": s.get("mixed_candidate", False),
            # Summary material: session title, first request, human prompt excerpts (incl. extended excerpts for mixed judgment)
            # 요약 재료: 세션 제목·첫 요청·사람 프롬프트 발췌(혼합 판단용 확장 발췌 포함)
            "title": s.get("custom_title") or "",
            "first_request": s.get("first_user_request") or "",
            "samples": s.get("human_samples") or [],
            "samples_more": s.get("human_samples_more") or [],
        })
    non_ticket.sort(key=lambda x: -x["human_minutes"])
    metrics = {
        "tokens": tok,
        "reaction_delay_sum_min": round(sum(delays), 1),
        "reaction_delay_count": len(delays),
        "reaction_delay_median_min": _median(delays),
        "reaction_delays": [round(x, 2) for x in delays],
        "non_ticket_active_minutes": round(sum(x["total_minutes"] for x in non_ticket), 1),
        "non_ticket_session_count": len(non_ticket),
    }

    report = {
        "date": label_date,
        "dates": sorted(target_dates),
        "tracking_start_date": tracking_start,
        "generated_at": datetime.now().astimezone().isoformat(),
        "timezone": datetime.now().astimezone().strftime("%Z%z"),
        "gap_threshold_min": GAP_THRESHOLD_MIN,
        "idle_gap_min": IDLE_GAP_MIN,
        "human_slot_min": HUMAN_SLOT_MIN,
        "repo_roots": REPO_ROOTS,
        "sessions": [_strip_internal(s) for s in all_sessions],
        "commits": [{k: v for k, v in c.items() if k != "_dt"} for c in all_commits],
        "tickets": tickets,
        "human": human,
        "human_events": human_events,
        "metrics": metrics,
        "non_ticket": non_ticket,
        "totals": {
            "session_count": len(non_sched),
            "scheduled_session_count": len(all_sessions) - len(non_sched),
            "active_minutes": total_active,
            "active_hhmm": minutes_to_hhmm(total_active),
            "human_active_minutes": human.get("active_minutes", 0.0),
            "human_active_hhmm": human.get("active_hhmm", "0:00"),
            "work_start": human.get("work_start"),
            "work_end": human.get("work_end"),
            "session_open_union_minutes": human.get("session_open_union_minutes", 0.0),
            "tokens_total": tok["total"],
            "reaction_delay_median_min": metrics["reaction_delay_median_min"],
            "non_ticket_active_minutes": metrics["non_ticket_active_minutes"],
            "commit_count": len(all_commits),
            "ticket_count": len([k for k in tickets if k != ETC_KEY]),
            "ticket_keys": sorted([k for k in tickets if k != ETC_KEY]),
        },
    }
    if len(target_dates) > 1:
        report["per_date"] = {}
        for d in sorted(target_dates):
            day_sessions = sess_by_date.get(d, [])
            day_non_sched = [s for s in day_sessions if not s.get("is_scheduled")]
            dh = compute_human(day_sessions, IDLE_GAP_MIN, HUMAN_SLOT_MIN)
            report["per_date"][d] = {
                "session_count": len(day_non_sched),
                "active_minutes": round(sum(s["active_minutes"] for s in day_non_sched), 1),
                "commit_count": len(commits_by_date.get(d, [])),
                "human_active_minutes": dh.get("active_minutes", 0.0),
                "work_start": dh.get("work_start"),
                "work_end": dh.get("work_end"),
                "session_switch": dh.get("session_switch", 0),
            }
    return report


def main():
    ap = argparse.ArgumentParser(description=t("Work-journal collector", "업무 일지 자동 수집기"))
    ap.add_argument("--date", help=t("YYYY-MM-DD (local). Defaults to the previous weekday",
                                            "YYYY-MM-DD (로컬). 생략 시 직전 평일"))
    ap.add_argument("--range", help=t("YYYY-MM-DD:YYYY-MM-DD (range sum, e.g. weekly)",
                                             "YYYY-MM-DD:YYYY-MM-DD (기간 합산, weekly 등)"))
    ap.add_argument("--pretty", action="store_true", help=t("Pretty-printed JSON", "보기 좋은 JSON"))
    args = ap.parse_args()

    if args.range:
        try:
            a, b = args.range.split(":")
            start = datetime.strptime(a.strip(), "%Y-%m-%d").date()
            end = datetime.strptime(b.strip(), "%Y-%m-%d").date()
        except Exception:
            print(t("Invalid --range format. e.g. 2026-10-08:2026-10-14",
                    "잘못된 --range 형식. 예: 2026-10-08:2026-10-14"), file=sys.stderr)
            sys.exit(2)
        if end < start:
            start, end = end, start
        dates = set()
        cur = start
        while cur <= end:
            dates.add(cur.strftime("%Y-%m-%d"))
            cur += timedelta(days=1)
        label = f"{start.isoformat()}~{end.isoformat()}"
        report = build_report(dates, label)
    else:
        if args.date:
            try:
                d = datetime.strptime(args.date.strip(), "%Y-%m-%d").date()
            except Exception:
                print(t("Invalid --date format. e.g. 2026-10-08",
                        "잘못된 --date 형식. 예: 2026-10-08"), file=sys.stderr)
                sys.exit(2)
        else:
            d = previous_weekday(datetime.now().astimezone().date())
        label = d.strftime("%Y-%m-%d")
        report = build_report({label}, label)

    indent = 2 if args.pretty else None
    print(json.dumps(report, ensure_ascii=False, indent=indent))


if __name__ == "__main__":
    main()
