# Design review rubric (common design bar)

Single source of truth for severity, scoring and pass bars. `scripts/score.py` implements §4–§5; the `design-reviewer` agent applies §1–§3.

Contents: 1 Severity · 2 Concrete tells · 2a Mobile · 2b Typeface · 3 Heuristics · 4 Score · 5 Bars · 6 Waivers · 7 Credits

## 1. Severity (상/중/하)

Tiers follow Hallmark's Floor / Reflex / Finish model.

| 등급 | Hallmark tier | Meaning | Waivable | Equivalent |
|---|---|---|---|---|
| **상** | Floor | Broken, inaccessible or dishonest. Nothing ships with one open. | Never | Impeccable P0–P1 · OneRedOak Blocker/High · Nielsen 3–4 |
| **중** | Reflex | A default a model falls into, or a real usability cost with a workaround. | Yes, with a reason (§6) | P2 · Medium · Nielsen 2 |
| **하** | Finish | Craft detail. Reported, never blocks. | Yes | P3 · Nit · Nielsen 1 |

Rate a finding the reviewer found itself (not a lint gate) with this test:
- 상: the user cannot finish the task, a WCAG 2.2 AA criterion fails, the layout breaks at a common width (320–1920), content is invented or a control fakes success, or a console error breaks behaviour.
- 중: a user would hesitate, misread or need a second look; or the page shows an AI-default tell from §2.
- 하: only a designer would notice.
- Tie-break: "Would a user contact support about this?" Yes ⇒ at least 중.
- A form or flow that is not wired up yet but says so before the user fills it in is 중 (unfinished), not 상. Showing success with nothing behind it stays 상 (70).
- Product decision (`kind: product`): a 중/하 that design cannot fix on its own, such as a backend endpoint, real photos, legal text, a real contact or a business fact. It is listed apart, left out of the score, and blocks only `prod`. A 상 is never `product`: contain it in the design (hide, disable properly, disclose) even while the decision is open.

Lint gate mapping (Hallmark `sloplint --json` grades): `FAIL` → 상, `REFLEX` → 중, gates named `F*` → 하, `WARN` counts only after the reviewer confirms it. `WAIVED`, `ANSWERED`, `DISMISSED`, `NOTE`, `REJECTED` never count.

Overrides to Hallmark tiers (token hygiene is a refactor, not a ship blocker):
- 상 → 중: `7a` pure black/white literal, `24a` raw spacing literal, `48` colour/font literal outside tokens, `58` ~80 words per screen.
- Dropped (Hallmark build bookkeeping, meaningless on pages not built with Hallmark): `20` stamp, `32` ledger. Gate `8` is judged only on its template half, not against Hallmark's build log.

`scripts/score.py` enforces the overrides, drops and app skips on reviewer findings too, so a mis-tiered finding cannot change the score.

Surface `app` (dashboards, admin, forms) skips marketing-only gates: `6a 6b 8 42 44a 44b 58 59 77 78 79 85`.

## 2. Concrete tells

A generic "looks like AI" is not a finding. Name the tell. Each line is one finding type with its Hallmark gate id where one exists; `K*` ids are extra tells from oh-my-design's anti-slop guide and Korean copy practice.

A single soft pattern (a rounded card, a centred hero, one accent colour) is not slop on its own. Slop is a cluster of defaults with no product reason, so judge 중 tells against what the page is for. Keep quality defects (contrast, focus, overflow, broken states) as their own findings, never folded into "feels AI".

상
- Contrast under 4.5:1 body / 3:1 large text, icons, focus rings, field edges (40); button text near its fill colour, grey text on colour (41)
- No visible `:focus-visible`, or a ring that fades in (26a, 15); keyboard cannot reach or operate a control
- Animation without a `prefers-reduced-motion` fallback (27); content hidden until JS runs (62)
- Horizontal scroll or overlapping/covered text at any width 320–1920 (34, 73); button or nav label wrapping (49a)
- Invented metric, testimonial, logo wall or case-study count (46a); a form that shows success with no request behind it (70)
- Placeholder or cliché copy: Jane Doe, Acme, seamless, supercharge, empower, unlock, world-class, "Not X. It's Y." cadence, em dashes in UI copy, stock "Learn more" second action (19)
- Eyebrow: short inert label above a heading, `TRUSTED BY` over logos, category pill over a card (54); tracked or uppercase label at 15px or under (67)
- Template punctuation: `A · B · C` meta strings, arrow glued to link text `Learn more →`, decorative status dots (63)
- Purple→blue/pink or cyan-on-dark gradient (2a); card inside a card (4); emoji as an icon (30a); hand-drawn browser or OS window bar (47a)
- Hero sized in `vh` (6a); hero headline, one sentence and primary action not all visible at 1280×800 (44b)
- `transition: all`, or animating width/height/top/left (10a); input that shifts border or height between states, disabled by opacity alone (39a)
- Broken image (76); decorative svg/canvas with no `aria-hidden` or label (33)

중
- More than three families (37); monospace as costume on labels (64). Which typeface a page uses is not scored; see §2b
- Gradient text (2b); framework stock swatch such as Tailwind indigo-500/violet-600 (74); cream paper + high-contrast serif + terracotta accent (65); aurora/mesh blobs, glow orbs (29); accent over ~5% of a viewport (23)
- Card tells: three equal icon-over-heading tiles, icon in a rounded tile, thick coloured side stripe (3)
- The AI template: hero → three features → CTA → footer (8); every section separated the same way (9); AI nav and AI footer by reflex (42)
- Centred stack hero with everything on one axis (6b); dead band under hero content (79); thin sections with no mass (77); section heads under 40px at 1440 (78)
- Prose measure outside 45–75ch (25); running text under 12px or leading under 1.3 (75); crowded heads (71); cramped boxes (72)
- Same hover lift on every card, image zoom on hover (11); bounce/overshoot easing (12); celebratory toast for a visible effect (16)
- Empty gradient picture slots (81); drawn SVG illustration where a photo or the product belongs (80); counting devices (82); photo wall (83); a mocked product where the real one could be captured (84)
- Email sign-up as the stock last section (85); decoration text such as `BETA` pills, scroll cues, `01 / 4` counters (66); one fact repeated in four sections (69)
- Missing `:active`/`:disabled` (26b); control height outside 44–52px on marketing, 32–40px app without hit-area expansion (39b)
- Missing loading, empty or error state on a data view (OneRedOak Robustness)
- Display headline squeezed into a narrow column so it stacks into three or more short lines at 1280+ when the copy would fit in two, or broken by hand with `<br>` (K1)
- Korean text without `word-break: keep-all`, so a word splits across lines (K2); copy that reads as translated English: `~을 통해`, `~할 수 있습니다` chains, English subject order, `~의 ~의` stacking (K3)
- Sections wrapped in cards or panels when nothing in them is an object to pick, move or close (K4); every section built from the same title size, card count and alignment (9)
- Every block fades or slides in on scroll; staggered entrance on content the user came to read (K5)
- Result lands in the wrong place (K7). Where a submit or CTA result appears must match what it is:
  - a new document, results page, checkout or payment goes to its own page, a modal, or a new tab (external links marked and `rel="noopener"`);
  - a short confirmation or error stays next to the control, scrolled into view, focused or announced with `role=status`.
  Appending a whole result, receipt or next step under the form, or anywhere out of view, is K7. If the user cannot tell anything happened, it is 상 (status hidden).
- Sibling components out of alignment: cards in one row whose titles, bodies, meta rows or buttons sit at different heights because copy length differs; grid items off the shared baseline or edge (K6). Measure it: same row, same part, same `top` within 1px. Fix with subgrid, a fixed line count, or pinning the last row to the bottom

하
- Straight quotes, `...` for an ellipsis, orphan word on the last line, heading level skipped, `text-wrap: balance` on display heads, more than three weights, unthemed `::selection`/caret/scrollbar, one lone item on a grid's last row (Hallmark F1–F26)

## 2a. Mobile checklist (375×812, also 360 and 390 when width matters)

Measure on the page, do not eyeball. Ids are `M*`.

상
- Tap target under 24×24px with less than 24px clear space around it (WCAG 2.5.8): icon buttons, standalone links, bare checkboxes (M1). Measure the clickable area, not the glyph: a checkbox inside a `<label>` with its text is the whole label. A link inside a sentence is exempt
- A control only reachable by hover: menu, tooltip with needed info, action revealed on `:hover` (M2)
- A fixed or sticky element covers the focused input, the submit button or content the user must read, including with the on-screen keyboard open (M3)

중
- Primary controls under 44px tall or wide on touch (nav CTA, form buttons, tabs, toggles) (M4)
- Text inputs under 16px font, so iOS zooms the page on focus (M5)
- Wrong or missing keyboard and fill hints: phone without `type=tel` or `inputmode`, email without `type=email`, missing `autocomplete` on name, tel, email, address (M6)
- First screen at 375×812 does not show the headline and the primary action (M7)
- Height set in `vh` so browser bars cut or jump the block; use `svh`/`dvh` (M8)
- Desktop layout squeezed instead of re-ordered: columns too narrow to read, tables or comparisons that need side-by-side view stacked with no way to compare, sticky header taller than ~15% of the screen (M9)

하
- Fixed bottom bars or buttons ignore `env(safe-area-inset-bottom)` (M10)
- Phone numbers and emails shown as plain text instead of `tel:` / `mailto:` links (M11)

## 2b. Typeface: suggest, never score

Typeface choice is taste, so it never becomes a finding (Hallmark gate `1` is dropped). The project picks it in DESIGN.md; the reviewer only checks it is applied as written. Readability is still scored through the measurable tells above (size, leading, measure, contrast).

When the face looks off for the page (no DESIGN.md choice, a novelty or handwriting face on body text, a face missing Hangul glyphs so it falls back mid-line), put one line in `suggestions` naming popular options for Korean product pages:

- Pretendard: neutral UI and body, the most common default
- Gmarket Sans: bold, friendly headings for commerce and food
- SUIT, Spoqa Han Sans Neo: clean UI alternatives to Pretendard
- Noto Sans KR / Noto Serif KR: widest glyph coverage
- Latin and digits: Inter, paired with any of the above

## 3. Heuristics (UX score)

Score Nielsen's 10 heuristics 0–4 each. 4 means genuinely excellent, not "fine". Most real interfaces land between 20 and 32 out of 40.

| # | Heuristic | 0 | 2 | 4 |
|---|---|---|---|---|
| 1 | Visibility of system status | no feedback | partial | every action confirms |
| 2 | Match with the real world | jargon, odd order | mostly | the user's own words and order |
| 3 | User control and freedom | traps, no undo | some exits | undo, cancel, back everywhere |
| 4 | Consistency and standards | each screen differs | minor drift | one system throughout |
| 5 | Error prevention | easy to break | some guards | constraints and confirmations |
| 6 | Recognition over recall | must remember | partial | options visible in context |
| 7 | Flexibility and efficiency | one slow path | some shortcuts | accelerators for experts |
| 8 | Aesthetic and minimalist design | noise competes | some clutter | only what serves the task |
| 9 | Error recovery | cryptic | generic | plain cause and next step |
| 10 | Help and documentation | none needed but none present | partial | in context, searchable |

`null` (n/a) with a one-line reason is allowed when a heuristic cannot apply. On marketing pages 7 and 10 are usually n/a. The max shrinks to 4 × scored count; never pad.

## 4. Score (0–100)

```
UX     = 50 × (Σ heuristic scores) / (4 × scored heuristics)
Craft  = max(0, 50 − 10×상 − 4×중 − 1×하)
Total  = round(UX + Craft)
```

- Two independent runs (the default): a 상 counts only when both runs flag the same issue (same gate, or a shared `file:line`) as 상. A 상 from one run alone is scored as 중 and listed as 재확인 필요. Each run is scored on its own and the total is their mean; 중/하 counts are the mean rounded up.
- Lint findings count once per gate id, not per occurrence. A reviewer finding that names the same gate as a lint finding merges into it.
- Grade: A ≥ 90 · B ≥ 80 · C ≥ 70 · D ≥ 60 · F < 60.

## 5. Bars

| Bar | When | Pass when |
|---|---|---|
| `poc` | PoC, internal demo | 상 = 0 and Total ≥ 70 |
| `beta` | external beta, pilot customer | 상 = 0, 중 ≤ 3 and Total ≥ 80 |
| `prod` | public release | 상 = 0, 중 = 0 and Total ≥ 90 |

Any open 상 fails every bar, whatever the total.

## 6. Waivers

A project may keep `.design-review/waivers.md`, one line per waiver:

```
- 65: 브랜드 가이드(DESIGN.md §Color)가 크림 배경과 테라코타 포인트를 지정
```

Rules: gate id, colon, reason about this project (10+ characters). 상 gates cannot be waived; such lines are reported as rejected. Waived gates are listed in the report but excluded from the score. When a project's DESIGN.md or brand guide explicitly mandates something a 중/하 gate flags, the reviewer suggests a waiver line instead of counting the finding against the brand.

## 7. Credits

Severity tiers and gate ids: [Nutlope/hallmark](https://github.com/Nutlope/hallmark) (MIT). Heuristic scoring and P0–P3 ladder: [pbakaus/impeccable](https://github.com/pbakaus/impeccable) (Apache-2.0). Live review phases and triage labels: [OneRedOak/claude-code-workflows](https://github.com/OneRedOak/claude-code-workflows) (MIT). Cluster-over-pattern judgement and K* tells: [oh-my-design anti-slop](https://oh-my-design.kr/docs/ko/anti-slop) (MIT). Rules here are paraphrased, not copied.
