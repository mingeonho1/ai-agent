---
name: orchestrate-workers
description: |
  The main agent uses the orchterm orchestration MCP (orchterm-agent-orch) to dispatch worker agents
  (codex · agy · claude) into isolated git worktrees and coordinate them. When one worker is blocked and
  needs another artifact, the main agent delegates to a different worker and relays the result back.
  Preparing finished worktree work (rebase · conflict resolution · build/test) is autonomous; merging
  always requires user approval. Use for requests like "run this as worktree multi-agent", "spin up
  workers", "delegate to a worker", "have A use claude and B use codex" (Korean: "워크트리 멀티에이전트로",
  "졸병 띄워서", "워커에게 위임", "A는 claude B는 codex로 시켜"). Prerequisite: the orchterm-agent-orch MCP
  must be registered. Respond in the user's language (match the language
  the user writes in).
---

# Orchestrate Workers — multi-agent worktree coordination

You (the main agent) are the **control plane**. You dispatch worker agents into isolated worktrees to complete the parent task.
Your tool is the orchterm orchestration MCP: `open_session(ai, cwd)` → `{session_id}`, `send(session_id, message)`
→ `{reply}` (blocking: waits until the worker finishes one turn), `close_session(session_id)`. You can also query
available agents with `list_agents()`, and **the live sessions you opened (`session_id` · `agent` · `status`) with
`list_sessions(from)`** — this is the **source of truth for reuse lookups** (check with this, not your memory).
`open_session`/`close_session` are **commander-only** (rejected if a worker calls them); workers only use `send`
(reverse messages to the commander) and `orch_report`.

> **Endpoint ID & `from` parameter (required)**: each agent's endpoint id is in the environment variable `$ORCHTERM_ENDPOINT_ID`.
> When calling orch tools (`open_session`/`send`/`close_session`), **always** pass this value as the `from` argument.
> Example: `send(session_id="s_...", from="$ORCHTERM_ENDPOINT_ID", message="...")`. If `from` is not a participant in that
> session, the call is rejected (prevents hijacking someone else's session).

> **Reply channel (automatic)**: the `reply` of `send` arrives as a **structured reply** the worker sends by calling
> the `orch_report(session_id, result)` tool. The app **automatically appends** a "call orch_report when done"
> instruction to your message — you don't need to tell the worker yourself (no duplication). If the worker omits it,
> TUI output scraping catches the reply as a fallback. `Ⓜ` markers in the worker's reply come through verbatim in
> `result`, so the marker branching convention below is unchanged.

## Dispatching · stopping workers (commander must read)

`send(session_id, from, message)` **blocks** until the worker finishes and **returns the worker's answer directly** — that return value is the result. **Always take it and relay it to the user (don't discard it). No polling or re-calling needed.**

- **To keep the main agent unblocked (optional):** if you have a background subagent tool (e.g. Claude's Task/run_in_background), wrap `open_session`+`send` inside it — the subagent receives the send return value and reports to you, so the main agent isn't blocked. **If you have no such tool (codex/agy etc.), just call `send` directly** — the main agent pauses during the worker's turn, which is normal, and the user can stop an in-progress worker any time via the UI "Stop" button.
- **Stopping an in-progress worker (very important)**: when the user presses the **"Stop"** button (Korean UI: "중지") in the **orchestration dashboard** or the **commander tab's top header**, that worker is interrupted and your `send` (or the **background Task** that dispatched that worker) resolves with **`⟨중지됨 …⟩`** (the app's literal "stopped" marker, emitted in Korean). Then:
  - **Abandon that whole request immediately.** Don't `send` again, nudge, or prod. **Don't create a new worker/session.** Don't try to check the result via `get_turn_result` either.
  - Even if the background Task finished or went idle, **don't "check the result because it's done"** — termination after a stop is **not completion but a deliberate user interruption**.
  - Report only **"stopped"** to the user and wait for the next instruction. (No need to call a cancel tool yourself — the UI handles it.) The session is kept, so `send` again **only when the user explicitly asks again**.
- `from` is always your `$ORCHTERM_ENDPOINT_ID`.

## Session lifetime · reuse policy (must read)

- **Worker tabs appear next to the commander (no focus stealing)**: a new worker appears as the active tab of the
  **anchor panel/Space** where the commander lives, but **the user's currently active Space and keyboard focus do not
  change.** If the user is working in another Space, leave it alone (the worker gets ready in the inactive Space and
  is announced via a Space chip/badge); don't force a Space switch — summarize progress in your responses.
- **You may run yourself as a background task**: coordination takes a long time (`send` is blocking). If the user wants
  to do other work meanwhile, you can **run this orchestration as a Claude Code background task/agent** so it doesn't
  block the foreground conversation. (This does **not** mean dropping workers into headless `-p`/`exec` — interactive
  workers stay as they are; only the coordination loop runs asynchronously.) But **decisions you need to ask the user**
  (integration worktree mode, ambiguous worker choice, etc.) must be **collected at the start, before going to the
  background.** If a new question comes up while running in the background, proceed with the safe default (direct-merge
  mode · new domain worker) and report that assumption to the user.
- **Reuse a session once opened (when the domain fits)**: pawns are highly reusable. Don't **`close_session`
  immediately** just because one task finished. The default is to give the same worker follow-up work in the **same
  domain** via `send` (keeping session context = smarter). But reuse must be **a worker that fits that domain** — work in
  a different domain gets its own dedicated worker (create one if none exists); never dump it on an arbitrary worker or
  on the requester (see **"Worker selection rules"** below).
- **Close only on user request — absolute rule**: call `close_session` **only when the user explicitly says
  "close"/"clean up"**. Closing workers because the work is done, because it's the "wrap-up" step, or for tidiness is
  **forbidden** (an absolute rule on par with the merge gate). Keep blocked or finished workers alive — even **when all
  work is complete** — until the user says to close them. Since `close_session` is the only code path that kills a worker
  (no auto-cleanup), workers stay alive if you don't call it. Worktree cleanup (merge/delete) and closing sessions are
  **completely separate**.

## Prerequisite checks (before starting)

- Confirm the `orchterm-agent-orch` MCP tools (`open_session`/`send`/`close_session`) are visible. If not, stop
  and tell the user: "Enable agent orchestration in orchterm settings and restart."
  - ⚠️ If **multiple app instances (release + dev/worktree)** are running at once, each registers under a different key —
    release (base 0) is `orchterm-agent-orch`, dev/worktree (base>0) is `orchterm-agent-orch-dev<base>`
    (e.g. base 8 → `orchterm-agent-orch-dev8`). They coexist without overwriting each other, so **decide which app to
    launch workers in and use that instance's tools** (for dev-app testing, the `...-dev<base>` tools).
- Confirm the target branch (usually the current working branch) and the repo root.
- **Ask the user whether to use an integration/collection test worktree (at task start, required).** Ask whether to create
  a dedicated worktree that **gathers all workers' output in one place for a final combined build/test**, and proceed
  **as answered**. Don't decide on your own.
  - **Create it (integration worktree mode)**: `git worktree add .worktrees/<task>-integration -b
    orch/<task>-integration <target>`. As each worker reports `Ⓜ DONE` (+commit), merge its branch into this integration
    worktree to **collect** it; after all workers finish, **build/test the combined whole here** (verify the integrated
    result, not per-worker isolated tests). After approval, merge the integration branch into the target.
  - **Don't create it (direct-merge mode)**: the default — prepare/test each worker branch separately, then merge it into the target.
  - Fix the mode and follow it in the "Integration" step below.

## Worker selection rules — every time before assigning a task/subtask (must read)

Whether it's a new request or a worker's NEED, decide **which worker gets it** in this order:

1. **Identify the task domain** (e.g. backend, frontend, DB, code review, docs…).
2. **Check whether a dedicated worker for that domain already exists** — **always query live sessions
   (`session_id` · `agent` · `status`) with `list_sessions(from=$ORCHTERM_ENDPOINT_ID)`** and cross-check against your
   memory (each worker's domain). Don't rely on memory alone — a worker whose reply was empty or late still has a live
   session, so recover it via `list_sessions` and reuse it.
   - **If one exists**, **reuse** it (continue via `send` — **don't reopen**).
   - **If not**, **create** a worker for that domain (`open_session`).
3. **Never hand a NEED back to the requester itself (absolute).** E.g. if a backend worker is blocked with "need DB work",
   **giving the DB work to that backend worker is pointless** — always pass it to a **different** (DB-dedicated) worker.
   A NEED means "I can't / won't do this, someone else please do it."
4. **If it's ambiguous whether to reuse or create → ask the user.** Present the current worker list (`<agent> · <commander>`
   + the task each worker owns) and ask **"Should I create a new worker, or reuse one of these?"**, then proceed with the
   answer. **Don't decide on your own.**
   - E.g. a **backend** task comes in but the only nearby-domain worker is a **'code review'** one — it's ambiguous whether
     to reuse that worker for backend too or create a dedicated backend worker → present the worker list and ask the user.

## Coordination loop (turn-based pull, driven by you)

A worker **ends its turn and makes a request when blocked** (you receive that response and branch). Workers never poke
you asynchronously first in the middle of work.

> **Bidirectional messaging**: a session is a 1:1 channel dedicated to two parties (the commander who opened it ↔ the
> opened worker). **Workers too** can **speak to the commander first** by calling `send(session_id, from=$ORCHTERM_ENDPOINT_ID, message)`
> with their own session id. Each turn's reply is returned by the receiving side via `orch_report(session_id, result)`
> (same as before, no `from` needed).

1. **Create worker A's worktree**: `git worktree add .worktrees/<task> -b orch/<task>` (based on the target branch).
   - Windows: run `npm install` separately in the worktree (don't share node_modules via junction —
     `git worktree remove` deletes the original).
2. **Open A and instruct it**:
   ```
   sid_a = open_session(ai="claude", cwd="<repo>/.worktrees/<task>")
   send(sid_a, "<task description>\n\n[Convention] If you get blocked needing an artifact another agent must produce,
                stop and end your turn with 'Ⓜ NEED: <what you need>'. When everything is done, **always commit your
                changes to git first**, then end with 'Ⓜ DONE: <summary> | docs: <path>' — without a commit the
                integration step can't see your changes.")
   ```
3. **Branch on A's response (send return value)**:
   - **`Ⓜ NEED:` (or natural language like "I need ~")** → delegate to **a worker matching that need's domain**.
     Worker choice follows the **"Worker selection rules"** above (reuse a dedicated domain worker if one exists / create
     one if not / ask the user if ambiguous). **Don't hand it back to requester A.**
     ```
     # e.g. A (backend) sends a "need DB work" NEED → secure a DB-domain worker
     sid_db = <existing DB worker sid>      # reuse if it exists
            or open_session(ai="codex", cwd="<repo>/.worktrees/<task>-db")   # create if not (pick ai by fit)
     reply_db = send(sid_db, "<concrete task derived from A's need> ... **commit, then** end with 'Ⓜ DONE: <summary> | docs: <path>'")
     # relay reply_db's docs path/result to A
     send(sid_a, "Ⓜ RESOLVED: <summary of reply_db result> | docs: <path>")
     ```
     Then repeat this branching on A's next response.
   - **`Ⓜ DONE:` (or natural-language completion)** → go to the integration step.
   - **Blocked/error/timeout** → safeguards (below).
4. **Agent choice (cross-agent)**: pick `ai` by task fit — design · coding = claude, code review · execution
   verification = codex, UI · exploring alternatives = agy. Multiple workers of the same kind are fine.
5. **Passing results/docs**: workers share the same filesystem. Just relay the path string.

## Marker convention

| Direction | Marker | Meaning |
|------|------|------|
| worker→main | `Ⓜ NEED: <request>` | Blocked — needs another artifact |
| worker→main | `Ⓜ DONE: <summary> \| docs: <path>` | Done — **changes committed to git** |
| main→worker | `Ⓜ RESOLVED: <result> \| docs: <path>` | Delivers the resolved request |

- **Committing before DONE is mandatory (absolute).** A worker must **commit its changes** in its worktree before sending
  `Ⓜ DONE` — otherwise the integration step's `git diff <target>...HEAD` and rebase can't see the changes, producing
  "says it's done but the diff is empty." If a worker sends DONE without committing (revealed at integration as a dirty
  working tree / no changes on HEAD), the main agent uses the next `send` to correct it — **"commit your changes, then
  send `Ⓜ DONE` again"** — and only then proceeds with integration.
- Even without markers, interpret the response in natural language and branch (markers are a robustness aid). If a worker
  breaks the convention, correct it with the next `send`: "Tell me again in `Ⓜ NEED`/`Ⓜ DONE` format."

## Integration — **always get user approval before merging** (HARD GATE)

When a worker reports `Ⓜ DONE`, handle it **according to the mode chosen at the start (integration worktree / direct merge)**:

**A) Integration worktree mode**: for each worker's DONE, after step 0 (commit check), collect that worker's branch into
the integration worktree (`git -C .worktrees/<task>-integration merge orch/<task>-<worker>`, resolve conflicts by "keep
both sides"). **When all workers are done**, **build/test the combined whole** in the integration worktree (apply step 1
verification to the integrated result) → step 2 approval request (present the integrated result) → on approval, **merge
the integration branch into the target** (step 3). Don't merge individual workers separately.

**B) Direct-merge mode**: perform steps 0–4 below for each worker.

0. **Commit check (mandatory first)**: first confirm **the worker actually committed** with `git -C .worktrees/<task> status --porcelain`
   + `git -C .worktrees/<task> log <target>..HEAD --oneline`. If there are uncommitted changes in the working tree or no
   commits in `<target>..HEAD` (= "says it's done but didn't commit"), stop integration and **`send` that worker "commit
   your changes, then send `Ⓜ DONE` again"**, then go to step 1. (Integration worktree mode also runs this step 0 first.)
1. **Prepare (autonomous)**: review the changes with `git -C .worktrees/<task> diff <target>...HEAD` → rebase that worktree
   onto the latest target branch → resolve conflicts by "keep both sides" (benign conflicts where each side added
   something different) → **verify with build/test** (`npm run build` + `npx vitest run`; for Rust changes,
   `cargo test --manifest-path src-tauri/Cargo.toml`).
2. **Request approval (gate)**: present the following to the user and **explicitly request merge approval**:
   change summary · `git diff --stat` · test results. "Merge this into <target> as is?"
3. **Only on approval**: `git -C <repo> merge --ff-only orch/<task>` → `git worktree remove .worktrees/<task>`.
   **Keep the session (`sid`) alive, don't close it** (reuse policy) — give follow-up work to the same session.
   `close_session` only when the user asks for cleanup (worktree cleanup and closing sessions are separate).
4. **Not approved / waiting**: **never merge.** Wait with the worktree, branch, and session preserved.

> This gate is an absolute rule. Under no circumstances merge into the target branch without user approval.
> (Worker B's worktree for an intermediate artifact is usually not a merge target — even after A consumes its docs,
> **keep B's session alive** (reuse it for later artifacts). Remove the worktree with `git worktree remove` only when
> it's pure scratch and definitely won't be used again; `close_session` only on user request. If B's changes must land
> in the target, apply the same gate.)

## Safeguards

- **Delegation depth ≤ 3**: A→B→C only. If it goes deeper, stop and report to the user (prevents runaway/circular delegation).
- **Worker failure** (error/timeout): retry once → if it still fails, escalate to the user. No infinite retries.
- **Real semantic conflicts** (rebase conflicts that benign "keep both" can't resolve): escalate to the user.
- **Don't blanket-kill dev apps from other worktrees** (CLAUDE.md): clean up only what you launched.
- **Parallel vs sequential coordination**: `send` is blocking (waits for one worker turn), but **independent** workers can
  run in parallel by **calling multiple `send`s at once** in one turn (wall clock = slowest worker, not the sum). Rules:
  - **No concurrent `send` to the same session** — the engine rejects it with `session busy` (one worker, one turn at a time; PTY input would interleave).
  - **Dependencies are sequential** — if one worker's output is another's input, B starts after receiving A's reply (A→B).
  - **Keep concurrent workers to 3–4 or fewer** — beyond that, PTY/IPC backpressure is untested (fall back to sequential if excessive).
  - The delegation loop (NEED→B) is inherently sequential (dependent), but **N unrelated subtasks** are distributed via parallel `send`s.

## Wrap-up

Sessions are **kept by default for reuse** — `close_session` only when the user explicitly says "clean up/close". At
wrap-up, report the list of open sessions and the state (branch · path) of unmerged worktrees to the user, and **ask
whether to close them** (don't close them on your own).
