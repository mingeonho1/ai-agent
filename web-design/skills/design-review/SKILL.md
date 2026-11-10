---
name: design-review
description: Scores a page or app screen against a common design bar and reports 상/중/하 findings, a 0-100 score and pass/fail for the poc, beta or prod bar. Read-only on project source (writes only .design-review/). Use for "디자인 검수", "디자인 점수", "AI 티 나는지 봐줘", "PoC 디자인 기준 넘었어?", "/design-review".
argument-hint: "[path|url] [--bar poc|beta|prod] [--app]"
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/score.py *), Bash(node *sloplint.mjs *), Bash(node ${CLAUDE_SKILL_DIR}/scripts/measure.mjs *), Bash(node --version), Bash(git diff *), Bash(mkdir -p .design-review*), Bash(find *), Edit(.design-review/**), Write(.design-review/**)
---

# design-review

Measure a UI against `rubric.md` and report a score. Writes only under `.design-review/`; never edits project source. Offer fixes only after the report, and run them by §6.

## Context

Codex: `${CLAUDE_SKILL_DIR}` is this skill's install directory (`~/.agents/skills/design-review`) and the `!` lines are Claude-only, so run those checks yourself.

- Hallmark sloplint: !`ls ~/.claude/skills/hallmark/scripts/sloplint.mjs ~/.agents/skills/hallmark/scripts/sloplint.mjs 2>/dev/null | head -1 || true`
- Brand / waiver files: !`ls DESIGN.md design.md docs/DESIGN.md docs/design.md STYLE_GUIDE.md .design-review/waivers.md 2>/dev/null || true`
- Changed UI files: !`git diff --name-only HEAD 2>/dev/null | grep -E '\.(html|css|scss|jsx|tsx|vue|svelte|astro)$' | head -20 || true`
- Arguments: $ARGUMENTS

## 1. Resolve the run

- **target**: the path or URL in the arguments. None given → the changed UI files above; none of those either → ask once.
  Framework project (Next, Vite, etc.) → review a URL, not source files; if no URL was given, ask the user for it (don't probe ports).
- **bar**: `--bar` value, default `poc`.
- **surface**: `app` when `--app` is given or the target is a dashboard, admin, settings or form screen; otherwise `page`.
- **run dir**: `.design-review/run-<YYYYMMDD-HHMMSS>/` (create it). Don't edit `.gitignore`; mention once in the report if `.design-review/` is not ignored.

## 2. Lint (optional, deterministic)

Sloplint path above is empty → write one line `lint 건너뜀 — Hallmark 미설치 (npx skills add nutlope/hallmark -g)` and go to §3.

Otherwise, from the run dir:

```bash
node <sloplint> <path> --json --render > lint.json          # local file or directory
node <sloplint> --url <URL> --json --render > lint.json     # running site
```

Add `--scope app` when surface=app.

- Exit 1 means findings and is normal. Exit 2 or invalid JSON → treat as no lint and say why in one line.
- `--render` needs `puppeteer-core` and Chrome; if the summary says the render tier did not run, keep the static result and note it.
- Collect the screenshots it wrote: `find <run dir> <target dir> -path '*shots*' -name '*.png' -newer <run dir>`.

## 2b. Measure (optional, deterministic)

If the target is a URL or a local HTML file (relative or absolute path), just run it:

```bash
node ${CLAUDE_SKILL_DIR}/scripts/measure.mjs <url-or-file> --out <run dir>
```

It writes `shot-1440.png`, `shot-768.png`, `shot-375.png` (+ `shot-<w>-full-<n>.png` tiles when capture did not time out) and `measure.json` (overflow at 320–1920, 375px tap targets, input font-size/type/inputmode/autocomplete, h1 and primary CTA bottom vs 812, fixed/sticky elements, console errors). Add the screenshots to the reviewers' `screenshots` and pass `measure: <run dir>/measure.json`.
Exit 2 (no Chrome / Node < 22) → skip the measurement: one line `측정 건너뜀 — <reason>`, `measure: none`, continue. If Chrome is not auto-detected, `--chrome <path>` or `CHROME_PATH` points to it.

## 3. Fresh-context review (two independent runs)

Reviewer agent not installed → tell the user to install the package (`python3 <ai-agent repo root>/scripts/install.py <claude|codex> --user --package web-design`) and stop; do not review in this thread, since the context that built the page is its weakest reviewer.

Spawn two fresh read-only reviewer subagents in the same message, so they run in parallel and never see each other. Claude uses `design-reviewer`; Codex uses `design_reviewer` (a new thread per run with `spawn_agent`, never `resume_agent`, no inherited context). Give each its own browser tab or page. Pass paths and facts only, never your own opinion of the design:

```
target: <target>   surface: <page|app>
rubric: ${CLAUDE_SKILL_DIR}/rubric.md
screenshots: <png paths, or none>
lint: <run dir>/lint.json or none
measure: <run dir>/measure.json or none
brand: <brand file paths, or none>
browser: use only tab <id>
```

Save each JSON block exactly as returned to `<run dir>/review-a.json` and `review-b.json`. If a reply has no valid JSON, re-ask that agent once for the JSON only. If one run still fails, score the other alone and say the result is single-run.

Reviewers never see previous rounds' results (keeps each run independent); `score.py` compares rounds itself under `지난 검수 대비`.

Scorer counts 상 only if both runs flag it; score = mean.

## 4. Score

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/score.py --review <run dir>/review-a.json --review <run dir>/review-b.json [--lint <run dir>/lint.json] --bar <bar> [--waivers .design-review/waivers.md] --out-dir .design-review
```

Exit 1 means the bar was not met. Exit 2 means bad input (message on stderr): fix the review JSON from the reviewer's reply and rerun; never hand-compute a score.

## 5. Report

Show the script's markdown as-is, in Korean, then at most three lines of your own:
- the one change that would raise the score most;
- for a failed bar, what must change to pass it (from `fail_reasons`);
- whether to fix 상 items now (needs the user's go-ahead).

Never present a score you did not get from `score.py`.

## 6. Fix round (only on the user's go-ahead)

Fix in the main thread with these constraints.

Fixing to one review's wording overfits: a patch tends to add a new tell, and the next run finds older issues the last one missed. Fix to the rubric, not to the report.

- Fix only design items under 상/중/하. Leave `제품 결정 필요` items to the user. Fix a `재확인 필요` item only if you can reproduce it.
- Hard constraints: the rubric's 상 lines (§1 test, §2 상 block, §2a 상 block); a fix may not add a 상 tell (example: disabling a form with `opacity` alone is `39a`). Check your own diff against them before handing back.
- A change that re-composes layout (column count, hero arrangement, section order, removing or adding sections) needs the user's go-ahead first, even when a finding suggests it.
- Also check: status/announcement regions (`role=status`, `aria-live`) are not hidden from assistive tech; at 375 no fixed/sticky element covers a CTA or a focused input; `:active`/`:hover`/`:disabled` states keep text contrast; if the site has language or variant pages, every one of them got the same fix.
- Smallest change that solves the user's problem. No new sections, and no copy written to satisfy a reviewer phrase; prefer removing to adding.
- Re-run §3–§5 on the result. Stop after two rounds with no gain in the two-run mean and report what is left; further rounds chase reviewer noise.
