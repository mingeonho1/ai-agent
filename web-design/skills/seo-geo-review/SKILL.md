---
name: seo-geo-review
description: Scores a page 0-100 for SEO + GEO (AI-search citability), lists what is missing tagged 상/중/하 with a one-line fix each, and reports pass/fail against the poc, beta or prod bar. Never modifies project source. Use for "SEO 검수", "GEO 점수", "AI 검색 노출 봐줘", "PoC SEO 기준 넘었어?", "/seo-geo-review".
argument-hint: "[path|url] [--bar poc|beta|prod]"
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/seo_check.py *)
---

# seo-geo-review

Measure a page against `rubric.md` and report a score. Read-only: the script fetches only the target and its root files (`/robots.txt`, `/sitemap.xml`, `/llms.txt`) and writes only under `--out-dir`. Offer fixes only after the report.

Codex: `${CLAUDE_SKILL_DIR}` below means this skill's install directory (`~/.agents/skills/seo-geo-review`). Arguments: $ARGUMENTS

## 1. Resolve the run

- **target**: the path or URL in the arguments. An HTML file, a site directory containing `index.html`, or an `http(s)` URL. None given → ask once.
  Framework project with a running dev server → pass the URL, not source files (SSR output is what crawlers see). No server → ask for the URL or the build output directory.
- **bar**: `--bar` value, default `poc`.
- **out dir**: `.seo-geo-review` (the script creates it). Don't edit `.gitignore`; mention once in the report if `.seo-geo-review/` is not ignored.

## 2. Run

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/seo_check.py --target <target> --bar <bar> --out-dir .seo-geo-review
```

Exit 0 = bar met, 1 = bar not met (both print the report), 2 = bad input: show stderr, ask the user once for a corrected target and rerun; don't loop; never hand-compute a score.
`--json` prints the result as JSON (for filtering by severity).

## 3. Report

Don't echo the whole markdown. In Korean, show the report header, the 상/중/하 counts, and the 상 and 중 failures (filter via `--json`); point to `.seo-geo-review/` for the full result. Then at most three lines of your own:
- the one change that would raise the score most;
- for a failed bar, what must change to pass it (from the `미달` reasons);
- whether to fix 상 items now (needs the user's go-ahead).

Never present a score you did not get from `seo_check.py`.

## 4. Content pass (optional)

Only if the user asks (e.g. "내용도 봐줘") or accepts your offer. Read only the first h1, the first paragraph and the FAQ section (not the whole page) and give at most 5 bullets under the heading `내용 점검 (점수 미반영)`, kept apart from the report:
- does the first paragraph say what / who / where without jargon;
- are FAQ answers conclusion-first and quotable on their own;
- are claims backed by a number, source, date or named author;
- does the title/description match what the page actually offers.

These never change the score, the bar result or the 상/중/하 counts.
