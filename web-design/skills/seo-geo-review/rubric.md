# SEO + GEO review rubric

Single source of truth for checks, severity and pass bars. `scripts/seo_check.py` implements it; keep the `CHECKS` table there and this file in sync.

Contents: 1 Severity · 2 Checks · 3 Scoring · 4 Bars · 5 Limits · 6 Sources

## 1. Severity (상/중/하)

| 등급 | Meaning | Blocks |
|---|---|---|
| **상** | Page cannot be indexed, shown or read by crawlers at all | every bar |
| **중** | Real loss of ranking, rich results or AI citation, with a workaround | beta (more than 3), prod (any) |
| **하** | Hygiene. Reported, never blocks | nothing |

상 checks are pass/fail only (no partial credit). 중/하 may be partial; a partial check counts as a fail for the 상/중/하 tally, and the report shows the points it lost.

## 2. Checks (100 points)

Evaluated on the raw HTML (what a non-JS crawler sees). `n/a` = awarded in full.

| id | category | pts | sev | pass rule | why |
|---|---|---|---|---|---|
| T1 | 기술 | 3 | 중 | `<html lang>` non-empty | language targeting, screen readers |
| T2 | 기술 | 5 | 상 | `<title>` exists | the primary result title |
| T3 | 기술 | 2 | 하 | title 10–60 chars | longer titles get truncated |
| T4 | 기술 | 4 | 중 | meta description exists | default snippet source |
| T5 | 기술 | 1 | 하 | description 50–160 chars | snippet length |
| T6 | 기술 | 3 | 중 | `link rel=canonical` with href | avoids duplicate-URL splitting |
| T7 | 기술 | 5 | 상 | no `noindex` in meta robots/googlebot (or `X-Robots-Tag` for URLs) | noindex removes the page from search |
| T8 | 기술 | 2 | 중 | viewport has `width=device-width` | mobile-first indexing |
| O1 | 온페이지 | 5 | 상 | exactly one `<h1>` | topic signal for crawlers and LLM chunkers |
| O2 | 온페이지 | 2 | 하 | no heading level skip (h2→h4) | structure parsing |
| O3 | 온페이지 | 4 | 중 | ≥90% of non-decorative images have non-empty alt (decorative = `alt=""`, role=presentation/none, aria-hidden). 70–89% = partial 2. No images = n/a | image search, accessibility |
| O4 | 온페이지 | 4 | 중 | og:title + og:description + og:image. Two of three = partial 2 | link previews, AI answer cards |
| O5 | 온페이지 | 1 | 하 | twitter:card | X previews |
| O6 | 온페이지 | 2 | 하 | no link text like 자세히 보기 / 더 보기 / Learn more / click here (after trimming arrows/punctuation) | anchor text is a relevance signal |
| O7 | 온페이지 | 2 | 하 | `link rel` containing `icon` | favicon shown in results |
| S1 | 구조화 | 5 | 중 | ≥1 JSON-LD block and all parse. Some parse = partial 3 | prerequisite for rich results |
| S2 | 구조화 | 5 | 중 | has Organization, LocalBusiness (or common subtype: Restaurant, Store, …), Product, Offer or Service (nested nodes count) | tells engines who/what the page is |
| S3 | 구조화 | 5 | 중 | page has a heading matching FAQ / 자주 묻는 / 자주 하는 질문 ⇒ FAQPage JSON-LD whose question names all appear in visible text (≥half = partial 3). No FAQ section = n/a | FAQ markup that does not match the page is spam |
| G1 | GEO | 5 | 중 | robots.txt does not `Disallow: /` for GPTBot, ClaudeBot, PerplexityBot, Google-Extended, OAI-SearchBot (own group, else `*`; `Allow: /` overrides). Some blocked = partial 2; all = 0; **no robots.txt = partial 3** | blocked bots cannot cite you |
| G2 | GEO | 3 | 하 | `llms.txt` exists at site root and is non-empty | emerging site summary for LLMs |
| G3 | GEO | 6 | 상 | visible text in initial HTML ≥ 500 chars (script/style/noscript/template/svg/head excluded) | most AI crawlers do not run JS; an empty shell is invisible |
| G4 | GEO | 4 | 중 | first `<p>` after the first `<h1>` is 20–200 chars and has an entity cue (…입니다/제공/운영/판매/배송/전문, is/provides/offers…). 201–320 chars = partial 2 | LLMs quote the opening statement as the definition |
| G5 | GEO | 3 | 중 | FAQ answers (p/dd/details under the FAQ heading, else JSON-LD answers) are all 40–400 chars and not questions (≥half = partial 1). No FAQ = n/a. Answer-first wording is judged only in the optional content pass | quotable, self-contained answers |
| G6 | GEO | 2 | 하 | ≥5 distinct numbers with units / prices / times in visible text (3–4 = partial 1) | concrete facts are what gets cited |
| G7 | GEO | 2 | 중 | email, phone (also `mailto:`/`tel:`) or address / 사업자 info as text | trust and entity grounding |
| P1 | 성능 | 4 | 중 | every `<img>` has width and height (≥half = partial 2). No images = n/a | prevents layout shift (CLS) |
| P2 | 성능 | 3 | 하 | images after the first two have `loading=lazy` (≥half = partial 1) | saves bandwidth |
| P3 | 성능 | 4 | 중 | no `<script src>` in head without defer/async/`type=module` (one = partial 2) | render blocking |
| P4 | 성능 | 2 | 하 | HTML ≤ 200 KB | crawl/parse budget |
| P5 | 성능 | 2 | 하 | if Google Fonts used: preconnect (googleapis/gstatic) 1 + `display=swap` 1. Not used = n/a | font loading |

Category totals: 기술 25 · 온페이지 20 · 구조화 15 · GEO 25 · 성능 15.

## 3. Scoring

`total = sum of earned points`. Grade: A ≥90, B ≥80, C ≥70, D ≥60, else F. Same input, same score. The optional Claude content pass is never added.

## 4. Bars

| 기준 | 언제 | 통과 조건 |
|---|---|---|
| `poc` (기본) | PoC, 내부 데모 | 상 0건, 60점 이상 |
| `beta` | 외부 베타, 파일럿 | 상 0건, 중 3건 이하, 75점 이상 |
| `prod` | 정식 출시 | 상 0건, 중 0건, 90점 이상 |

## 5. Limits

- Raw HTML only: no JS execution, external CSS/JS and images are not fetched. A page that is empty until JS runs fails G3 by design.
- Heuristics (G4, G5, G6, G7, O6) approximate quality; they can miss or over-credit. Use the content pass for judgement.
- Local targets: site root = the HTML file's directory; `robots.txt`/`sitemap.xml`/`llms.txt` are read from there. `sitemap.xml` is reported but not scored.
- Fetching: target + three root files only, 10 s timeout, UA `seo-geo-review`, same-host redirects for root files.

## 6. Sources

Google Search Central (title/description/canonical/robots meta/structured data/FAQ rich results), Open Graph protocol, schema.org, llmstxt.org, OpenAI/Anthropic/Perplexity/Google crawler docs (GPTBot, OAI-SearchBot, ClaudeBot, PerplexityBot, Google-Extended), web.dev (CLS, lazy loading, font-display). Wording is original.
