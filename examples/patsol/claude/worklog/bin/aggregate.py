#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Work-journal cumulative/dashboard aggregator.
업무 일지 누적/대시보드 집계기 (work-journal aggregator)

Treats state.json as the single source of truth: merges one day's data (collect.py
auto-collection + human answers) and deterministically (no mental math) computes and
prints ▶ per-ticket cumulative time ▶ cumulative dashboard (week/month/all) ▶ Notion
table markdown. Standard library only.
state.json을 "단일 진실원천"으로 삼아, 하루치 데이터(collect.py 자동수집 + 사람 답변)를
병합하고 ▶ 티켓별 누적시간 ▶ 누적 대시보드(주/월/전체) ▶ Notion 표 마크다운 을
모두 결정적으로(암산 없이) 계산해 출력한다. 표준 라이브러리만 사용.

Key point: build *replaces* state.daily[date] wholesale, so re-running the same date
never double-counts (idempotent). Cumulatives/dashboard are recomputed from all of
state.daily every time.
핵심: build 는 state.daily[date] 를 통째로 "교체"하므로 같은 날짜를 다시 돌려도
이중 계상되지 않는다(멱등). 누적/대시보드는 매번 state.daily 전체에서 재계산한다.

Two kinds of human time are distinguished:
  - my time (human_minutes): time a person actually spent attending to a ticket
    (auto-estimated by collect.py). The key metric. Arrives via the day["human"] block
    and tickets[KEY]["human_minutes"].
  - off-session time (planning/research/discussion/etc): planning/research/discussion/
    other time spent outside sessions (human input). The existing TIME_KEYS. Total/ratio
    formulas keep using these.
두 종류의 사람 시간을 구분한다:
  - 내 시간(human_minutes): 사람이 실제로 티켓에 주의를 쓴 시간(collect.py 자동 추정).
    핵심 지표. day["human"] 블록과 tickets[KEY]["human_minutes"] 로 들어온다.
  - 세션 밖 시간(planning/research/discussion/etc): 세션 밖에서 쓴 기획/이해·조사/논의/
    기타 시간(사람 입력). 기존 TIME_KEYS. 합계/비율 formula 는 이 값들로 유지한다.

Usage / 사용:
    # Merge one day + recompute + save state + print result (JSON)
    # 하루치 병합 + 재계산 + state 저장 + 결과(JSON) 출력
    python3 aggregate.py build --date 2026-10-08 --input /path/day.json [--mode auto|interactive]

    # Recompute and print only the dashboard markdown, without modifying state
    # state 수정 없이 대시보드만 재계산해 마크다운 출력
    python3 aggregate.py dashboard [--asof 2026-10-08]

    # Print ticket cumulatives only
    # 티켓 누적만 출력
    python3 aggregate.py cumulatives

day.json schema (example) / day.json 스키마(예):
(Korean values such as "기타" and "진행 중" are real data: the catch-all ticket key from
collect.py and Jira workflow status names.)
{
  "retro": "Focused morning, flow broken by afternoon discussions",
  "plan": ["{{JIRA_PROJECT_KEY}}-123 cost analysis draft", "{{JIRA_PROJECT_KEY}}-124 channel priorities"],
  "human": { "active_minutes": 289.1, "work_start":"09:32", "work_end":"17:58",
             "session_switch": 44, "ticket_switch": 14, "switches_per_hour": 9.1,
             "max_concurrent_sessions": 12, "avg_concurrent_sessions": 3.6,
             "session_open_union_minutes": 755.0, "by_ticket": {...},
             "timeline": {"09": {"기타": 5.0}, ...} },
  "tickets": {
    "{{JIRA_PROJECT_KEY}}-123": {
      "summary":"Simplify infrastructure",
      "jira_url":"https://{{JIRA_SITE}}/browse/{{JIRA_PROJECT_KEY}}-123",
      "status":"진행 중",
      "claude": 47, "human_minutes": 30,
      "planning": 30, "research": 20, "discussion": 15, "etc": 0,
      "commits": 2, "sessions": 3,
      "progress_pct": 60,
      "status_change": "해야 할 일→진행 중",
      "progress":"...", "blocked":"...", "blocked_min": 0,
      "decisions":"...", "next":"..."
    }
  }
}
Time values are in minutes. Missing fields are treated as 0/empty (backward compatible).
시간 값 단위는 분(minute). 누락 필드는 0/빈값으로 처리(하위호환).
"""

import argparse
import json
import os
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

STATE_PATH = os.environ.get("WORKLOG_STATE", os.path.expanduser("~/.claude/worklog/state.json"))

TIME_KEYS = ["claude", "planning", "research", "discussion", "etc"]
TIME_LABELS = {
    "claude": t("Claude work (parallel sum)", "Claude 작업량(병렬 합산)"),
    "planning": t("Planning", "기획"),
    "research": t("Research", "이해·조사"),
    "discussion": t("Discussion", "논의"),
    "etc": t("Other", "기타"),
}
# Human-entered qualitative/off-session fields preserved on reaggregate (not auto metrics).
# Text fields: decisions/blocked/next; numeric fields: planning/research/discussion/etc/blocked_min.
# 재집계(reaggregate) 때 사람이 입력한 질적/세션 밖 필드 — 자동 수치가 아니므로 보존한다.
# 텍스트 필드: decisions/blocked/next, 수치 필드: planning/research/discussion/etc/blocked_min.
HUMAN_TICKET_TEXT_FIELDS = ["decisions", "blocked", "next"]
HUMAN_TICKET_NUM_FIELDS = ["planning", "research", "discussion", "etc", "blocked_min"]
# Jira "Done" status name in the Korean workspace schema — must match exactly, do not translate.
DONE_STATUS = "완료"
# Catch-all ticket key emitted by collect.py (data key, not a label) — do not translate.
ETC_KEY = "기타"
# Notion "작업" DB kind select values (config.json kind_values) — must match the schema.
KIND_TICKET = "티켓"
KIND_NON_TICKET = "티켓 외"
# Dashboard heading used to locate the section on the Notion page (config.json
# dashboard_heading) — must match the live page, do not translate.
DASHBOARD_HEADING = "📈 누적 대시보드"
BAR_LEN = 10

# ──────────────────────────────────────────────────────────────────────────

def load_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            st = json.load(f)
    except FileNotFoundError:
        st = {}
    st.setdefault("last_processed_date", None)
    st.setdefault("processed_dates", [])
    st.setdefault("backfill_max", 5)
    st.setdefault("last_run_at", None)
    st.setdefault("runs", [])
    st.setdefault("daily", {})
    return st


def save_state(st):
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_PATH)


def num(v):
    try:
        if v is None or v == "":
            return 0.0
        return float(v)
    except Exception:
        return 0.0


def mins_to_hhmm(m):
    m = int(round(num(m)))
    return f"{m // 60}:{m % 60:02d}"


def pct(part, whole):
    whole = num(whole)
    if whole <= 0:
        return 0.0
    return round(num(part) / whole * 1000) / 10


def bar(p):
    p = max(0.0, min(100.0, num(p)))
    filled = int(round(p / 100 * BAR_LEN))
    return "▓" * filled + "░" * (BAR_LEN - filled) + f" {int(round(p))}%"


def _density_cell(v):
    """Minutes → density glyph + number. 4 levels (▁▃▅▇) based on 60 min/hour.
    분 → 진하기 글리프 + 숫자. 시간당 60분 기준 4단계(▁▃▅▇)."""
    v = num(v)
    if v <= 0:
        return "·"
    if v < 15:
        g = "▁"
    elif v < 30:
        g = "▃"
    elif v < 45:
        g = "▅"
    else:
        g = "▇"
    return f"{g} {int(round(v))}"


def esc(s):
    """Minimal escaping (special chars) for Notion markdown table cells.
    Notion 마크다운 표 셀용 최소 이스케이프(특수문자)."""
    s = "" if s is None else str(s)
    for ch in ["\\", "*", "~", "`", "[", "]", "<", ">", "{", "}", "|", "^"]:
        s = s.replace(ch, "\\" + ch)
    return s.replace("\n", " ").strip()


# ──────────────────────────────────────────────────────────────────────────
# Date utils / 날짜 유틸
# ──────────────────────────────────────────────────────────────────────────

def d(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


# ──────────────────────────────────────────────────────────────────────────
# Aggregation / 집계
# ──────────────────────────────────────────────────────────────────────────

def ticket_cumulatives(daily):
    """Recompute per-ticket cumulatives from all of state.daily.
    state.daily 전체에서 티켓별 누적을 재계산."""
    cum = {}
    for dstr in sorted(daily.keys()):
        day = daily[dstr]
        for key, t in (day.get("tickets") or {}).items():
            c = cum.setdefault(key, {
                "ticket": key,
                "claude": 0.0, "planning": 0.0, "research": 0.0,
                "discussion": 0.0, "etc": 0.0,
                "my_minutes": 0.0,
                "session_total_min": 0.0, "tokens": 0.0, "reaction_sum": 0.0,
                "commits": 0.0, "sessions": 0.0,
                "blocked_count": 0, "blocked_min": 0.0,
                "start_date": dstr, "done_date": None,
                "status": None, "summary": "", "jira_url": "",
                "latest_date": dstr, "blocked": "",
                "basis": set(), "shared_with": set(), "tools": set(),
            })
            for k in TIME_KEYS:
                c[k] += num(t.get(k))
            c["my_minutes"] += num(t.get("human_minutes"))
            c["session_total_min"] += num(t.get("total_minutes"))
            c["tokens"] += num(t.get("tokens"))
            c["reaction_sum"] += num(t.get("reaction_sum"))
            c["commits"] += num(t.get("commits"))
            c["sessions"] += num(t.get("sessions"))
            c["basis"] |= set(t.get("basis") or [])
            c["shared_with"] |= set(t.get("shared_with") or [])
            c["tools"] |= set(t.get("tools") or [])
            if (t.get("blocked") or "").strip():
                c["blocked_count"] += 1
                c["blocked_min"] += num(t.get("blocked_min"))
            if dstr < c["start_date"]:
                c["start_date"] = dstr
            if dstr >= c["latest_date"]:
                c["latest_date"] = dstr
                # Latest status/summary/link come from the most recent date.
                # 최신 상태/요약/링크는 가장 최근 날짜 기준
                if t.get("status"):
                    c["status"] = t.get("status")
                if t.get("summary"):
                    c["summary"] = t.get("summary")
                if t.get("jira_url"):
                    c["jira_url"] = t.get("jira_url")
                if (t.get("blocked") or "").strip():
                    c["blocked"] = t.get("blocked")
    # Done date / total time / ratios
    # 완료일/총시간/비율
    for key, c in cum.items():
        total = sum(c[k] for k in TIME_KEYS)
        c["total_min"] = total
        human = total - c["claude"]          # off-session human input (planning+research+discussion+other) / 세션 밖 사람 입력(기획+이해+논의+기타)
        c["human_min"] = human
        c["human_pct"] = pct(human, total)
        c["my_minutes"] = round(c["my_minutes"], 1)
        c["session_total_min"] = round(c["session_total_min"], 1)
        c["tokens"] = int(round(c["tokens"]))
        c["reaction_sum"] = round(c["reaction_sum"], 1)
        c["basis"] = sorted(c["basis"])
        c["shared_with"] = sorted(x for x in c["shared_with"] if x != key)
        c["tools"] = sorted(c["tools"]) or ["Claude"]
        # done_date: latest date if the latest status is Done, else None.
        # done_date: 최신 상태가 완료면 최신 날짜, 아니면 None
        if c["status"] == DONE_STATUS:
            c["done_date"] = c["latest_date"]
        else:
            c["done_date"] = None
        if c["done_date"]:
            try:
                c["lead_days"] = (d(c["done_date"]) - d(c["start_date"])).days
            except Exception:
                c["lead_days"] = None
        else:
            c["lead_days"] = None
    return cum


def day_totals(day):
    tot = {k: 0.0 for k in TIME_KEYS}
    tot["commits"] = 0.0
    tot["sessions"] = 0.0
    tot["human_minutes"] = 0.0
    for key, t in (day.get("tickets") or {}).items():
        for k in TIME_KEYS:
            tot[k] += num(t.get(k))
        tot["commits"] += num(t.get("commits"))
        tot["sessions"] += num(t.get("sessions"))
        tot["human_minutes"] += num(t.get("human_minutes"))
    tot["total_min"] = sum(tot[k] for k in TIME_KEYS)
    # The day's "my time" total equals the sum attributed to tickets (= human block active);
    # prefer the human block value when present.
    # 하루의 '내 시간' 합계는 티켓 귀속 합(=human 블록 active)과 같다. human 블록이 있으면 그 값 우선.
    h = day.get("human") or {}
    if h.get("active_minutes") is not None:
        tot["my_minutes"] = round(num(h.get("active_minutes")), 1)
    else:
        tot["my_minutes"] = round(tot["human_minutes"], 1)
    return tot


# ──────────────────────────────────────────────────────────────────────────
# Markdown rendering / 마크다운 렌더
# ──────────────────────────────────────────────────────────────────────────

def render_daily_table(day):
    """📊 Today's metrics table (Notion-flavored markdown). "My time" is the leading key metric.
    📊 오늘 수치 표(Notion-flavored markdown). '내 시간'이 맨 앞 핵심 지표."""
    tickets = day.get("tickets") or {}
    keys = sorted(tickets.keys(), key=lambda k: (k == ETC_KEY, k))
    total_lbl = t("Total", "합계")
    cols = ([t("Ticket", "티켓"), t("My time", "내 시간")] + [TIME_LABELS[k] for k in TIME_KEYS]
            + [total_lbl, t("Progress", "진행률"), t("Commits", "커밋"), t("Sessions", "세션"),
               t("Status change", "상태 변화")])
    lines = ['<table fit-page-width="true" header-row="true">']
    lines.append("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in cols) + "</tr>")
    grand = {k: 0.0 for k in TIME_KEYS}
    gmy = 0.0
    gcommit = gsession = 0.0
    for key in keys:
        tk = tickets[key]  # named tk so it doesn't shadow t() / t() 가리지 않도록 tk
        row_total = sum(num(tk.get(k)) for k in TIME_KEYS)
        for k in TIME_KEYS:
            grand[k] += num(tk.get(k))
        gmy += num(tk.get("human_minutes"))
        gcommit += num(tk.get("commits"))
        gsession += num(tk.get("sessions"))
        cells = [esc(key), mins_to_hhmm(tk.get("human_minutes"))]
        cells += [mins_to_hhmm(tk.get(k)) for k in TIME_KEYS]
        cells.append(mins_to_hhmm(row_total))
        cells.append(esc(bar(tk.get("progress_pct", 0))))
        cells.append(str(int(num(tk.get("commits")))))
        cells.append(str(int(num(tk.get("sessions")))))
        cells.append(esc(tk.get("status_change", "")) or "-")
        lines.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    grand_total = sum(grand[k] for k in TIME_KEYS)
    # Day "my time" total prefers the human block's active value (same as ticket-attributed sum).
    # 하루 '내 시간' 합계는 human 블록 active 우선(티켓 귀속 합과 동일)
    h = day.get("human") or {}
    my_total = num(h.get("active_minutes")) if h.get("active_minutes") is not None else gmy
    # Total row / 합계 행
    sumc = [f"**{total_lbl}**", f"**{mins_to_hhmm(my_total)}**"] + [f"**{mins_to_hhmm(grand[k])}**" for k in TIME_KEYS]
    sumc += [f"**{mins_to_hhmm(grand_total)}**", "-", f"**{int(gcommit)}**", f"**{int(gsession)}**", "-"]
    lines.append('<tr color="gray_bg">' + "".join(f"<td>{c}</td>" for c in sumc) + "</tr>")
    # Ratio row (by time type; "my time" is a separate metric, so '-').
    # 비율 행(시간 유형 기준; 내 시간은 별도 지표라 '-')
    ratc = [t("Ratio", "비율"), "-"] + [f"{pct(grand[k], grand_total)}%" for k in TIME_KEYS]
    ratc += ["100%", "-", "-", "-", "-"]
    lines.append("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in ratc) + "</tr>")
    lines.append("</table>")
    return "\n".join(lines)


def render_work_timeline(day):
    """🕘 Work timeline: one summary line + hour × ticket table (cell = minutes + density). '' if no data.
    🕘 근무 타임라인: 요약 한 줄 + 시간대 × 티켓 표(셀=분 + 진하기). 데이터 없으면 ''."""
    h = day.get("human") or {}
    tl = h.get("timeline") or {}
    by = h.get("by_ticket") or {}
    if not tl:
        return ""
    # Columns: top-5 tickets by my time (excluding the catch-all) + the catch-all.
    # 열: 내 시간 상위 5 티켓(기타 제외) + 기타
    non_etc = sorted([(k, v) for k, v in by.items() if k != ETC_KEY], key=lambda x: -x[1])[:5]
    cols = [k for k, _ in non_etc]
    if ETC_KEY in by:
        cols.append(ETC_KEY)
    if not cols:
        cols = sorted(by.keys())
    hours = sorted(tl.keys())

    L = []
    L.append(t("### 🕘 Work timeline", "### 🕘 근무 타임라인"))
    active = h.get('active_hhmm') or mins_to_hhmm(h.get('active_minutes'))
    opened = h.get('session_open_union_hhmm') or mins_to_hhmm(h.get('session_open_union_minutes'))
    sw_n = int(num(h.get('session_switch')))
    sw_h = h.get('switches_per_hour', 0)
    mx = int(num(h.get('max_concurrent_sessions')))
    avg = h.get('avg_concurrent_sessions', 0)
    summary = t(
        f"- Actual working time **{active}** · sessions open {opened}"
        f" · {sw_n} switches ({sw_h}/hour) · max concurrent sessions {mx} (avg {avg})",
        f"- 실제 일한 시간 **{active}** · 세션 열림 {opened}"
        f" · 스위칭 {sw_n}회(시간당 {sw_h}) · 최대 동시 세션 {mx} (평균 {avg})",
    )
    L.append(summary)

    tbl = ['<table fit-page-width="true" header-row="true">']
    head = [t("Hour", "시간대")] + cols + [t("Sum", "계")]
    tbl.append("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in head) + "</tr>")
    coltot = {c: 0.0 for c in cols}
    for hr in hours:
        row = tl[hr]
        cells = [f"{hr}:00"]
        rowtot = 0.0
        for c in cols:
            v = num(row.get(c, 0))
            rowtot += v
            coltot[c] += v
            cells.append(_density_cell(v))
        cells.append(mins_to_hhmm(rowtot))
        tbl.append("<tr>" + "".join(f"<td>{esc(x)}</td>" for x in cells) + "</tr>")
    foot = [f"**{t('Total', '합계')}**"] + [f"**{mins_to_hhmm(coltot[c])}**" for c in cols] + [f"**{mins_to_hhmm(sum(coltot.values()))}**"]
    tbl.append('<tr color="gray_bg">' + "".join(f"<td>{x}</td>" for x in foot) + "</tr>")
    tbl.append("</table>")
    L.append("\n".join(tbl))
    return "\n\n".join(L)


def _fmt_md(dstr):
    """YYYY-MM-DD → MM/DD (original on failure).
    YYYY-MM-DD → MM/DD (실패 시 원문)."""
    try:
        return d(dstr).strftime("%m/%d")
    except Exception:
        return dstr or "-"


def _ticket_period(c):
    """Ticket work period: start~done (lead N days) if done, else start~ongoing (N days).
    티켓 작업 기간: 완료면 시작~완료(리드N일), 진행 중이면 시작~진행(N일)."""
    start = c.get("start_date")
    if not start:
        return "-"
    if c.get("done_date"):
        base = f"{_fmt_md(start)}~{_fmt_md(c['done_date'])}"
        ld = c.get("lead_days")
        return base + (t(f" ({ld}d)", f" ({ld}일)") if ld is not None else "")
    latest = c.get("latest_date") or start
    try:
        days = (d(latest) - d(start)).days + 1
    except Exception:
        days = 1
    return t(f"{_fmt_md(start)}~ongoing ({days}d)", f"{_fmt_md(start)}~진행 ({days}일)")


def _hbar(value, maxv, width=12):
    """Render a 0~maxv value as a text bar of the given width.
    0~maxv 값을 폭 width의 텍스트 막대로."""
    maxv = num(maxv)
    if maxv <= 0:
        return "░" * width
    filled = int(round(num(value) / maxv * width))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def _collect_non_ticket(daily, start, end):
    """Sum in-range non-ticket work by label (session title / first prompt).
    범위 내 '티켓 외 작업'을 라벨(세션 제목·첫 프롬프트) 단위로 합산."""
    agg = {}
    for dstr in sorted(daily.keys()):
        try:
            dd = d(dstr)
        except Exception:
            continue
        if not (start <= dd <= end):
            continue
        for it in (daily[dstr].get("non_ticket") or []):
            untitled = t("(untitled)", "(제목 없음)")
            label = (it.get("label") or untitled).strip() or untitled
            a = agg.setdefault(label, {
                "label": label, "total": 0.0, "claude": 0.0, "human": 0.0,
                "tokens": 0.0, "reaction_sum": 0.0, "count": 0,
                "first": dstr, "last": dstr,
                "tools": set(), "mixed": False,
            })
            # Fall back to claude_minutes when total_minutes is missing (old data).
            # total_minutes 없으면(구버전 데이터) claude_minutes 로 대체
            a["total"] += num(it.get("total_minutes", it.get("claude_minutes")))
            a["claude"] += num(it.get("claude_minutes"))
            a["human"] += num(it.get("human_minutes"))
            a["tokens"] += num(it.get("tokens_total"))
            a["reaction_sum"] += num(it.get("reaction_sum"))
            a["count"] += 1
            a["tools"].add(it.get("tool") or "Claude")
            if it.get("mixed"):
                a["mixed"] = True
            if dstr < a["first"]:
                a["first"] = dstr
            if dstr >= a["last"]:
                a["last"] = dstr
    for a in agg.values():
        a["tools"] = sorted(a["tools"]) or ["Claude"]
    return sorted(agg.values(), key=lambda x: -x["human"])


def _collect_manual(daily):
    """Sum per-date day['manual'] (manual work rows entered by a person) by name.
    Keeps offline activities not auto-collected from sessions/commits (e.g. attending an
    external conference) as-is in the "작업" DB and dashboard. Not included in day_totals /
    ticket cumulatives (avoids double counting). Item schema (minutes): name, total_min,
    my_min, claude_min, reaction_min, tokens, sessions, tool, summary, note, date (or
    first_date/last_date).
    날짜별 day['manual'](사람이 직접 넣은 수동 작업 행)을 작업명(name) 단위로 합산.
    세션/커밋으로 자동 수집되지 않는 오프라인 활동(예: 외부 컨퍼런스 참석)을 '작업' DB·
    대시보드에 그대로 남기기 위한 항목. day_totals/티켓 누적에는 들어가지 않는다(이중계상 방지).
    각 항목 스키마(분 단위): name, total_min, my_min, claude_min, reaction_min, tokens,
    sessions, tool, summary, note, date(또는 first_date/last_date)."""
    agg = {}
    for dstr in sorted(daily.keys()):
        for it in (daily[dstr].get("manual") or []):
            name = (it.get("name") or "").strip()
            if not name:
                continue
            fd = it.get("first_date") or it.get("date") or dstr
            ld = it.get("last_date") or it.get("date") or dstr
            a = agg.setdefault(name, {
                "name": name, "total_min": 0.0, "my_min": 0.0, "claude_min": 0.0,
                "reaction_min": 0.0, "tokens": 0.0, "sessions": 0.0,
                "first": fd, "last": ld, "summary": "", "note": "",
                "tools": set(),
            })
            a["total_min"] += num(it.get("total_min"))
            a["my_min"] += num(it.get("my_min"))
            a["claude_min"] += num(it.get("claude_min"))
            a["reaction_min"] += num(it.get("reaction_min"))
            a["tokens"] += num(it.get("tokens"))
            a["sessions"] += num(it.get("sessions"))
            if it.get("summary"):
                a["summary"] = it.get("summary")
            if it.get("note"):
                a["note"] = it.get("note")
            if it.get("tool"):
                a["tools"].add(it.get("tool"))
            if fd < a["first"]:
                a["first"] = fd
            if ld >= a["last"]:
                a["last"] = ld
    for a in agg.values():
        a["tools"] = sorted(a["tools"])
    return sorted(agg.values(), key=lambda x: -x["my_min"])


def collect_work_summaries(daily):
    """Merge per-date day['work_summaries'] (work key → activity-summary bullets, written by
    Claude) per work key. The SKILL rewrites the full cumulative summary each run, so the
    latest date's value is the most complete. Work key = ticket key
    ({{JIRA_PROJECT_KEY}}-xxxx) for tickets, session title (label) otherwise.
    날짜별 day['work_summaries'](작업키→활동 요약 bullet, Claude 작성)를 작업키별로 병합.
    매 실행마다 SKILL 이 누적 요약을 통째로 다시 써 넣으므로 최신 날짜 값이 가장 완전하다.
    작업키 = 티켓은 티켓 키({{JIRA_PROJECT_KEY}}-xxxx), 티켓 외는 세션 제목(label)."""
    out = {}
    for dstr in sorted(daily.keys()):
        for key, text in (daily[dstr].get("work_summaries") or {}).items():
            if (text or "").strip():
                out[key] = text
    return out


def build_worklist(daily):
    """Unify ticket work + non-ticket work into one "work" list (sorted by my time desc).
    Each item maps to one row in the Notion "작업" DB (upsert key = name).
    - Ticket work: from ticket_cumulatives. Session-based metrics (total = union active,
      my time, Claude work, reaction delay, tokens, session count) + ticket key + Jira
      status + link basis / shared sessions.
    - Non-ticket work: from _collect_non_ticket (per session title / first prompt label).
    - work_summary: activity summary written by Claude (if any).
    티켓 작업 + 티켓 외 작업을 하나의 '작업' 목록으로 통합(총 시간 내림차순).
    각 작업은 Notion '작업' DB 한 행에 대응한다(upsert 키 = name).
    - 티켓 작업: ticket_cumulatives 기반. 세션 기반 지표(총 시간=합집합 활성, 내 시간,
      Claude 작업, 반응지연, 토큰, 세션 수) + 티켓 키 + Jira 상태 + 연결 근거/중복 공유.
    - 티켓 외 작업: _collect_non_ticket 기반(세션 제목/첫 프롬프트 라벨 단위).
    - work_summary: Claude 가 작성한 활동 요약(있으면)."""
    if not daily:
        return []
    all_dates = sorted(daily.keys())
    all_s, all_e = d(all_dates[0]), d(all_dates[-1])
    cum = ticket_cumulatives(daily)
    summaries = collect_work_summaries(daily)

    items = []
    for key, c in cum.items():
        if key == ETC_KEY:
            continue
        summary = (c.get("summary") or "").strip()
        name = f"{key} {summary}".strip() if summary else key
        items.append({
            "name": name,
            "ticket": key,
            "kind": KIND_TICKET,
            "total_min": round(num(c.get("session_total_min")), 1),
            "my_min": round(num(c.get("my_minutes")), 1),
            "claude_min": round(num(c.get("claude")), 1),
            "reaction_min": round(num(c.get("reaction_sum")), 1),
            "tokens": int(num(c.get("tokens"))),
            "sessions": int(num(c.get("sessions"))),
            "first_date": c.get("start_date"),
            "last_date": c.get("latest_date") or c.get("start_date"),
            "jira_status": c.get("status") or "",
            "summary": summary,
            "basis": c.get("basis") or [],
            "shared_with": c.get("shared_with") or [],
            "tool": "·".join(c.get("tools") or ["Claude"]),
            "mixed": False,
            "work_summary": summaries.get(key, ""),
        })

    for a in _collect_non_ticket(daily, all_s, all_e):
        items.append({
            "name": a["label"],
            "ticket": "",
            "kind": KIND_NON_TICKET,
            "total_min": round(num(a.get("total")), 1),
            "my_min": round(num(a.get("human")), 1),
            "claude_min": round(num(a.get("claude")), 1),
            "reaction_min": round(num(a.get("reaction_sum")), 1),
            "tokens": int(num(a.get("tokens"))),
            "sessions": int(num(a.get("count"))),
            "first_date": a.get("first"),
            "last_date": a.get("last"),
            "jira_status": "",
            "summary": "",
            "basis": ["title"],
            "shared_with": [],
            "tool": "·".join(a.get("tools") or ["Claude"]),
            "mixed": bool(a.get("mixed")),
            "work_summary": summaries.get(a["label"], ""),
        })

    # Manual work rows entered by a person (offline external activities etc.). Not in
    # day_totals / ticket cumulatives; appear only as one row in the "작업" DB / dashboard.
    # tool stays blank when empty (no Claude default).
    # 사람이 직접 넣은 수동 작업 행(오프라인 외부 활동 등). day_totals/티켓 누적엔 없고
    # '작업' DB·대시보드에만 한 행으로 나온다. tool 은 비어 있으면 공란 유지(기본값 Claude 아님).
    for a in _collect_manual(daily):
        items.append({
            "name": a["name"],
            "ticket": "",
            "kind": KIND_NON_TICKET,
            "total_min": round(num(a.get("total_min")), 1),
            "my_min": round(num(a.get("my_min")), 1),
            "claude_min": round(num(a.get("claude_min")), 1),
            "reaction_min": round(num(a.get("reaction_min")), 1),
            "tokens": int(num(a.get("tokens"))),
            "sessions": int(num(a.get("sessions"))),
            "first_date": a.get("first"),
            "last_date": a.get("last"),
            "jira_status": "",
            "summary": "",
            "basis": ["manual"],
            "shared_with": [],
            "tool": "·".join(a.get("tools") or []),
            "mixed": False,
            "note": a.get("note", ""),
            "manual": True,
            "work_summary": a.get("summary", "") or summaries.get(a["name"], ""),
        })

    # Sort: my time (time a person actually spent) desc, tie-break by total time.
    # 정렬 기준: 내 시간(사람이 실제로 쓴 시간) 내림차순, 동률이면 총 시간.
    items.sort(key=lambda x: (-x["my_min"], -x["total_min"]))
    return items


BASIS_LABELS = {
    "branch": t("branch", "브랜치"),
    "title": t("session title", "세션 제목"),
    "prompt": t("prompt", "프롬프트"),
    "commit": t("commit", "커밋"),
    "manual": t("manual entry", "수동 입력"),
}


def _basis_str(basis):
    """Link-basis list → human-readable string.
    연결 근거 리스트 → 사람이 읽는 문자열."""
    if not basis:
        return "—"
    return "·".join(BASIS_LABELS.get(b, b) for b in basis)


def _period_str(first, last):
    """First~last used date → MM/DD or MM/DD~MM/DD.
    첫~마지막 사용일 → MM/DD 또는 MM/DD~MM/DD."""
    f, l = _fmt_md(first), _fmt_md(last)
    return f if f == l else f"{f}~{l}"


def _summary_cell(text, n=70):
    """Summary for a verification-table cell: join bullets into one short line.
    검증 표 셀용 요약: bullet 들을 한 줄로 합쳐 짧게."""
    if not (text or "").strip():
        return "-"
    parts = []
    for ln in str(text).splitlines():
        ln = ln.strip().lstrip("-•*").strip()
        if ln:
            parts.append(ln)
    joined = " · ".join(parts)
    if len(joined) > n:
        joined = joined[:n].rstrip() + "…"
    return joined


def render_dashboard(daily, asof, heading=DASHBOARD_HEADING):
    """Dashboard visualizing the work DB data as-is.
    Layout: one "last updated" line + verification table (my time desc). My time / total
    time are shown in hours only on the dashboard. Share bars are based on my time.
    작업 DB 데이터를 그대로 시각화한 대시보드.
    구성: 최근 갱신 1줄 + 검증용 표(내 시간 내림차순). 내 시간·총 시간은 대시보드에서만
    '시간' 단위로 표기한다. 비중 막대는 내 시간 기준."""
    items = [it for it in build_worklist(daily) if num(it["total_min"]) > 0]
    # My time desc (tie-break by total time) / 내 시간 내림차순(동률이면 총 시간)
    items.sort(key=lambda x: (-num(x["my_min"]), -num(x["total_min"])))

    L = [f"## {heading}"]
    now_s = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    L.append(t(f"_Last updated: {now_s} · as of {asof}_", f"_최근 갱신: {now_s} · 기준일 {asof}_"))
    if not items:
        L.append(t("_No work aggregated yet._", "_아직 집계된 작업이 없습니다._"))
        return "\n\n".join(L)

    # Verification table (my time desc) / 검증용 표 (내 시간 내림차순)
    L.append(t("_Verification table — ⚠ mixed session = a session mixing several human prompt topics; "
               "⚠ shared session = one session counted under several work items (duplicated in the total-time sum)._",
               "_검증용 표 — ⚠ 혼합 세션은 사람 프롬프트 주제가 여럿 섞인 세션, "
               "⚠ 세션 공유는 한 세션이 여러 작업에 중복 계상된 경우(총 시간 합계에 중복 포함)._"))
    maxv = max(num(it["my_min"]) for it in items) or 1.0
    head = [t("Work", "작업"), t("Kind", "구분"), t("Tool", "도구"), t("My time", "내 시간"),
            t("Total time", "총 시간"), t("Share", "비중"), t("Summary", "요약"),
            t("Sessions", "세션 수"), t("Period", "기간"), t("Link basis", "연결 근거"), t("Notes", "비고")]
    tbl = ['<table fit-page-width="true" header-row="true">']
    tbl.append("<tr>" + "".join(f"<td>{esc(h)}</td>" for h in head) + "</tr>")
    for it in items:
        my_hrs = num(it["my_min"]) / 60.0
        tot_hrs = num(it["total_min"]) / 60.0
        notes = []
        if it.get("mixed"):
            notes.append(t("⚠ mixed session", "⚠ 혼합 세션"))
        sw = it.get("shared_with") or []
        if sw:
            notes.append(t("⚠ shares sessions with " + ", ".join(sw), "⚠ " + ", ".join(sw) + "와 세션 공유"))
        if (it.get("note") or "").strip():
            notes.append(it["note"].strip())
        note = " · ".join(notes) if notes else "-"
        # Tool: Claude/Codex for auto sessions; blank for manual rows (offline external activity).
        # 도구: 자동 세션은 Claude/Codex, 수동 행(오프라인 외부 활동)은 공란 유지.
        tool_val = it.get("tool")
        if tool_val:
            tool_cell = esc(tool_val)
        elif it.get("manual"):
            tool_cell = ""
        else:
            tool_cell = "Claude"
        cells = [
            f"<td>{esc(it['name'])}</td>",
            f"<td>{esc(it['kind'])}</td>",
            f"<td>{tool_cell}</td>",
            "<td>" + t(f"{my_hrs:.1f}h", f"{my_hrs:.1f}시간") + "</td>",
            "<td>" + t(f"{tot_hrs:.1f}h", f"{tot_hrs:.1f}시간") + "</td>",
            f"<td>`{_hbar(it['my_min'], maxv)}`</td>",
            f"<td>{esc(_summary_cell(it.get('work_summary')))}</td>",
            f"<td>{int(num(it['sessions']))}</td>",
            f"<td>{esc(_period_str(it.get('first_date'), it.get('last_date')))}</td>",
            f"<td>{esc(_basis_str(it.get('basis')))}</td>",
            f"<td>{esc(note)}</td>",
        ]
        tbl.append("<tr>" + "".join(cells) + "</tr>")
    tbl.append("</table>")
    L.append("\n".join(tbl))
    return "\n\n".join(L)


# ──────────────────────────────────────────────────────────────────────────
# Commands / 커맨드
# ──────────────────────────────────────────────────────────────────────────

def _is_blank_text(v):
    return not (str(v).strip() if v is not None else "")


def _reaggregate_merge(old_day, new_day, requested_mode):
    """Reaggregate: refresh auto metrics from new_day (latest collect) but preserve
    human-entered qualitative/off-session fields from old_day (fall back to old only when
    new is blank — a filled new value wins). Also preserves manual rows, retro, plan, and
    work_summaries. Never downgrades mode (auto never turns a day a person closed as
    interactive back into auto). Returns: (merged_mode).
    재집계: 자동 수치는 new_day(최신 collect)로 갱신하되, 사람이 입력한 질적/세션 밖
    필드는 old_day 에서 보존한다(new 가 비어 있을 때만 old 로 되돌림 — new 가 채워졌으면
    그 값이 이긴다). 수동 행(manual)·회고(retro)·계획(plan)·작업 요약(work_summaries)도 보존.
    mode 는 절대 강등하지 않는다(사람이 interactive 로 마감한 날을 auto 가 auto 로 바꾸지 않음).
    반환: (merged_mode)."""
    if not old_day:
        return requested_mode
    # Day-level qualitative fields / 하루 단위 질적 필드
    if _is_blank_text(new_day.get("retro")) and not _is_blank_text(old_day.get("retro")):
        new_day["retro"] = old_day.get("retro")
    if not new_day.get("plan") and old_day.get("plan"):
        new_day["plan"] = old_day.get("plan")
    if not new_day.get("manual") and old_day.get("manual"):
        new_day["manual"] = old_day.get("manual")
    # Work summaries: old ∪ new (new wins per key) / 작업 요약: old ∪ new (키 단위로 new 가 이김)
    merged = dict(old_day.get("work_summaries") or {})
    merged.update(new_day.get("work_summaries") or {})
    new_day["work_summaries"] = merged
    # Preserve per-ticket qualitative/off-session fields / 티켓별 질적/세션 밖 필드 보존
    old_t = old_day.get("tickets") or {}
    for key, t in (new_day.get("tickets") or {}).items():
        ot = old_t.get(key) or {}
        for f in HUMAN_TICKET_TEXT_FIELDS:
            if _is_blank_text(t.get(f)) and not _is_blank_text(ot.get(f)):
                t[f] = ot.get(f)
        for f in HUMAN_TICKET_NUM_FIELDS:
            if num(t.get(f)) == 0 and num(ot.get(f)) != 0:
                t[f] = ot.get(f)
    # Never downgrade mode / mode 강등 금지
    if old_day.get("mode") == "interactive" and requested_mode == "auto":
        return "interactive"
    return requested_mode


def cmd_build(args):
    st = load_state()
    with open(args.input, "r", encoding="utf-8") as f:
        day = json.load(f)
    date = args.date
    old_day = (st.get("daily") or {}).get(date)
    new_day = {
        "retro": day.get("retro", ""),
        "plan": day.get("plan", []),
        "human": day.get("human", {}),
        "metrics": day.get("metrics", {}),
        "non_ticket": day.get("non_ticket", []),
        "tickets": day.get("tickets", {}),
        "work_summaries": day.get("work_summaries", {}),
        "manual": day.get("manual", []),
    }
    mode = args.mode
    if getattr(args, "reaggregate", False):
        mode = _reaggregate_merge(old_day, new_day, args.mode)
    # Confirmed flag: if the target date is before the run date (local = KST), metrics are
    # final → stop auto reaggregation. An early same-day close stays unconfirmed → next
    # day's auto reaggregates once to fill in evening work.
    # 확정 플래그: 대상 날짜가 실행일(로컬=KST)보다 과거면 수치 확정 → auto 재집계 중단.
    # 당일 조기 마감이면 미확정 → 다음날 auto 가 한 번 재집계해 저녁 작업을 보완.
    today = datetime.now().astimezone().date()
    try:
        confirmed = d(date) < today
    except Exception:
        confirmed = False
    # Idempotent merge: replace the whole date / 멱등 병합: 해당 날짜를 통째로 교체
    new_day["mode"] = mode
    new_day["confirmed"] = confirmed
    new_day["updated_at"] = datetime.now().astimezone().isoformat()
    st["daily"][date] = new_day
    # Update state / 상태 갱신
    st["last_processed_date"] = max(
        [x for x in st.get("processed_dates", []) + [date]] or [date]
    )
    if date not in st["processed_dates"]:
        st["processed_dates"].append(date)
    st["processed_dates"] = sorted(set(st["processed_dates"]))
    st["last_run_at"] = datetime.now().astimezone().isoformat()
    st["runs"] = (st.get("runs", []) + [{
        "date": date, "at": st["last_run_at"], "mode": mode,
        "reaggregate": bool(getattr(args, "reaggregate", False)),
    }])[-200:]
    save_state(st)

    cum = ticket_cumulatives(st["daily"])
    out = {
        "date": date,
        "mode": mode,
        "confirmed": confirmed,
        "reaggregated": bool(getattr(args, "reaggregate", False)) and old_day is not None,
        "daily_totals": day_totals(st["daily"][date]),
        "daily_table_md": render_daily_table(st["daily"][date]),
        "work_timeline_md": render_work_timeline(st["daily"][date]),
        "human": st["daily"][date].get("human", {}),
        "metrics": st["daily"][date].get("metrics", {}),
        "ticket_cumulatives": cum,
        "worklist": build_worklist(st["daily"]),
        "dashboard_md": render_dashboard(st["daily"], date),
        "state_path": STATE_PATH,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2 if args.pretty else None))


def cmd_worklist(args):
    st = load_state()
    print(json.dumps(build_worklist(st["daily"]), ensure_ascii=False, indent=2))


def cmd_dashboard(args):
    st = load_state()
    asof = args.asof or (max(st["daily"].keys()) if st["daily"] else datetime.now().astimezone().strftime("%Y-%m-%d"))
    print(render_dashboard(st["daily"], asof))


def cmd_cumulatives(args):
    st = load_state()
    print(json.dumps(ticket_cumulatives(st["daily"]), ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(description=t("Work-journal cumulative/dashboard aggregator",
                                               "업무 일지 누적/대시보드 집계기"))
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help=t("Merge one day + recompute + save state",
                                         "하루치 병합 + 재계산 + state 저장"))
    b.add_argument("--date", required=True)
    b.add_argument("--input", required=True)
    b.add_argument("--mode", default="interactive", choices=["interactive", "auto"])
    b.add_argument("--reaggregate", action="store_true",
                   help=t("Reaggregate an already-processed date: refresh auto metrics only and "
                          "preserve human-entered qualitative/off-session fields, manual rows, "
                          "retro, plan, and summaries (no mode downgrade)",
                          "이미 처리된 날짜 재집계: 자동 수치만 갱신하고 사람이 입력한 "
                          "질적/세션 밖 필드·수동 행·회고·계획·요약은 보존(mode 강등 금지)"))
    b.add_argument("--pretty", action="store_true")
    b.set_defaults(func=cmd_build)

    dash = sub.add_parser("dashboard", help=t("Recompute and print dashboard markdown only",
                                               "대시보드 마크다운만 재계산 출력"))
    dash.add_argument("--asof")
    dash.set_defaults(func=cmd_dashboard)

    c = sub.add_parser("cumulatives", help=t("Print ticket cumulatives as JSON", "티켓 누적 JSON 출력"))
    c.set_defaults(func=cmd_cumulatives)

    w = sub.add_parser("worklist", help=t("Print the unified work list as JSON (for work DB upsert)",
                                         "통합 '작업' 목록 JSON 출력(작업 DB upsert용)"))
    w.set_defaults(func=cmd_worklist)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
