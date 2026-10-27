#!/usr/bin/env python3
"""Score a page 0-100 for SEO + GEO (AI-search citability) and report what is missing, tagged 상/중/하.

Implements rubric.md (checks, severity, bars). stdlib only.
Usage: seo_check.py --target <html file | site dir | http(s) URL> [--bar poc|beta|prod] [--json] [--out-dir .seo-geo-review]
Prints a Korean markdown report (or JSON with --json); writes <out-dir>/<timestamp>-<slug>.json when --out-dir is given.
Fetches only the target and its root files (/robots.txt /sitemap.xml /llms.txt). Never modifies the target.
Exit 0 = bar met, 1 = bar not met, 2 = bad input.
"""
import argparse
import datetime
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

UA = "seo-geo-review"
TIMEOUT = 10
MAX_BYTES = 4_000_000
RANK = {"하": 1, "중": 2, "상": 3}
BARS = {
    "poc": {"min_total": 60, "max_mid": None},
    "beta": {"min_total": 75, "max_mid": 3},
    "prod": {"min_total": 90, "max_mid": 0},
}
CATS = {"T": "기술", "O": "온페이지", "S": "구조화", "G": "GEO", "P": "성능"}
AI_BOTS = ["GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended", "OAI-SearchBot"]
GENERIC_LINKS = {"자세히 보기", "자세히", "더 보기", "더보기", "여기", "여기를 클릭", "클릭", "바로가기",
                 "learn more", "click here", "read more", "more", "here", "details"}
ENTITY_TYPES = {"organization", "localbusiness", "product", "offer", "service", "corporation", "ngo",
                "onlinestore", "store", "restaurant", "foodestablishment", "bakery", "cafeorcoffeeshop",
                "professionalservice", "onlinebusiness", "aggregateoffer", "softwareapplication"}
FAQ_HEAD = re.compile(r"faq|자주\s*묻는|자주\s*하는\s*질문", re.I)
ENTITY_CUE = re.compile(r"입니다|합니다|드립니다|운영|제공|판매|배송|전문|만드는|만들어|서비스|브랜드|매장|"
                        r"\b(?:is|are|we|offers?|provides?|sells?|delivers?|based in)\b", re.I)
FACT = re.compile(
    r"[₩$€¥]\s?\d[\d,.]*"
    r"|\d[\d,.]*\s?(?:원|만원|천원|%|퍼센트|kcal|칼로리|인분|개월|시간|분|초|주|일|개|명|년|월|곳|종|가지|호점|점|건|배|세"
    r"|(?:kg|mg|ml|km|cm|mm|g|l|m|usd|krw|won|minutes?|mins?|hours?|hrs?|days?|weeks?|months?|years?|stores?|items?|people)(?![a-z]))"
    r"|\b\d{1,2}:\d{2}\b", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
TEL = re.compile(r"(?:\+?82[-\s]?)?0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}|\b1[5-9]\d{2}-\d{4}\b")
OPERATOR = re.compile(r"사업자\s*(?:등록)?\s*번호|대표자|통신판매|주소|오시는\s*길|[가-힣]+(?:시|도)\s+[가-힣]+(?:구|군|시)\s"
                      r"|\b(?:street|avenue|address)\b", re.I)

SKIP_TAGS = {"noscript", "template", "svg"}
BLOCK_TAGS = {"p", "li", "dd", "dt", "summary", "details", "div", "section", "article", "main", "header", "footer",
              "nav", "aside", "td", "th", "blockquote", "address", "figcaption", "label",
              "h1", "h2", "h3", "h4", "h5", "h6"}
HEADINGS = {f"h{i}" for i in range(1, 7)}

# id, category, points, severity, failure statement, fix
CHECKS = [
    ("T1", 3, "중", "<html lang> 없음", "`<html lang=\"ko\">`처럼 문서 언어를 지정한다"),
    ("T2", 5, "상", "<title> 없음", "페이지를 설명하는 `<title>`을 넣는다"),
    ("T3", 2, "하", "<title> 길이가 10–60자를 벗어남", "핵심 키워드를 앞에 두고 10–60자로 맞춘다"),
    ("T4", 4, "중", "meta description 없음", "`<meta name=\"description\">`에 무엇을·누구에게·어디서를 한두 문장으로 쓴다"),
    ("T5", 1, "하", "meta description 길이가 50–160자를 벗어남", "50–160자로 맞춘다"),
    ("T6", 3, "중", "canonical 없음", "`<link rel=\"canonical\" href=\"https://…\">`를 넣는다"),
    ("T7", 5, "상", "noindex가 걸려 있음", "meta robots·X-Robots-Tag의 noindex를 제거한다(의도한 비공개가 아니라면)"),
    ("T8", 2, "중", "viewport meta 없음", "`<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">`을 넣는다"),
    ("O1", 5, "상", "h1이 정확히 1개가 아님", "페이지 주제를 담은 `<h1>`을 하나만 둔다"),
    ("O2", 2, "하", "제목 레벨을 건너뜀", "h2→h3→h4 순서로 단계를 건너뛰지 않는다"),
    ("O3", 4, "중", "의미 있는 이미지의 alt 커버리지 90% 미만", "장식이 아닌 이미지는 내용을 설명하는 alt를, 장식은 `alt=\"\"`를 쓴다"),
    ("O4", 4, "중", "og:title·og:description·og:image 중 누락", "세 가지 Open Graph 메타를 모두 넣는다"),
    ("O5", 1, "하", "twitter:card 없음", "`<meta name=\"twitter:card\" content=\"summary_large_image\">`를 넣는다"),
    ("O6", 2, "하", "일반적인 링크 문구('자세히 보기' 등) 사용", "링크 문구만 읽어도 목적지를 알 수 있게 바꾼다"),
    ("O7", 2, "하", "favicon 링크 없음", "`<link rel=\"icon\" href=\"…\">`를 넣는다"),
    ("S1", 5, "중", "JSON-LD가 없거나 파싱되지 않음", "`<script type=\"application/ld+json\">`을 유효한 JSON으로 넣는다"),
    ("S2", 5, "중", "Organization/LocalBusiness/Product/Offer/Service 스키마 없음", "사업 주체나 상품·서비스를 JSON-LD로 표시한다"),
    ("S3", 5, "중", "FAQ 섹션은 있으나 FAQPage JSON-LD가 없거나 본문과 불일치", "본문에 보이는 질문 그대로 FAQPage JSON-LD를 만든다"),
    ("G1", 5, "중", "AI 크롤러 허용 여부 문제(robots.txt)", "robots.txt에서 GPTBot·ClaudeBot·PerplexityBot·Google-Extended·OAI-SearchBot를 `Disallow: /`로 막지 않는다"),
    ("G2", 3, "하", "llms.txt 없음", "사이트 루트에 `llms.txt`로 사이트 요약과 핵심 링크를 둔다"),
    ("G3", 6, "상", "초기 HTML에 본문 텍스트가 500자 미만(JS 렌더링 의심)", "SSR/SSG로 본문을 초기 HTML에 담는다. AI 크롤러 대부분은 JS를 실행하지 않는다"),
    ("G4", 4, "중", "h1 다음 첫 문단이 무엇·누구·어디를 200자 안에 말하지 않음", "h1 바로 아래에 '○○은 △△에서 □□를 제공하는 …입니다' 형태의 한두 문장을 둔다"),
    ("G5", 3, "중", "FAQ 답변이 결론 먼저·독립적인 40–400자가 아님", "답변 첫 문장에 결론을 쓰고, 질문 없이 읽어도 이해되게 40–400자로 쓴다"),
    ("G6", 2, "하", "구체적 사실(숫자+단위·가격·시간)이 5개 미만", "가격·수량·시간·기간 같은 인용 가능한 수치를 본문에 쓴다"),
    ("G7", 2, "중", "연락처·운영자 정보 없음", "이메일·전화·주소·사업자 정보를 본문(푸터 포함)에 텍스트로 쓴다"),
    ("P1", 4, "중", "<img>에 width·height 없음", "모든 `<img>`에 width·height를 넣어 레이아웃 이동을 막는다"),
    ("P2", 3, "하", "첫 두 이미지 이후에 loading=lazy 없음", "화면 아래 이미지에 `loading=\"lazy\"`를 단다"),
    ("P3", 4, "중", "head에 렌더 차단 <script>(defer/async/module 없음)", "`defer` 또는 `async`, `type=\"module\"`을 단다"),
    ("P4", 2, "하", "HTML이 200KB 초과", "인라인 SVG·스타일·데이터를 외부 파일로 분리한다"),
    ("P5", 2, "하", "Google Fonts에 preconnect 또는 display=swap 없음", "`preconnect`(googleapis·gstatic)와 `&display=swap`을 둘 다 쓴다"),
]
META = {c[0]: {"cat": CATS[c[0][0]], "points": c[1], "severity": c[2], "fail": c[3], "fix": c[4]} for c in CHECKS}


def die(msg):
    print(f"seo_check.py: {msg}", file=sys.stderr)
    sys.exit(2)


# ---------- parsing ----------

class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lang = None
        self.title = None
        self.metas, self.links, self.scripts, self.jsonld, self.styles = [], [], [], [], []
        self.imgs, self.anchors, self.records, self.texts = [], [], [], []
        self.stack, self.root = [], {"tag": "text", "parts": []}
        self.head = False
        self.skip = 0
        self._title = self._script = self._style = self._a = None

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag in SKIP_TAGS:
            self.skip += 1
            return
        if self.skip:
            return
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "head":
            self.head = True
        elif tag == "body":
            self.head = False
        elif tag == "title" and self.title is None:
            self._title = []
        elif tag == "meta":
            self.metas.append(a)
        elif tag == "link":
            self.links.append(a)
        elif tag == "script":
            typ = a.get("type", "").lower()
            self._script = (typ, [])
            self.scripts.append({"src": "src" in a, "defer": "defer" in a, "async": "async" in a,
                                 "type": typ, "head": self.head})
        elif tag == "style":
            self._style = []
        elif tag == "img":
            a["_pos"] = len(self.imgs)
            self.imgs.append(a)
            if self._a is not None and a.get("alt"):
                self._a["text"].append(a["alt"])
        elif tag == "a":
            self._a = {"href": a.get("href", ""), "label": a.get("aria-label", ""), "text": []}
        elif tag in BLOCK_TAGS:
            rec = {"tag": tag, "parts": []}
            self.records.append(rec)
            self.stack.append(rec)

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            if self.skip:
                self.skip -= 1
            return
        if self.skip:
            return
        if tag == "head":
            self.head = False
        elif tag == "title" and self._title is not None:
            self.title = " ".join("".join(self._title).split())
            self._title = None
        elif tag == "script" and self._script is not None:
            typ, buf = self._script
            if "ld+json" in typ:
                self.jsonld.append("".join(buf))
            self._script = None
        elif tag == "style" and self._style is not None:
            self.styles.append("".join(self._style))
            self._style = None
        elif tag == "a" and self._a is not None:
            self.anchors.append(self._a)
            self._a = None
        elif tag in BLOCK_TAGS:
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i]["tag"] == tag:
                    del self.stack[i:]
                    break

    def handle_data(self, data):
        if self._script is not None:
            self._script[1].append(data)
        elif self._style is not None:
            self._style.append(data)
        elif self._title is not None:
            self._title.append(data)
        elif self.skip or self.head:
            return
        else:
            (self.stack[-1] if self.stack else self.root)["parts"].append(data)
            self.texts.append(data)
            if self._a is not None:
                self._a["text"].append(data)

    def meta(self, key):
        for m in self.metas:
            if m.get("name", "").lower() == key or m.get("property", "").lower() == key:
                return m.get("content", "")
        return None


def clean(parts):
    return " ".join(" ".join(parts).split())


def rec_text(rec):
    return clean(rec["parts"])


def jsonld_nodes(blobs):
    """-> (parsed ok count, total, flat list of dict nodes incl. nested)."""
    ok, nodes = 0, []

    def walk(x):
        if isinstance(x, dict):
            nodes.append(x)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    for b in blobs:
        try:
            walk(json.loads(b.strip()))
            ok += 1
        except (json.JSONDecodeError, ValueError):
            pass
    return ok, len(blobs), nodes


def types_of(node):
    t = node.get("@type")
    return [str(x).lower() for x in (t if isinstance(t, list) else [t])] if t else []


def squash(s):
    return re.sub(r"[\W_]+", "", s.lower())


def parse_robots(txt):
    groups, cur, last_ua = [], None, False
    for line in txt.splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        k, v = (x.strip() for x in line.split(":", 1))
        k = k.lower()
        if k == "user-agent":
            if cur is None or not last_ua:
                cur = {"agents": [], "rules": []}
                groups.append(cur)
            cur["agents"].append(v.lower())
            last_ua = True
        else:
            last_ua = False
            if k in ("allow", "disallow") and cur is not None:
                cur["rules"].append((k, v))
    return groups


def blocked_bots(robots_txt):
    groups = parse_robots(robots_txt)
    out = []
    for bot in AI_BOTS:
        sel = [g for g in groups if bot.lower() in g["agents"]] or [g for g in groups if "*" in g["agents"]]
        rules = [r for g in sel for r in g["rules"]]
        if ("disallow", "/") in rules and ("allow", "/") not in rules:
            out.append(bot)
    return out


# ---------- fetching ----------

class SameHost(urllib.request.HTTPRedirectHandler):
    def __init__(self, host):
        self.host = host

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        p = urllib.parse.urlparse(newurl)
        if p.scheme not in ("http", "https") or p.netloc != self.host:
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, same_host=None):
    """-> (status, body bytes, headers) ; raises URLError/HTTPError/OSError."""
    handlers = [SameHost(same_host)] if same_host else []
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with opener.open(req, timeout=TIMEOUT) as r:
        return r.status, r.read(MAX_BYTES), r.headers, r.geturl()


def decode(body, headers=None):
    cs = headers.get_content_charset() if headers else None
    try:
        return body.decode(cs or "utf-8", errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def root_text(origin, name):
    try:
        status, body, _, _ = fetch(f"{origin}/{name}", same_host=urllib.parse.urlparse(origin).netloc)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return decode(body) if status == 200 and body.strip() else None


def load_target(target):
    """-> dict(label, raw bytes, html str, robots, sitemap, llms, xrobots)."""
    if re.match(r"^[a-z][a-z0-9+.-]*://", target, re.I):
        p = urllib.parse.urlparse(target)
        if p.scheme not in ("http", "https") or not p.netloc:
            die(f"unsupported URL {target!r}; only http(s) is allowed")
        try:
            status, body, headers, final = fetch(target)
        except urllib.error.HTTPError as e:
            die(f"HTTP {e.code} for {target}")
        except (urllib.error.URLError, OSError, ValueError) as e:
            die(f"cannot fetch {target}: {e}")
        ctype = headers.get("Content-Type", "")
        if "html" not in ctype.lower():
            die(f"{target} is not HTML (Content-Type: {ctype or 'none'})")
        fp = urllib.parse.urlparse(final)
        origin = f"{fp.scheme}://{fp.netloc}"
        return {"label": target, "raw": body, "html": decode(body, headers), "xrobots": headers.get("X-Robots-Tag", ""),
                "robots": root_text(origin, "robots.txt"), "sitemap": root_text(origin, "sitemap.xml"),
                "llms": root_text(origin, "llms.txt")}
    path = Path(target).expanduser()
    if path.is_dir():
        path = path / "index.html"
    if not path.is_file():
        die(f"no such HTML file: {path}")
    if path.suffix.lower() not in (".html", ".htm"):
        die(f"not an .html file: {path}")
    try:
        raw = path.read_bytes()
    except OSError as e:
        die(f"cannot read {path}: {e}")
    root = path.resolve().parent

    def local(name):
        f = root / name
        try:
            t = f.read_text(encoding="utf-8", errors="replace") if f.is_file() else None
        except OSError:
            t = None
        return t if t and t.strip() else None

    return {"label": str(path.resolve()), "raw": raw, "html": raw.decode("utf-8", errors="replace"), "xrobots": "",
            "robots": local("robots.txt"), "sitemap": local("sitemap.xml"), "llms": local("llms.txt")}


# ---------- checks ----------

def run_checks(t):
    pg = Page()
    pg.feed(t["html"])
    pg.close()
    R = {}  # id -> (earned, found)
    visible = clean(pg.texts)
    recs = pg.records
    headings = [(int(r["tag"][1]), rec_text(r)) for r in recs if r["tag"] in HEADINGS]

    # Technical
    R["T1"] = (3, pg.lang) if (pg.lang or "").strip() else (0, "")
    title = pg.title or ""
    R["T2"] = (5, f"“{title}”") if title else (0, "")
    R["T3"] = (2, f"{len(title)}자") if 10 <= len(title) <= 60 else (0, f"{len(title)}자" if title else "title 없음")
    desc = (pg.meta("description") or "").strip()
    R["T4"] = (4, "") if desc else (0, "")
    R["T5"] = (1, f"{len(desc)}자") if 50 <= len(desc) <= 160 else (0, f"{len(desc)}자" if desc else "description 없음")
    canon = any("canonical" in l.get("rel", "").lower().split() and l.get("href") for l in pg.links)
    R["T6"] = (3, "") if canon else (0, "")
    noindex = [m.get("content", "") for m in pg.metas
               if m.get("name", "").lower() in ("robots", "googlebot") and "noindex" in m.get("content", "").lower()]
    if "noindex" in t["xrobots"].lower():
        noindex.append(f"X-Robots-Tag: {t['xrobots']}")
    R["T7"] = (0, "; ".join(noindex)) if noindex else (5, "")
    vp = pg.meta("viewport")
    R["T8"] = (2, "") if vp and "width=device-width" in vp.replace(" ", "").lower() else (0, "")

    # On-page
    h1n = sum(1 for lv, _ in headings if lv == 1)
    R["O1"] = (5, "h1 1개") if h1n == 1 else (0, f"h1 {h1n}개")
    skips = []
    prev = None
    for lv, tx in headings:
        if prev is not None and lv > prev + 1:
            skips.append(f"h{prev}→h{lv}")
        prev = lv
    R["O2"] = (0, ", ".join(skips[:3])) if skips else (2, "")
    meaningful = [i for i in pg.imgs if i.get("alt") != "" and i.get("role", "").lower() not in ("presentation", "none")
                  and i.get("aria-hidden", "").lower() != "true"]
    with_alt = [i for i in meaningful if i.get("alt", "").strip()]
    if not meaningful:
        R["O3"] = (4, "의미 있는 이미지 없음")
    else:
        cov = len(with_alt) / len(meaningful)
        R["O3"] = (4 if cov >= 0.9 else 2 if cov >= 0.7 else 0, f"{len(with_alt)}/{len(meaningful)}개 ({round(cov * 100)}%)")
    og = [k for k in ("og:title", "og:description", "og:image") if pg.meta(k)]
    miss = [k for k in ("og:title", "og:description", "og:image") if k not in og]
    R["O4"] = (4 if not miss else 2 if len(og) == 2 else 0, "누락: " + ", ".join(miss) if miss else "")
    R["O5"] = (1, "") if pg.meta("twitter:card") else (0, "")
    bad = []
    for a in pg.anchors:
        txt = (clean(a["text"]) or a["label"]).strip().lower().strip("→»›>…·.!> ")
        if txt in GENERIC_LINKS:
            bad.append(f"“{txt}”")
    R["O6"] = (0, ", ".join(dict.fromkeys(bad[:4])) + (f" 등 {len(bad)}곳" if len(bad) > 1 else "")) if bad else (2, "")
    R["O7"] = (2, "") if any("icon" in l.get("rel", "").lower() for l in pg.links) else (0, "")

    # Structured data
    ok, total, nodes = jsonld_nodes(pg.jsonld)
    if total and ok == total:
        R["S1"] = (5, f"블록 {total}개")
    elif ok:
        R["S1"] = (3, f"{total}개 중 {ok}개만 파싱됨")
    else:
        R["S1"] = (0, f"블록 {total}개, 파싱 실패" if total else "블록 없음")
    found_types = sorted({tp for n in nodes for tp in types_of(n) if tp in ENTITY_TYPES})
    R["S2"] = (5, ", ".join(found_types)) if found_types else (0, "")
    faq_heads = [i for i, r in enumerate(recs) if r["tag"] in HEADINGS and FAQ_HEAD.search(rec_text(r))]
    faq_nodes = [n for n in nodes if "faqpage" in types_of(n)]
    questions, ld_answers = [], []
    for n in faq_nodes:
        me = n.get("mainEntity") or []
        for q in (me if isinstance(me, list) else [me]):
            if isinstance(q, dict) and q.get("name"):
                questions.append(str(q["name"]))
                ans = q.get("acceptedAnswer")
                if isinstance(ans, dict) and ans.get("text"):
                    ld_answers.append(re.sub(r"<[^>]+>", " ", str(ans["text"])))
    if not faq_heads:
        R["S3"] = (5, "FAQ 섹션 없음(해당 없음)")
    elif not questions:
        R["S3"] = (0, "FAQPage JSON-LD 없음")
    else:
        sv = squash(visible)
        hit = sum(1 for q in questions if squash(q) in sv)
        R["S3"] = (5 if hit == len(questions) else 3 if hit * 2 >= len(questions) else 0,
                   f"질문 {len(questions)}개 중 {hit}개가 본문에 보임")

    # GEO
    if t["robots"] is None:
        R["G1"] = (3, "robots.txt 없음(부분 점수)")
    else:
        blocked = blocked_bots(t["robots"])
        R["G1"] = (5 if not blocked else 2 if len(blocked) < len(AI_BOTS) else 0,
                   "차단: " + ", ".join(blocked) if blocked else "5개 AI 봇 모두 허용")
    R["G2"] = (3, "") if t["llms"] else (0, "")
    n = len(visible)
    R["G3"] = (6, f"{n}자") if n >= 500 else (0, f"{n}자")
    first = None
    seen_h1 = False
    for r in recs:
        if r["tag"] == "h1":
            seen_h1 = True
        elif seen_h1 and r["tag"] == "p" and rec_text(r):
            first = rec_text(r)
            break
    if first is None and seen_h1:
        for r in recs[[i for i, r in enumerate(recs) if r["tag"] == "h1"][0]:]:
            if r["tag"] not in HEADINGS | {"li", "nav", "summary", "dt"} and len(rec_text(r)) >= 20:
                first = rec_text(r)
                break
    if first is None:
        R["G4"] = (0, "h1 다음 문단 없음")
    else:
        L = len(first)
        cue = bool(ENTITY_CUE.search(first))
        snippet = first if L <= 60 else first[:57] + "…"
        R["G4"] = (4 if 20 <= L <= 200 and cue else 2 if 200 < L <= 320 and cue else 0, f"{L}자 “{snippet}”")
    answers, div_answers = [], []
    for i in faq_heads:
        lvl = int(recs[i]["tag"][1])
        for r in recs[i + 1:]:
            if r["tag"] in HEADINGS and int(r["tag"][1]) <= lvl:
                break
            tx = rec_text(r)
            if len(tx) < 8 or tx.endswith(("?", "？")):
                continue
            if r["tag"] in ("p", "dd", "details", "blockquote", "td"):
                answers.append(tx)
            elif r["tag"] == "div":
                div_answers.append(tx)
    answers = answers or div_answers
    answers = answers or [a.strip() for a in ld_answers]
    if not faq_heads:
        R["G5"] = (3, "FAQ 섹션 없음(해당 없음)")
    elif not answers:
        R["G5"] = (0, "FAQ 답변을 찾지 못함")
    else:
        good = sum(1 for a in answers if 40 <= len(a) <= 400)
        R["G5"] = (3 if good == len(answers) else 1 if good * 2 >= len(answers) else 0, f"답변 {len(answers)}개 중 {good}개가 40–400자")
    facts = {re.sub(r"\s+", "", m.group(0).lower()) for m in FACT.finditer(visible)}
    R["G6"] = (2 if len(facts) >= 5 else 1 if len(facts) >= 3 else 0, f"{len(facts)}개")
    hrefs = " ".join(a["href"] for a in pg.anchors)
    contact = []
    if EMAIL.search(visible) or "mailto:" in hrefs:
        contact.append("이메일")
    if TEL.search(visible) or "tel:" in hrefs:
        contact.append("전화")
    if OPERATOR.search(visible):
        contact.append("주소·사업자")
    R["G7"] = (2, ", ".join(contact)) if contact else (0, "")

    # Performance
    imgs = pg.imgs
    if not imgs:
        R["P1"] = (4, "이미지 없음")
        R["P2"] = (3, "이미지 없음")
    else:
        sized = sum(1 for i in imgs if i.get("width") and i.get("height"))
        R["P1"] = (4 if sized == len(imgs) else 2 if sized * 2 >= len(imgs) else 0, f"{sized}/{len(imgs)}개")
        below = imgs[2:]
        if not below:
            R["P2"] = (3, "이미지 2개 이하")
        else:
            lazy = sum(1 for i in below if i.get("loading", "").lower() == "lazy")
            R["P2"] = (3 if lazy == len(below) else 1 if lazy * 2 >= len(below) else 0, f"{lazy}/{len(below)}개")
    js_types = {"", "text/javascript", "application/javascript", "text/ecmascript"}
    blocking = [s for s in pg.scripts if s["head"] and s["src"] and not s["defer"] and not s["async"] and s["type"] in js_types]
    R["P3"] = (4, "") if not blocking else (2, "1개") if len(blocking) == 1 else (0, f"{len(blocking)}개")
    size = len(t["raw"])
    R["P4"] = (2 if size <= 200 * 1024 else 0, f"{size / 1024:.0f}KB")
    gf_text = " ".join([l.get("href", "") for l in pg.links] + pg.styles)
    if "fonts.googleapis.com" not in gf_text:
        R["P5"] = (2, "Google Fonts 미사용(해당 없음)")
    else:
        pre = any("preconnect" in l.get("rel", "").lower() and ("fonts.googleapis.com" in l.get("href", "") or "fonts.gstatic.com" in l.get("href", ""))
                  for l in pg.links)
        swap = "display=swap" in gf_text
        R["P5"] = (1 * pre + 1 * swap, f"preconnect {'O' if pre else 'X'} · display=swap {'O' if swap else 'X'}")

    extras = {"robots": t["robots"] is not None, "sitemap": t["sitemap"] is not None, "llms": t["llms"] is not None}
    return R, extras


def score(label, R, extras, bar):
    checks = []
    for cid, *_ in CHECKS:
        m = META[cid]
        earned, found = R[cid]
        status = "pass" if earned == m["points"] else "fail" if earned == 0 else "partial"
        checks.append({"id": cid, "category": m["cat"], "points": m["points"], "earned": earned, "severity": m["severity"],
                       "status": status, "title": m["fail"], "found": found, "fix": m["fix"]})
    total = sum(c["earned"] for c in checks)
    grade = next(g for g, th in (("A", 90), ("B", 80), ("C", 70), ("D", 60), ("F", 0)) if total >= th)
    subtotals = {}
    for c in checks:
        s = subtotals.setdefault(c["category"], [0, 0])
        s[0] += c["earned"]
        s[1] += c["points"]
    counts = {s: sum(1 for c in checks if c["severity"] == s and c["status"] != "pass") for s in RANK}
    rule = BARS[bar]
    reasons = []
    if counts["상"]:
        reasons.append(f"상 {counts['상']}건 (0건이어야 함)")
    if rule["max_mid"] is not None and counts["중"] > rule["max_mid"]:
        reasons.append(f"중 {counts['중']}건 (최대 {rule['max_mid']}건)")
    if total < rule["min_total"]:
        reasons.append(f"총점 {total} (최소 {rule['min_total']})")
    return {"target": label, "bar": bar, "pass": not reasons, "fail_reasons": reasons, "total": total, "grade": grade,
            "subtotals": {k: {"earned": v[0], "points": v[1]} for k, v in subtotals.items()}, "counts": counts,
            "checks": checks, "files": extras}


def trend(out_dir, target, total):
    prev = []
    for p in sorted(Path(out_dir).glob("*.json"))[-50:]:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if d.get("target") == target and "total" in d:
            prev.append(d["total"])
    return prev[-4:] + [total]


def render(r, history):
    c = r["counts"]
    mark = "✅ 통과" if r["pass"] else "❌ 미달"
    sub = " · ".join(f"{k} {v['earned']}/{v['points']}" for k, v in r["subtotals"].items())
    lines = [
        f"## SEO·GEO 검수 — {r['target']}",
        "",
        f"**{r['total']}/100 ({r['grade']})** · 기준 `{r['bar']}` {mark}"
        + ("" if r["pass"] else f" — {', '.join(r['fail_reasons'])}"),
        f"{sub} · 상 {c['상']} · 중 {c['중']} · 하 {c['하']}",
    ]
    if len(history) > 1:
        lines.append("추이: " + " → ".join(map(str, history)))
    for sev in ("상", "중", "하"):
        group = [x for x in r["checks"] if x["severity"] == sev and x["status"] != "pass"]
        if not group:
            continue
        lines += ["", f"### {sev} ({len(group)})"]
        for x in group:
            part = f" (부분 {x['earned']}/{x['points']}점)" if x["status"] == "partial" else f" (−{x['points']}점)"
            found = f" — {x['found']}" if x["found"] else ""
            lines += [f"- `{x['id']}` {x['title']}{part}{found}", f"  - 수정: {x['fix']}"]
    passed = [x["id"] for x in r["checks"] if x["status"] == "pass"]
    lines += ["", f"### 통과 {len(passed)}/{len(r['checks'])}", "- " + " ".join(f"`{i}`" for i in passed)]
    f = r["files"]
    lines += ["", "참고(점수 미반영): " + " · ".join(f"{n} {'있음' if f[k] else '없음'}"
                                                 for n, k in (("robots.txt", "robots"), ("sitemap.xml", "sitemap"), ("llms.txt", "llms")))]
    lines.append("검수 한계: 원본 HTML만 분석(렌더링 후 DOM·외부 CSS/JS 미분석). 문장 품질은 규칙으로만 근사한다.")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--bar", choices=BARS, default="poc")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out-dir")
    a = ap.parse_args()

    t = load_target(a.target)
    R, extras = run_checks(t)
    r = score(t["label"], R, extras, a.bar)
    history = [r["total"]]
    if a.out_dir:
        out = Path(a.out_dir)
        try:
            out.mkdir(parents=True, exist_ok=True)
            history = trend(out, r["target"], r["total"])
            slug = re.sub(r"[^A-Za-z0-9]+", "-", r["target"]).strip("-")[-60:] or "target"
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            (out / f"{stamp}-{slug}.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as e:
            die(f"cannot write to --out-dir {out}: {e}")
    print(json.dumps({**r, "history": history}, ensure_ascii=False, indent=2) if a.json else render(r, history))
    sys.exit(0 if r["pass"] else 1)


if __name__ == "__main__":
    main()
