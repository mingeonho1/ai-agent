---
name: example-one-shot-slack-followup
description: (Example pattern) Follow up on a Slack thread exactly once at the promised time — first read whether it's already been handled; if not, send a reminder message exactly once and report the result. If already handled, don't send.
---

> This file is **an example template for the one-shot Slack follow-up pattern**. Use it when someone asked you to
> "remind me again around then": at that time, check the status and nudge once only if needed. Fill in `<...>` with
> your own context.
> Core pattern: **(1) before sending, read to check whether it's already resolved, (2) send exactly once only if
> unresolved (no retry even on failure), (3) leave the result as a notification.**
>
> ⚠️ Sending a Slack message is hard to undo. Before registering an auto-send task like this, verify the wording,
> recipient, and conditions yourself.

This task is a one-shot Slack reminder. Do only the steps below in order and nothing else. (Don't use other tools such as time tracking.)

## Background
`<When, in which channel/thread, what you asked of whom, and when they replied "remind me again around then">`. Now is that time.

## Step 1: Check whether it's already resolved (read only)
Read the target thread with `slack_read_thread` (channel_id=`<channel ID>`, message_ts=`<thread parent ts>`). If the other person (`<@target member id>`) later posted a message saying it's already handled (e.g. "done"/"handled"), **don't send the reminder**; send only the step 3 notification (example text: "Looks already handled, so I didn't send the reminder").

## Step 2: Send the reminder (once only)
If there's no sign it was handled, send the text below exactly once with `slack_send_message` to the same thread (channel_id=`<channel ID>`, thread_ts=`<thread parent ts>`). Don't use channel-wide broadcast (reply_broadcast). If sending fails, don't retry; report the failure in step 3.

```
<@target member id> `<Polite reminder body — 1–3 lines on what to check/handle>`
```

## Step 3: Report the result
Notify the user of the result via Bash ("sent" if sent, the text above if skipped, "send failed: <reason>" if it failed).
```
osascript -e 'display notification "<one-line result>" with title "⏰ Reminder"'
```

When finished, report what you did in one line only.
