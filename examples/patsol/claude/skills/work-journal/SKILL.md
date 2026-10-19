---
name: work-journal
description: >-
  Per-Jira-ticket work journal. Organizes the day's work by "task" (ticket or session title) — progress/blockers,
  time (total time · my time · Claude work + planning·understanding·research·discussion·other that only a human knows),
  decisions made and why, status changes — plus today's plan. Auto-collects Claude Code sessions, git commits, and Jira,
  asks only about what a human alone knows in one batch, then records it in Notion (📈 dashboard + unified "task" DB +
  daily/ticket DBs for AI reference) with number tables. Respond in the user's language (match the language the user writes in).
  Triggers: "work journal", "/work-journal", "what did I do today", "summarize yesterday", "ticket summary", "weekly retro",
  "업무 정리", "일지", "오늘 뭐했지", "어제 정리", "티켓 정리", "주간 회고".
model: opus
effort: high
allowed-tools: Bash, Read, Write, Glob, Grep
---

# work-journal — per-task work journal + daily auto-summary

A skill for the user ({{USER_DISPLAY_NAME}}) to track "how I work, how I make decisions, and how I get things done."
It **auto-collects what Claude knows**, **asks once, in a batch, only about what a human alone knows (planning/understanding/discussion time, blocker causes, decision reasons)**,
then records it **in Notion as number tables + a cumulative dashboard + a unified "task" DB**. Respond in the user's language (match the language the user writes in).

> Korean names in backticks below (Notion DB/property/select/view names, page headings, Jira status names, the `기타` bucket key) are the live Notion/Jira workspace schema and the keys produced by `collect.py`/`aggregate.py`. Use them verbatim — do not translate.

## Core principles
- **No mental math.** Time totals, ratios, cumulatives, the dashboard, h:mm conversion, progress bars, and the work list are all computed by `aggregate.py`. Use its output (JSON/markdown) as-is.
- **Idempotent.** Re-running the same date never double-counts (the date in `state.json` is replaced wholesale). Re-running and backfilling are safe. **The task DB, ticket DB, and dashboard are upserted/overwritten on every run.**
- **Reaggregate = refresh numbers only, preserve human input.** `aggregate build … --reaggregate` refreshes only the auto-collected numbers (time, tokens, sessions, commits, work list, summary material) from the latest collect, and **merges (preserves) human-entered qualitative fields (decisions, blockers, out-of-session planning/research/discussion/other, retro, plan, manual summaries, manual rows) from the previous state**. Mode is never downgraded (auto never turns a day closed as interactive back into auto). Use this flag to **re-aggregate through end of day a day the human closed early, which missed evening work**.
- **Confirmed flag (`confirmed`).** `aggregate build` sets **`state.daily[D].confirmed=true` if the target date is before the run date (KST)** (numbers final). A same-day early close stays `confirmed=false`, so the next day's auto run re-aggregates it once to fill the gap; by then it's a past day, so it becomes `confirmed=true` and is not reprocessed again.
- **Tracking start floor.** Dates before `config.tracking_start_date` (read from config.json at run time) are never collected, aggregated, or recorded. `collect.py` ignores them automatically and `aggregate.py build` rejects them. Also excluded from backfill.
- **Session = one Claude Code session.** `collect.py` groups the main transcript file and **the subagent files sharing the same sessionId (agent-*.jsonl, sidechains)** into one session (not per file). So "session count" and "max concurrent sessions" reflect real Claude Code sessions.
- **Session↔ticket linking is strict.** A session is linked to a ticket only when the ticket key appears in one of:
  (1) **the git branch name**, (2) **the session title (custom-title)**, (3) **a non-sidechain prompt typed by the session's human** (= explicit work target), (4) **the message/branch of a commit made within the session span**.
  **Tickets that appear only in sidechain (subagent) prompts, only in tool results/system-reminders/auto-injections, or only in a skill's Jira lookup text are not linked** (treated as reference mentions). Sessions failing these criteria are classified as **"non-ticket work" (`티켓 외`) based on the session title**. All this logic lives in `collect.py`, so the skill never attaches tickets on its own.
- **Three time metrics are distinct.**
  - **Total time (min)** = active time over the **union** of message timestamps in the session group's **main (non-sidechain) file**. "Actual elapsed work time" (counted 1× even if parallel). Subagent (sidechain) time is not included.
  - **Claude work (min, parallel sum)** = **simple sum of per-file active time** (main + sidechains) in the group. Overlapping parallel subagents can exceed total/wall-clock time.
  - **My time (min)** = active time reconstructed from the timestamps of prompts the human typed, using the **slot method** (min `HUMAN_SLOT_MIN`=5 min per prompt, prompts within 15 min merged into one span — same rule as `compute_human`) (automatic). **Never asked. Sort key for the task DB and dashboard.**
  - Note: if one session spans multiple tickets (e.g. prompts mention PS-A, commits PS-B), its time is counted **for both tickets** (blended session). Intended, same nature as "parallel sum."
- **Ask only what a human alone knows.** Never ask about values that can be estimated automatically (total time, Claude work, my time, commit count, session count, tokens, reaction delay, Jira status). Ask only about planning/understanding·research/discussion/other time spent **outside** sessions, plus blockers and decisions (section 3). Never re-ask if an answer exists.
- **Tool distinction (Claude / Codex).** `collect.py` merges Claude Code sessions and **Codex sessions the user launched directly** (rollouts in `~/.codex/sessions` and `~/.codex/archived_sessions`, originator `Codex Desktop`/`codex_work_desktop`/`codex-tui`, etc.) into **one pipeline**. **Must exclude**: guardian subagents (`source` is a dict/`subagent`) and **sessions created by importing Claude sessions into Codex** (`imported_thread_id` in `external_agent_session_imports.json` — prevents double counting). Each session/task gets a `tool` (Claude/Codex), shown as the task DB `도구` property and the dashboard `도구` column. Dates are KST; the same `tracking_start_date` floor applies.
- **Scheduled sessions and sidechain correction.** Scheduled sessions are excluded from all totals. Sidechain files are absorbed into the parent session and only contribute to Claude work (parallel); they are not counted as separate tickets/sessions (and not in total time). `collect.py` handles all of this.
- **Always verify at the end.** Re-read the task DB, daily page, ticket DB, and dashboard to confirm the updates; on failure, retry once and then report to the user.

## Files & paths (absolute)
- Config: `~/.claude/worklog/config.json` — Notion/Jira IDs, property-name mapping, `tracking_start_date`. **Read it at the start of every run and take all IDs from it (no hardcoding).** `notion.work_db` (unified task DB), `notion.ticket_db`, `notion.daily_db`, and `notion.parent_page_id` are all there.
- State (single source of truth): `~/.claude/worklog/state.json` — per-date data and the source of cumulatives. Managed by `aggregate.py`. Each date has `mode` (auto/interactive), `confirmed` (numbers final), and `manual` (manual task rows). `wandsol_synced` (WandSol sync record, including `pending_additional_min`) also lives here.
- Collector: `python3 ~/.claude/worklog/bin/collect.py`
- Aggregator: `python3 ~/.claude/worklog/bin/aggregate.py`
- Note: `~/.claude/settings.json` is unrelated to this skill; don't touch it.

## Parent page layout (fixed)
The `config.notion.parent_page_id` page is, top to bottom:
1. **Intro** (one paragraph).
2. **`## 📈 누적 대시보드`** (cumulative dashboard) — visualizes task DB data as-is. One "last updated" line + a verification table (**my time desc**; columns: task·kind·tool·my time·total time·share·summary·session count·period·link basis·notes). **The end marker is the verification table's `</table>`** (the dashboard's last block). No mermaid charts, KPI callouts, pies, period summaries, or detail-metric toggles.
3. **`작업` inline DB** (task DB, `config.notion.work_db`) — tickets and non-ticket work unified. Each row has an activity `요약` (summary; body identical) and `도구` (tool: Claude/Codex). Default view "전체 (내 시간순)" (all, by my time) + "티켓만" (tickets only) / "티켓 외" (non-ticket) filter views.
4. **`## 🗂 AI 참고용 기록`** (records for AI reference) heading + one intro line.
5. **`일별 기록` inline DB** (daily records, `config.notion.daily_db`).
6. **`티켓 트래킹` inline DB** (ticket tracking, `config.notion.ticket_db`).

## Arguments (`$ARGUMENTS`)
- (none) → summarize the **previous weekday** + today's plan (interactive).
- `YYYY-MM-DD` → summarize that date only.
- `auto` → **non-interactive (for the scheduler)**. No questions; record only automatic facts, leave human time/decisions blank, and finish with a "fill in with `/work-journal`" hint.
- `ticket {{JIRA_PROJECT_KEY}}-123` → just that ticket, summarized/asked based on recent activity.
- `weekly` → weekly retro over the last 7 days (same number-table format).

---

## Procedure

### 0) Load & determine target dates
1. Read `config.json` and `state.json`.
2. Parse arguments. Mode: **auto mode** (no questions) if the `auto` argument is present, otherwise **interactive mode**.
3. Target dates:
   - Default/date argument: that date (default: previous weekday).
   - **Backfill**: from the day after `state.last_processed_date` up to the target date, collect **weekdays not in `state.processed_dates`**. Process oldest first. If more than `state.backfill_max` (default 5), take only that many, most recent first.
   - **Exclude all dates before `tracking_start_date`** (including backfill).
   - **auto mode re-aggregation of interactive-closed days (evening work fill-in).** Even for an already-closed day (`state.daily[D].mode == "interactive"`), auto mode includes it if **not yet confirmed (`state.daily[D].confirmed != true`) and within "the previous weekday and unconfirmed days after it"**, and **re-aggregates only the auto-collected numbers through end of day** (fills in evening work missed when the human closed early). Always run it as `aggregate build … --mode auto --reaggregate` so **human-entered qualitative fields and manual rows are preserved** and mode stays interactive. **Skip interactive days already `confirmed=true`.** Limit re-aggregation to "the previous weekday + unconfirmed days after it"; never reopen older confirmed days. An interactive re-run with an explicit date is still allowed (human input wins).
   - `weekly`: range (section 7 below).

### 1) Auto-collect (per date)
- For each target date D: run `python3 ~/.claude/worklog/bin/collect.py --date D --pretty` → parse JSON. (If D is before `tracking_start_date`, the report is empty; skip it.)
  - `sessions[]` = **session groups** (main + sidechains; Claude sessions + user-launched Codex sessions). Each session: `total_minutes` (total time, main-only union), `active_minutes` (Claude work, parallel sum), `human_active_minutes` (my time, slot), `tokens`, `reaction_delay_sum`, `git_branch`, `custom_title`, `tickets`, `is_scheduled`, `human_times`, `label`, **`tool`** (Claude/Codex), **`mixed_candidate`** (candidate for mixed topics), **`human_samples_more`** (up to 12 prompt excerpts for the mixed judgment), etc.
  - `tickets{}` = per-ticket aggregates: `active_minutes` (Claude), `total_minutes` (total time), `human_minutes` (my time), `tokens_total`, `reaction_sum`, `commit_count`, `session_count`, etc. Also **`basis`** (link basis: branch/title/prompt/commit), **`shared_with`** (other tickets sharing the same session = double-counted), **`tools`** (contributing tools), and summary material (`titles`·`prompts`·`commit_messages`). `기타` (other) = bucket of ticketless sessions.
  - `human` (actual human work time, automatic): `active_minutes`/`active_hhmm`, `work_start`/`work_end`, `session_open_union_minutes`, `session_switch`/`ticket_switch`·`switches_per_hour`, `max_concurrent_sessions`/`avg_concurrent_sessions`, `by_ticket`, `timeline`.
  - `metrics` (automatic): `tokens`, `reaction_delay_sum_min`·`reaction_delay_median_min`·`reaction_delays`, `non_ticket_active_minutes`.
  - `non_ticket[]` (automatic): ticketless sessions labeled by session title / first prompt — `label`, `tool` (Claude/Codex), `total_minutes`, `claude_minutes`, `human_minutes`, `tokens_total`, `reaction_sum`, `date`, `mixed_candidate`. Includes summary material `title`·`first_request`·`samples`·`samples_more`.
  - `totals`: `session_count` (non-scheduled), `scheduled_session_count`, `active_minutes`, `commit_count`, `ticket_count`, `ticket_keys`.
- **Day-off detection**: if the human started 0 sessions that day (including days with only scheduled sessions) and there are 0 commits, it's a **day off**. Days the user explicitly calls a day off/holiday/leave are also days off.
  - For a day off, ask nothing and skip sections 2, 3, and 6. Run `aggregate build` (in the current run mode) with `day.json`=`{"retro":"Day off (no activity)","plan":[],"tickets":{}}` (retro text in the output language) → mark processed.
  - Notion: daily page title=D, retro="Day off", time and commits 0, body `Day off — no activity to record` (in the output language). Don't touch the task DB or ticket DB. Refresh the dashboard (section 8) as usual.
  - Chat: one line, "D: recorded as day off".
- **Strict linking, again**: the skill trusts `collect.py`'s `tickets`/`non_ticket` results as-is. Never add a ticket just because it was mentioned once in a prompt or showed up in a Jira lookup.

### 2) Jira lookup
- Confirm identity with `atlassianUserInfo` (account `config.jira.account_id`).
- For the PS tickets that appeared (`ticket_keys` from collect), call `searchJiraIssuesUsingJql` (cloudId=`config.jira.cloud_id`): `jql: key in (...)`, `fields: ["summary","status","updated"]` → summary, status, webUrl.
- **A Jira lookup is never a ticket-link basis.** The status/summary obtained here only fills metadata for tickets collect already linked; it never links new tickets to work.
- **Status change**: if the ticket DB's current `상태` (status) differs from Jira's current status, record `"previous→current"`. **Jira is authoritative** for status (align to Jira even if a human changed the value manually).
- `progress_pct` (not asked; keys are Jira status names): 해야 할 일 (to do)=5, 진행 중 (in progress)=50, 리뷰 (review)=70, QA=75, DEV 배포완료 (deployed to DEV)=85, 완료 (done)=100, 보류 (on hold)=0.

### 3) Ask what only a human knows (interactive mode only)
- **Skip in auto mode.** Out-of-session time 0/blank, blockers and decisions empty.
- **My time is automatic, so never ask it.** Ask only about **time spent outside sessions** (planning/understanding·research/discussion/other, without a Claude session) and blockers/decisions.
- Scope: tickets with activity (prioritize excluding `기타`). **At most 3 questions per ticket**, short, **batched in one go** (`AskUserQuestion`). Batch across days when backfilling. **Never re-ask if an answer exists.**
- Example questions: ① "For this ticket, how much time **outside sessions** (meetings, offline planning, reading docs, etc.) went to planning/understanding·research/discussion each?" (`0`·`~30 min`·`~1 hour`·`~2 hours`·`custom`) ② "Where/why were you blocked?" ③ "Key decisions and why?"
- Conversion: `0→0`, `~30 min→30`, `~1 hour→60`, `~2 hours→120`. Blocked time (`blocked_min`) only when there was a blocker.

### 4) Assemble day.json → aggregate build
- Write date D's `day.json` to the scratchpad. Schema:
  ```json
  {
    "retro": "1–3 line daily retro",
    "plan": ["3 items for today's plan (section 6)"],
    "human": <collect report["human"] as-is>,
    "metrics": <collect report["metrics"] as-is>,
    "non_ticket": <collect report["non_ticket"] as-is>,
    "tickets": {
      "{{JIRA_PROJECT_KEY}}-123": {
        "summary":"...", "jira_url":"...", "status":"해야 할 일",
        "claude": <collect active_minutes>, "total_minutes": <collect total_minutes>,
        "human_minutes": <collect human_minutes>, "tokens": <collect tokens_total>,
        "reaction_sum": <collect reaction_sum>,
        "basis": <collect basis>, "shared_with": <collect shared_with>, "tools": <collect tools>,
        "planning": <answer>, "research": <answer>, "discussion": <answer>, "etc": <answer>,
        "commits": <collect commit_count>, "sessions": <collect session_count>,
        "progress_pct": <section 2>, "status_change": "" or "previous→current",
        "progress":"auto facts + summary", "blocked":"" , "blocked_min": 0,
        "decisions":"", "next":""
      },
      "기타": { "claude":..., "total_minutes":..., "human_minutes":..., "tokens":..., "reaction_sum":..., "basis":[], "shared_with":[], "planning":0, ... }
    },
    "work_summaries": {
      "{{JIRA_PROJECT_KEY}}-123": "- what was done in the session, bullet 1\n- bullet 2",
      "<non-ticket label>": "- bullet 1\n- bullet 2"
    },
    "manual": [
      {"name":"External conference (offsite event)","kind":"티켓 외","total_min":490,"my_min":490,
       "claude_min":0,"reaction_min":0,"tokens":0,"sessions":0,"date":"YYYY-MM-DD","tool":"",
       "summary":"Attended 09:50–18:00 (8h 10m)","note":"Offline external event"}
    ]
  }
  ```
  - Units are **minutes**. `claude`·`total_minutes`·`human_minutes`·`tokens`·`reaction_sum`·`commits`·`sessions`·`basis`·`shared_with`·`human`·`metrics`·`non_ticket` are **collect's automatic values as-is**. In auto mode, planning/research/discussion/etc=0 and blocked/decisions/next="".
  - `human`, `metrics`, and `non_ticket` must be included for the timeline, dashboard, task DB (non-ticket), tokens, and reaction delay to appear.
  - `progress` is a 1–2 line summary from collect's first_user_request, last_result, and commit messages (automatic).
  - **Write task summaries (`work_summaries`) — required every run.** For each task (ticket key / non-ticket label), use collect material (tickets: `titles`·`prompts`·`commit_messages` + `progress`; non-ticket: `title`·`first_request`·`samples`) to write "what was done in those session(s)" as **2–4 bullets, one short line each** (not too detailed). Task key = ticket key ({{JIRA_PROJECT_KEY}}-xxxx) for tickets, label for non-ticket. **When backfilling/re-aggregating, read `work_summaries` from the previous state and add/update only the new date's activity** (writing the whole value back). This value is used for the task DB `요약` property, the row body, and the dashboard summary column.
  - **When backfilling/re-aggregating, merge previously human-entered qualitative fields (planning/research/discussion/etc, decisions, blocked, blocked_min, next, work_summaries) from the previous state, for live tickets only** (drop values of tickets that disappeared). When auto re-aggregates an interactive-closed day, leave day.json's qualitative fields blank and **let aggregate preserve them via the `--reaggregate` flag** (the code auto-merges the previous state's qualitative fields, manual rows, retro, plan, and summaries). When a human re-runs interactively to change values, the new values win.
  - **Manual rows (manual) — offline activity not captured by sessions/commits.** Activities that leave no trace in Claude, git, or Jira (e.g. attending an external conference) go in `day.json`'s `manual` array as one row. Schema: `{"name":"task name","kind":"티켓 외","total_min":min,"my_min":min,"claude_min":0,"reaction_min":0,"tokens":0,"sessions":0,"date":"YYYY-MM-DD","tool":"","summary":"summary (e.g. attended 09:50–18:00)","note":"note (e.g. offline external event)"}`. `tool` stays **blank** since it's not an automatic session (don't create a new option). `aggregate` includes manual rows as one row in the task DB and dashboard but **not in day_totals or ticket cumulatives** (prevents double counting) — put the out-of-session time for the same activity separately in that date's out-of-session field (e.g. `etc` of the `기타` bucket). Manual rows are preserved on re-aggregation.
  - **Mixed-session judgment (done by Claude) — only sessions with `mixed_candidate=true`.** For candidates collect flagged (many human prompts and long wall-clock), read `human_samples_more` (prompt excerpts) and judge **whether multiple topics are actually mixed**.
    - **If multiple**: add `"mixed": true` to that `non_ticket` entry and **replace the task name (`label`) with a representative topic** (a name Claude derives from the summary material) **instead of the first prompt**. Rename the task key in `work_summaries` to the new label too (remove the old key), and start the summary bullets with "⚠ mixed session" (in the output language; Korean: "⚠ 혼합 세션") followed by **a list of the topics included**. Renamed rows are found and updated in the task DB upsert (5a).
    - **If one topic** (many prompts but one topic): don't add `mixed` (keep the label).
  - **Tool (`tool`) and mixed (`mixed`)**: keep `non_ticket`'s `tool` as collect's automatic value (Codex sessions are `"Codex"`). Pass tickets' `tools` as-is.
- Run: `python3 .../aggregate.py build --date D --input <day.json> --mode <auto|interactive> [--reaggregate] --pretty`
  - **Add `--reaggregate` only when re-aggregating an already-processed day** (auto filling in an interactive-closed day, or backfill correction). With it, only automatic numbers are refreshed; human-entered qualitative fields, manual rows, retro, plan, and summaries are preserved and mode is not downgraded.
  - Output: `daily_totals`, `daily_table_md`, `work_timeline_md`, `human`, `metrics`, `ticket_cumulatives`, **`worklist`** (unified task list = tickets + non-ticket + **manual rows**, my time desc; each task has `tool`·`mixed`·`note`), `dashboard_md`, plus `mode`·`confirmed`·`reaggregated`. **Write these values to Notion as-is.**
  - This call updates `state.json` (replaces the date; records processed/last_processed/run, mode, confirmed). Idempotent.
  - (`aggregate.py worklist` gives just the task list without modifying state; `aggregate.py dashboard --asof D` regenerates just the dashboard.)

### 5) Record in Notion
(IDs and property names come from `config.json`. Numbers are JS numbers, dates are `date:<property>:start`, selects are strings, relations are arrays of page URLs.)

**(5a) Task DB upsert** — `config.notion.work_db` (core)
- For each task in `worklist` (tickets + non-ticket + **manual rows**), look up the row with **`작업명`=name** in the ds (`data_source_id`) (create if missing, update if present = upsert).
- **Manual rows (`basis=["manual"]`)**: keep `도구` **blank** (not Claude/Codex), `요약`=work_summary (e.g. "attended 09:50–18:00 (8h 10m)"), reflect note (e.g. "offline external event") in notes/summary. Manual rows are not subject to WandSol correction (section 9).
- Properties (= `work_db.props` mapping): `작업명`=name (title), `티켓`=ticket (blank if none), `구분`=kind (select: 티켓/티켓 외), **`도구`=tool (select: Claude/Codex; `Claude·Codex` if both)**, `총 시간(분)`=total_min, `내 시간(분)`=my_min, `Claude 작업(분)`=claude_min, `반응 지연(분)`=reaction_min, `토큰`=tokens, `세션 수`=sessions, `첫 사용일`=first_date (`date:첫 사용일:start`), `마지막 사용일`=last_date, `Jira 상태`=jira_status (reference text), **`요약`=work_summary** (activity bullets written in section 4, text).
- **Put the same summary in the row body** as a bullet list (`replace_content` replacing only that row page's body — safe because task rows have no child DBs). Keep the `요약` property and the body identical.
- **Renamed rows (e.g. replaced with a mixed session's representative topic)**: find the old-name row and **update its `작업명` to the new name** (don't create a new one). If re-aggregation makes **a previously existing task name disappear from the worklist without carrying over to any new row**, don't delete it — **report it to the user** (section 10).
- The default view "전체 (내 시간순)" is sorted **by my time desc**. The "티켓만"/"티켓 외" filter views already exist (if not, create them with `notion-create-view` — see the DDL below section 8). If the sort is still by total time, change it with `notion-update-view` to **`SORT BY "내 시간(분)" DESC`**.

**(5b) Ticket DB upsert** — `config.notion.ticket_db` (for AI reference)
- For each ticket KEY (excluding `기타`), look up the row titled KEY (create if missing). **Overwrite** values with `ticket_cumulatives[KEY]`:
  - `누적 Claude 작업시간`=claude, `누적 기획시간`=planning, `누적 이해조사시간`=research, `누적 논의시간`=discussion, `누적 기타시간`=etc, `누적 내 시간`=my_minutes
  - `커밋 수`=commits, `세션 수`=sessions, `상태`=status, `요약`=summary, `Jira 링크`=jira_url, `막힌 점`=blocked, `시작일`=start_date, and `완료일`=done_date if done.
  - (Total time/ratio formulas are computed by the DB.) After creating/updating, get each ticket row's **page URL** (for the 5c relation).

**(5c) Daily page upsert** — `config.notion.daily_db` (for AI reference)
- Look up the row titled D (create if missing). Properties: `날짜값`=`date:날짜값:start`=D, `작업(분)`=daily_totals.claude, `기획/이해조사/논의/기타(분)`, `내 시간(분)`=daily_totals.my_minutes, `스위칭 수`=human.session_switch, `토큰 합계`=metrics.tokens.total, `반응 지연 합계(분)`=metrics.reaction_delay_sum_min, `티켓 외 시간(분)`=metrics.non_ticket_active_minutes, `커밋 수`, `세션 수`, `상태 변화`, `하루 회고`=retro, `관련 티켓`=array of 5b ticket page URLs.
- Body: replace with `replace_content` — `## 📊 오늘 수치` (today's numbers; daily_table_md) + work_timeline_md + `## 티켓별 상세` (per-ticket detail: progress/blockers/time/decisions/next) + `## 🧭 하루 회고` (daily retro) + `## ✅ 오늘 계획` (today's plan). (Daily pages have no child DBs, so replace_content is safe.)

### 6) Today's plan (plan)
- Recommend 3: from Jira `assignee=currentUser()` items in `진행 중` (in progress) / `해야 할 일` (to do) + yesterday's `blocked`. 1 continuing a blocked item + 1–2 in progress. Adjustable in interactive mode.

### 7) weekly (weekly retro)
- Range = last 7 days (or last week Mon–Sun, only on/after `tracking_start_date`). Confirm facts with `collect.py --range S:E`.
- Range numbers come from `collect.py --range S:E`, per-task total time from `aggregate.py worklist` (the dashboard has no weekly/monthly summary). Organize around the top tasks by total time.
- Analysis: time distribution, blocker patterns, decision tendencies, 2–3 improvement suggestions. Table + analysis in chat. Append this week's entry at the bottom of the parent page (or in a toggle). Daily state stays as-is.

### 8) Overwrite the cumulative dashboard (parent page)
- Use `aggregate`'s `dashboard_md` (or `aggregate.py dashboard --asof D`). Layout: one "last updated" line → verification table (**my time desc**: task·kind·tool·my time (hours)·total time (hours)·share bar (by my time)·summary·session count·period·link basis·notes). **My time and total time are in hours only on the dashboard** (the task DB and state stay in minutes).
- **The dashboard is not at the end of the page** (the task DB, 🗂 section, and DBs are below it). Replacement scope:
  - `notion-fetch` the parent page (`config.notion.parent_page_id`).
  - **old_str = from the `## 📈 누적 대시보드` line through the first `</table>` after it (inclusive).** The dashboard always ends with the verification table, so that `</table>` is the end marker (the only table in the dashboard). Leave the `작업` DB (`<database …>`) right below untouched.
  - `notion-update-page` `command=update_content`, `content_updates=[{old_str: <the full fetched dashboard section, heading through first </table>>, new_str: <dashboard_md>}]`. new_str also starts with `## 📈 누적 대시보드` and ends with `</table>`.
  - **Do not touch the task DB, 🗂 section, or daily/ticket DB blocks.** No whole-page replace_content (risk of deleting DBs). Don't use `allow_deleting_content` — **if a deletion warning appears, stop and report to the user.**

### 9) Automatic Jira worklog correction (WandSol shortfall)
Purpose: WandSol time tracking undercounts due to ticket switching and automatic idle pauses (especially when agents work in the background). At day close, add a Jira worklog for **the difference between session-based time and time already logged in Jira**. (The WandSol MCP has no worklog tool, so use Atlassian `addWorklogToJiraIssue`.)
- Scope: among that date's `day.json` `tickets`, **Jira tickets starting with PS- & total_minutes>0** (excluding Sentry keys like DJANGO-* and `기타`).
- Baseline (min) = that ticket's `total_minutes` for the day (collect automatic value). Blended sessions (shared across tickets, `shared_with` present) are divided by the number of sharing tickets to avoid double counting (in interactive mode, show the split so the user can adjust).
- Existing time = sum of that ticket's Jira worklogs with **author = me & started on that date (KST)** (`getJiraIssue` fields=["worklog"]). This includes WandSol complete/pause syncs and previous corrections.
- **Difference = baseline − existing. Only when it's 10 minutes or more**, call `addWorklogToJiraIssue` (timeSpent=difference, started=that day's first session time, commentBody="Worklog correction (based on session records): <one-line work summary>", written in the output language).
- **Dedup**: record `{worklog_id, minutes, method}` in `state.json`'s `wandsol_synced[date][ticket]`. For an existing (date, ticket), decide additional time only via the difference calculation above (previous corrections are already in the Jira sum, so re-runs don't double-upload). Update with a small python snippet after `aggregate build`.
- **Never auto-upload additional time produced by re-aggregation.** If a (date, ticket) is already recorded in `wandsol_synced` and re-aggregation increased the baseline (e.g. evening work added), **don't automatically add a Jira worklog.** Instead, write the extra into `wandsol_synced[date][ticket].pending_additional_min`, and show only "additional N min (not uploaded)" in the journal (daily page notes/summary) and chat/report. Actual upload only when the user explicitly approves in interactive mode.
- **Mode**: interactive → show a table of ticket, baseline, existing, and time to add, and record after approval. auto → record without approval and just leave the result.
- Log the result (tickets/time uploaded, skipped) in chat in 1–2 lines. If the Atlassian MCP isn't connected, one line: "Jira not connected — correction skipped".

### 10) Verification (mandatory)
1. **Task DB**: as many tasks as `worklist` rows, with the **my time desc** default view and ticket/non-ticket views visible. Check that `도구` (Claude/Codex) is filled, that no tickets that should be excluded (reference mentions only) are present, and that renamed rows weren't duplicated.
2. **Daily page**: row titled D, total formula = sum of daily_totals, 📊 table present in the body.
3. **Ticket DB**: cumulatives of processed tickets match `ticket_cumulatives`.
4. **Dashboard**: the parent page shows the "last updated" timestamp just written + the verification table (including tool, my time, total time, summary, link basis, ⚠ mixed session, ⚠ shared session — in the output language), and below it the task DB → 🗂 → daily/ticket DB order is intact.
- On mismatch/failure, retry once. If it still fails, clearly report where it failed.

### 11) Save state
- `state.json` is updated by section 4's `aggregate build`. The only extra thing you touch is section 9's `wandsol_synced`.
- **Human-input-complete marker (enforce integration)**: `aggregate build` records `mode` (`auto`|`interactive`) per date. `auto` = human input pending, `interactive` = complete. Re-running an auto day with `/work-journal {date}` switches it to `interactive`. `~/.claude/enforce/bin/check.py` reads this value, so **auto mode must pass `--mode auto` exactly.**

### 12) Chat output (short)
- 2–5 lines: dates processed, one line of **my time · sessions open · max concurrent sessions · tokens · median reaction delay**, one line of **top tasks by total time (tickets and non-ticket mixed)**, 1 line of blockers/key decisions, **today's 3 plan items**, and 1 line of WandSol sync result (or not connected).
- Links: parent "📒 업무 일지" page URL (`config.notion.parent_page_url`), task DB URL (`config.notion.work_db.database_url`).
- In auto mode: record only automatic facts + the hint "fill in human time and decisions with `/work-journal {date}`".

---

## Notion schema (one-time DDL)

### Task DB (`config.notion.work_db.data_source_id`)
Already created. If it needs recreating, use `notion-create-database` (parent = parent page):
```
CREATE TABLE ("작업명" TITLE, "티켓" RICH_TEXT,
  "구분" SELECT('티켓':blue, '티켓 외':gray),
  "도구" SELECT('Claude':blue, 'Codex':green, 'Claude·Codex':purple),
  "총 시간(분)" NUMBER, "내 시간(분)" NUMBER, "Claude 작업(분)" NUMBER,
  "반응 지연(분)" NUMBER, "토큰" NUMBER, "세션 수" NUMBER,
  "첫 사용일" DATE, "마지막 사용일" DATE, "Jira 상태" RICH_TEXT, "요약" RICH_TEXT)
```
- After creating, set `is_inline=true` with `notion-update-data-source`.
- Default view: with `notion-update-view`, name it "전체 (내 시간순)", `SORT BY "내 시간(분)" DESC`.
- Extra views (`notion-create-view`, with database_id): "티켓만" `FILTER "구분" = "티켓"; SORT BY "내 시간(분)" DESC`, "티켓 외" `FILTER "구분" = "티켓 외"; SORT BY "내 시간(분)" DESC`.

### Daily DB / Ticket DB (for AI reference, existing)
- Daily DB (`{{NOTION_DAILY_DS_ID}}`) properties: 작업(분)·기획(분)·이해조사(분)·논의(분)·기타(분)·내 시간(분)·스위칭 수·토큰 합계·반응 지연 합계(분)·티켓 외 시간(분)·커밋 수·세션 수·상태 변화·하루 회고·날짜값·관련 티켓. (Keep total/ratio formulas.)
- Ticket DB (`{{NOTION_TICKET_DS_ID}}`) properties: 누적 Claude 작업시간·누적 기획/이해조사/논의/기타시간·누적 내 시간·커밋 수·세션 수·상태·요약·Jira 링크·막힌 점·시작일·완료일. (Keep total time/ratio formulas.)

## Notion writing tips (format)
- Number properties: JS number. Dates: `date:시작일:start`="YYYY-MM-DD". Selects (`상태`·`구분`): exact option names. URL/text: strings. Relations: arrays of page URLs.
- Follow `notion://docs/enhanced-markdown-spec` before writing bodies (tables as `<table>…</table>`, cells as rich text, blank lines as `<empty-block/>`). Markdown from `aggregate` is already compliant — insert as-is.
- Notion/Jira MCP tools may be deferred; load them with ToolSearch: notion-create-pages/notion-update-page/notion-fetch/notion-query-data-sources/notion-create-view/notion-update-view/notion-update-data-source, searchJiraIssuesUsingJql/atlassianUserInfo.
- **Deleting/moving rows** (e.g. removing a wrongly aggregated past row) needs `notion-move-pages`, which the auto-mode classifier may block as a shared-DB modification. If blocked, stop and ask the user for permission or manual deletion (this connector has no trash/delete tool).

## Cautions
- **Total time, Claude work, my time, sessions open, switching, concurrent sessions, tokens, reaction delay, non-ticket work, and ticket links** are computed automatically by collect — use them as-is (don't ask).
- **Don't estimate out-of-session time (planning/understanding·research/discussion), blockers, or decisions** (blank in auto; interactive uses only answered values).
- Cumulatives and the task DB are **overwritten/upserted** from `aggregate`'s `ticket_cumulatives`/`worklist` (don't add them up yourself).
- The dashboard is **overwritten** (not appended), scoped by the end marker `</table>` (verification table).
- collect automatically corrects for scheduled sessions and sidechains (no human filtering needed).
- Never record dates before `tracking_start_date` under any circumstances.
