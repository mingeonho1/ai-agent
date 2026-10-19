---
name: example-announce-only-reminder
description: (Example pattern) An announce-only reminder that just says "it's time to do this" at a specific moment — no lookups or changes, only guidance; at the end it asks once whether to start. Respond in the user's language (match the language the user writes in).
---

> This file is **an example template for the one-shot / specific-date reminder pattern**. Fill in the `<...>` parts
> with real content and register it as your own Scheduled Task. Don't put real ticket numbers, dates, links, or
> people's names here; fill them in with your own context when registering.
> Core pattern: **don't execute the work — deliver only facts + a checklist, and at the end get the user's decision
> with "Shall I start?"**

Deliver a reminder to the user. Respond in the user's language (match the language the user writes in). Don't execute the work, only give guidance (no lookups or changes).

## What to deliver
**⏰ <One line on what it's time to do>.**
<One or two lines of background — why now, what promise/plan it was. E.g. "Not the main ticket; a post-completion check">

### Checklist
1. <Item 1 to check — where and what to compare/inspect>
2. <Item 2 to check>
3. <Item 3 to check>
4. <If there's a pre-work snapshot/baseline to compare against, its path/doc>

### Reference links
- Jira: https://{{JIRA_SITE}}/browse/{{JIRA_PROJECT_KEY}}-123
- Related doc: <Notion/wiki doc link>

At the end, ask "<One line asking whether to start — e.g. Shall I start now? Say the word and I'll begin by looking up ~.>"
