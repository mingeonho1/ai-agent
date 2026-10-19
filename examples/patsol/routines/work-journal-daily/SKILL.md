---
name: work-journal-daily
description: Weekdays 09:30 — auto-summarize the previous weekday's work + backfill missed weekdays + refresh the cumulative dashboard, and recommend today's plan. Respond in the user's language (match the language the user writes in).
---

Run the work-journal skill in auto mode. (Assumes the Notion and Jira MCPs are connected.)

Goal: every weekday morning, automatically summarize yesterday's (the previous weekday's) work per ticket, set today's plan, and record it in Notion.

How to run:
1. Invoke the work-journal skill (argument: `auto`). The skill follows the procedure in ~/.claude/skills/work-journal/SKILL.md.
2. If the skill is missing or fails to load, Read SKILL.md directly and follow its procedure.
3. If a required MCP tool (Notion, Jira, WandSol) isn't visible in this session, load it with ToolSearch. If it's still missing after loading, stop at that step and report what was missing and what couldn't be done (never skip silently).

auto mode behavior (summary):
- Read ~/.claude/worklog/config.json and state.json.
- Target = the previous weekday. If weekdays after state.last_processed_date were missed, backfill them too (at most backfill_max, oldest first).
- **Re-aggregate evening work for days the human closed early**: even if state.json `daily[date].mode == "interactive"`, a day that is **still `confirmed != true` and falls within "the previous weekday + any unconfirmed days after it"** is included, and `aggregate build … --mode auto --reaggregate` re-aggregates only the auto-collected numbers (time, tokens, sessions, commits, work list) through the end of the day. **Human-entered qualitative fields, manual rows, retro, plan, and summaries are preserved** and mode stays interactive (aggregate handles this). Once re-aggregated as a past day it becomes `confirmed=true` and is skipped from the next run on. **Never touch days already `confirmed=true`**. If there is nothing to re-aggregate, leave the Notion daily/ticket entries alone and only refresh the dashboard and today's plan.
- **WandSol Jira worklog correction (work-journal section 9)**: a **new date** being aggregated for the first time is in auto mode, so per section 9 the difference between session-based time and existing Jira time is uploaded automatically **without approval** (only when the difference is 10 minutes or more). However, **additional time from re-aggregation on tickets already synced (`wandsol_synced`) must not be auto-uploaded** — don't add a worklog to Jira; record it in `pending_additional_min` and only report "additional N min (not uploaded)". (If the Atlassian MCP isn't connected, one line: "Jira not connected — correction skipped".)
- For each date, gather only automatic facts via collect.py (auto-collects sessions, commits, tickets) + a Jira query (status/summary of tickets assigned to me).
- Values only a human knows (planning/understanding·research/discussion/other time, blocker causes, decision reasons) are left blank without asking (nobody is there to answer).
- Compute cumulatives, the dashboard, and number tables with aggregate.py build, then update the Notion daily page + ticket DB + the cumulative dashboard on the parent page (overwrite).
- Recommend 3 items for today's plan (based on Jira in-progress/to-do + yesterday's blockers).
- Finally, re-read the daily page, ticket DB, and dashboard to verify the updates; on failure, retry once and then report.

Completion notice (leave as this session's result):
- Dates processed, Claude work time per ticket (h:mm), today's 3 plan items, the daily page link, and the parent "📒 업무 일지" page link (the live Notion page title; keep verbatim).
- Since human time/decisions were left blank, include the hint: "Today, run `/work-journal {date}` to fill in planning/understanding/discussion time and decisions."

Caution: never touch ~/.claude/settings.json.
