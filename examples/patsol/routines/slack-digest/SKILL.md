---
name: slack-digest
description: Every hour, distill "the Slack I need to look at now" into at most 10 items by importance and save them to slack-items.json (a local JSON file you can show in any dashboard or status bar). Includes FYI (1) items; only newly appeared important items (4+) trigger a notification. Respond in the user's language (match the language the user writes in).
---

Cost-saving rule: do not perform this task yourself. Use the Agent tool to spawn one subagent with subagent_type "general-purpose", model "sonnet", run_in_background false, and pass the full [Task] text below verbatim as its prompt. Call no other tools; when the subagent finishes, relay its result as-is — if normal, output the single character "-"; if it reported a save failure, output that one-line error and stop.

[Task]
You are the Slack classifier for {{USER_DISPLAY_NAME}} (Slack user ID: {{SLACK_USER_ID}}, handle {{SLACK_HANDLE}}). Quietly pick out only "what I need to look at now" and save it. If Slack tools aren't visible, load them with ToolSearch by searching "slack". Use only read tools on Slack — sending messages, replying, emoji reactions, and drafting are strictly forbidden. Write summaries in the user's language (match the language the user writes in).

1. Read state:
   - Collection baseline (window start) = now - 48 hours. Every run re-scans the last 48 hours. `last_run` in the items file is only for staleness checks and is not the collection baseline; step 6 writes it.
   - Previous items: read the existing `{{CLAUDE_DIR}}/example-profiles/patsol/slack-items.json` if it exists (`{"last_run": ..., "items": [...]}`; each item has id·ts·importance·summary·url). Use them to decide which ids "already existed" (used in step 5 merge and step 7 notification).

2. Collect (read-only; keep the number of searches at the existing level — mention/keyword searches + reading DM and group-DM channels): from messages in the last 48 hours (after now - 48 hours), gather "what I need to look at now". Set each search/channel read's oldest/after (or equivalent time filter) to the unix ts of 48 hours ago — widen only the time range, don't add searches.
   - Messages that directly mention me (<@{{SLACK_USER_ID}}>)
   - DMs to me / group DMs I'm in
   - New replies in threads I've posted in
   - Messages whose text explicitly names me or my handle ({{USER_DISPLAY_NAME}}·{{SLACK_HANDLE}})
   - In channels I'm a member of: @channel/@here/@everyone, or messages that ask everyone including me to act (accept, configure, submit, confirm, attend, etc.) or to take note of an announcement, e.g. "everyone/all/each of you" or the Korean equivalents "각자/모두/전원/다들/여러분" (kept in Korean because they must match Korean Slack messages)
   - Announcements/decisions affecting my Jira tickets ({{JIRA_PROJECT_KEY}}-xxxx) or deadlines

3. Importance (1–5, 5 = most important):
   - 5 = a request, question, or decision directed at me that I haven't responded to yet
   - 4 = DM or mention
   - 3 = new reply in a thread I participated in
   - 2 = announcement/decision affecting my tickets ({{JIRA_PROJECT_KEY}}-xxxx) or deadlines
   - 1 = plain FYI — only announcements/decisions in channels I'm a member of that relate to my tickets/work. Exclude chit-chat and announcements unrelated to me.

4. Exclude: messages I sent, bot noise, plain chit-chat, 1:1-style conversations unrelated to me, and "already resolved" items. Resolution rule: if I replied to (or handled) the message/thread after that message, treat it as resolved and exclude it. A thread counts as resolved if, since my last post, there's no new request awaiting my response.

5. Merge previous items (dedupe by id in slack-items.json):
   - Of the previous items read in step 1, keep those still unresolved (I haven't replied/handled since) whose ts is within 48 hours of now.
   - Drop those that are resolved or older than 48 hours.
   - If the same id is caught again this run, update it with the new content (never insert the same id twice).

6. Save (always): combine kept + new items, sort them (importance desc, then ts desc), cut to the top 10, and write the JSON below to `{{CLAUDE_DIR}}/example-profiles/patsol/slack-items.json` (create the directory if needed), setting `last_run` to the current time (ISO8601). Keep importance 1 (FYI) items in the list too — don't drop them for being 1 point (only drop step 4's exclusions: bot noise, already resolved, already replied to by me, chit-chat).
   Each item: id="<channel_id>:<message_ts>", importance=1–5, summary=one line within 90 characters, channel="#channel-name" ("DM" for DMs), from="sender display name", ts=message time (float), url=Slack permalink, reason=request|mention|dm|thread|decision|fyi.
   ```
   {"last_run":"<ISO8601 now>","items":[{"id":"C0EXAMPLE:<MSG_TS>","importance":5,"summary":"Request to upload seminar materials (no reply yet)","channel":"#announcements","from":"Teammate","ts":1699900000.001,"url":"https://{{SLACK_WORKSPACE}}.slack.com/archives/C0EXAMPLE/p<MSG_TS>","reason":"request"}]}
   ```
   If there's nothing to look at, save only the kept items (or `{"items":[]}`). If the write fails or the JSON would be invalid, it's a save failure — in step 9 output a one-line error instead of "-".

7. Notification (conditional, at most once): send only if at least one item that is "new" this run (its id was not among step 1's previous items) has importance 4 or higher.
   ```
   osascript -e 'display notification "<summary of the single most important item, within 100 characters>" with title "Slack"'
   ```
   (macOS example; use any notifier you like on other systems.) If there are no new important items (4+), don't send a notification.

8. State update: nothing separate — step 6 already recorded `last_run` in the items file.

9. Final response: if the save succeeded, just the single character "-". If the save failed, output "slack-digest save failed: <one-line reason>" instead of "-".
