#!/usr/bin/env python3
"""Merge design-reviewer JSON (+ optional Hallmark sloplint --json) into a 0-100 score and a pass/fail against a bar.

Implements rubric.md §1 (severity mapping), §4 (score), §5 (bars), §6 (waivers).
Usage: score.py --review a.json [--review b.json] [--lint lint.json] [--bar poc|beta|prod] [--waivers waivers.md] [--out-dir .design-review]
Prints a Korean markdown report; writes <out-dir>/<timestamp>-<slug>.json when --out-dir is given.
Exit 0 = bar met, 1 = bar not met, 2 = bad input.
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

RANK = {"하": 1, "중": 2, "상": 3}
PENALTY = {"상": 10, "중": 4, "하": 1}
BARS = {
    "poc": {"min_total": 70, "max_mid": None},
    "beta": {"min_total": 80, "max_mid": 3},
    "prod": {"min_total": 90, "max_mid": 0},
}
# Hallmark Floor gates (gates.md § 1); everything else that is not F* is Reflex.
FLOOR = set("2a 7a 55a 4 6a 24a 34 44b 50 53 56 58 19 20 46a 47a 54 63 70 10a 15 17 18 "
            "26a 27 28a 39a 62 30a 33 76 73 40 41 48 49a 67 kept".split())
DEMOTE = {"7a", "24a", "48", "58"}  # 상 -> 중
DROP = {"20", "32", "1"}  # 1 = typeface choice: suggestion only (rubric §2b)
APP_SKIP = set("6a 6b 8 42 44a 44b 58 59 77 78 79 85".split())
COUNTED_GRADES = {"FAIL", "REFLEX", "WARN"}


def die(msg):
    print(f"score.py: {msg}", file=sys.stderr)
    sys.exit(2)


def norm_gate(g):
    return None if g in (None, "", "null") else str(g).strip().lower()


def gate_severity(gate, grade=None):
    if gate.startswith("f") and gate[1:].isdigit():
        return "하"
    if gate in DEMOTE:
        return "중"
    if grade == "FAIL" or (grade in (None, "WARN") and gate in FLOOR):
        return "상"
    return "중"


def parse_waivers(path):
    if not path or not Path(path).is_file():
        return {}
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*-\s*([A-Za-z0-9]+)\s*:\s*(.+?)\s*$", line)
        if m:
            out[m.group(1).lower()] = m.group(2)
    return out


def load_json(path, label):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        die(f"cannot read {label} {path}: {e}")


def validate(review, label):
    hs = review.get("heuristics") or []
    if sorted(h.get("id") for h in hs if isinstance(h.get("id"), int)) != list(range(1, 11)):
        die(f"{label}: heuristics must have ids 1-10, each once")
    for h in hs:
        if h.get("score") is not None and (not isinstance(h["score"], int) or not 0 <= h["score"] <= 4):
            die(f"{label}: heuristic {h['id']} score {h['score']!r} is not an integer 0-4")
    for i, f in enumerate(review.get("findings") or []):
        if f.get("severity") not in RANK:
            die(f"{label}: finding {i} has severity {f.get('severity')!r}; expected 상/중/하")


WHERE_KEY = re.compile(r"[\w./-]+\.(?:html|css|scss|js|jsx|ts|tsx|vue|svelte|astro):\d+")


def same_issue(f, g):  # same non-null gate, or a shared file:line
    ga, gb = norm_gate(f.get("gate")), norm_gate(g.get("gate"))
    return bool(ga and ga == gb) or bool(set(WHERE_KEY.findall(f.get("where", ""))) & set(WHERE_KEY.findall(g.get("where", ""))))


def merge_reviews(a, b):
    """Two independent runs -> (merged review for the report, each run with its lone 상 demoted).
    상 counts only when both runs call the same issue 상; a lone 상 is scored as 중 and listed for re-check.
    The report shows the union, one line per matched pair at the worse severity."""
    fa, fb = a.get("findings") or [], b.get("findings") or []
    pair = {}  # index in a -> index in b
    for i, f in enumerate(fa):
        j = next((j for j, g in enumerate(fb) if j not in pair.values() and same_issue(f, g)), None)
        if j is not None:
            pair[i] = j
    agreed_a = {i for i, j in pair.items() if fa[i]["severity"] == fb[j]["severity"] == "상"}
    agreed_b = {pair[i] for i in agreed_a}
    lone = [{k: f.get(k, "") for k in ("gate", "title", "where")}
            for f, ok in [(f, i in agreed_a) for i, f in enumerate(fa)] + [(g, j in agreed_b) for j, g in enumerate(fb)]
            if f["severity"] == "상" and not ok]

    def demote(fs, agreed):
        return [{**f, "severity": "중"} if f["severity"] == "상" and k not in agreed else f for k, f in enumerate(fs)]
    da, db = demote(fa, agreed_a), demote(fb, agreed_b)
    merged = []
    for i, f in enumerate(da):
        g = db[pair[i]] if i in pair else None
        both_product = f.get("kind") == "product" and (g is None or g.get("kind") == "product")
        merged.append({**f, "severity": max(f["severity"], g["severity"], key=RANK.get) if g else f["severity"],
                       "kind": "product" if both_product else None})
    merged += [g for j, g in enumerate(db) if j not in pair.values()]

    hb = {h["id"]: h.get("score") for h in b.get("heuristics") or []}
    heur = []
    for h in a.get("heuristics") or []:
        s = [x for x in (h.get("score"), hb.get(h["id"])) if x is not None]
        heur.append({**h, "score": sum(s) / len(s) if s else None})
    worst = max((a.get("verdict", ""), b.get("verdict", "")), key=["", "ship", "fix", "rebuild"].index)
    return {**a, "verdict": worst, "heuristics": heur, "findings": merged,
            "lint_review": (a.get("lint_review") or []) + (b.get("lint_review") or []),
            "suggestions": list(dict.fromkeys((a.get("suggestions") or []) + (b.get("suggestions") or []))),
            "limits": " / ".join(x for x in (a.get("limits"), b.get("limits")) if x),
            "consensus": {"runs": 2, "lone_high": lone}}, ({**a, "findings": da}, {**b, "findings": db})


def judge(total, counts, product, bar):
    rule = BARS[bar]
    reasons = []
    if counts["상"]:
        reasons.append(f"상 {counts['상']}건 (0건이어야 함)")
    if rule["max_mid"] is not None and counts["중"] > rule["max_mid"]:
        reasons.append(f"중 {counts['중']}건 (최대 {rule['max_mid']}건)")
    if total < rule["min_total"]:
        reasons.append(f"총점 {total} (최소 {rule['min_total']})")
    if bar == "prod" and product:
        reasons.append(f"제품 결정 {len(product)}건 미해결")
    grade = next(g for g, t in (("A", 90), ("B", 80), ("C", 70), ("D", 60), ("F", 0)) if total >= t)
    return grade, reasons


def score(review, lint, bar, waivers):
    surface = review.get("surface", "page")
    issues = {}  # key -> issue dict
    dismissed, unconfirmed = [], []

    reviews = review.get("lint_review") or []
    dismiss_at = [(norm_gate(r.get("gate")), (r.get("where") or "").strip()) for r in reviews if r.get("verdict") == "dismiss"]

    def is_dismissed(gate, where):  # empty where = whole gate; else file:line suffix match either way
        return any(g == gate and (not w or where.endswith(w) or w.endswith(where)) for g, w in dismiss_at)
    confirmed = {norm_gate(r.get("gate")) for r in reviews if r.get("verdict") == "confirm"}

    for f in (lint or {}).get("findings", []):
        gate, grade = norm_gate(f.get("gate")), f.get("grade")
        if not gate or grade not in COUNTED_GRADES or gate in DROP:
            continue
        if surface == "app" and gate in APP_SKIP:
            continue
        where = f"{f.get('file', '')}:{f.get('line', '')}".strip(":")
        if is_dismissed(gate, where):
            dismissed.append({"gate": gate, "where": where})
            continue
        if grade == "WARN" and gate not in confirmed:
            unconfirmed.append({"gate": gate, "where": where, "evidence": f.get("evidence", "")})
            continue
        sev = gate_severity(gate, grade)
        cur = issues.get(gate)
        if cur:
            cur["count"] += 1
            if RANK[sev] > RANK[cur["severity"]]:
                cur["severity"] = sev
        else:
            issues[gate] = {"severity": sev, "gate": gate, "title": f.get("evidence", ""), "where": where,
                            "fix": f.get("fix", ""), "source": "lint", "count": 1}

    product = []
    for i, f in enumerate(review.get("findings") or []):
        sev = f.get("severity")
        gate = norm_gate(f.get("gate"))
        if gate and (gate in DROP or (surface == "app" and gate in APP_SKIP)):
            continue
        if gate in DEMOTE and sev == "상":
            sev = "중"
        if f.get("kind") == "product" and sev != "상":  # needs a product decision, not a design fix (rubric §1)
            product.append({"severity": sev, "title": f.get("title", ""), "where": f.get("where", ""), "fix": f.get("fix", "")})
            continue
        key = gate or f"r{i}"
        cur = issues.get(key)
        if cur and cur["source"] == "lint":  # same gate as a lint finding: one issue, worst severity, reviewer wording
            cur.update({k: f[k] for k in ("title", "where", "fix") if f.get(k)})
            cur["severity"] = max(cur["severity"], sev, key=RANK.get)
            cur["source"] = "lint+review"
        elif cur:  # same gate reported again: counted once, other locations kept
            cur["count"] += 1
            cur["severity"] = max(cur["severity"], sev, key=RANK.get)
            cur["where"] += f"; {f.get('where', '')}"
        else:
            issues[key] = {"severity": sev, "gate": gate, "title": f.get("title", ""), "where": f.get("where", ""),
                           "fix": f.get("fix", ""), "impact": f.get("impact", ""), "source": "review", "count": 1}

    waived, rejected = [], []
    for gate, reason in waivers.items():
        hit = issues.get(gate)
        if not hit:
            continue
        if hit["severity"] == "상" or len(reason) < 10:
            rejected.append({"gate": gate, "reason": reason,
                             "why": "상은 면제 불가" if hit["severity"] == "상" else "사유 10자 미만"})
            continue
        waived.append({"gate": gate, "reason": reason, "severity": issues.pop(gate)["severity"]})

    counts = {s: sum(1 for x in issues.values() if x["severity"] == s) for s in RANK}

    hs = review.get("heuristics") or []
    scored = [h for h in hs if h.get("score") is not None]
    if not scored:
        die("review has no scored heuristics")
    ux = 50 * sum(h["score"] for h in scored) / (4 * len(scored))
    craft = max(0, 50 - sum(PENALTY[s] * n for s, n in counts.items()))
    total = round(ux + craft)
    grade, reasons = judge(total, counts, product, bar)

    order = sorted(issues.values(), key=lambda x: -RANK[x["severity"]])
    return {
        "target": review.get("target", ""), "surface": surface, "bar": bar, "pass": not reasons,
        "fail_reasons": reasons, "total": total, "grade": grade, "ux": round(ux, 1), "craft": craft,
        "counts": counts, "heuristics": hs, "heuristic_raw": f"{sum(h['score'] for h in scored):g}/{4 * len(scored)}",
        "product": product, "runs": review.get("consensus", {}).get("runs", 1),
        "lone_high": review.get("consensus", {}).get("lone_high", []),
        "issues": order, "waived": waived, "rejected_waivers": rejected, "dismissed": dismissed,
        "unconfirmed_warns": unconfirmed, "verdict": review.get("verdict", ""), "summary": review.get("summary", ""),
        "strengths": review.get("strengths", []), "suggested_waivers": review.get("suggested_waivers", []),
        "suggestions": review.get("suggestions", []),
        "limits": review.get("limits", ""), "lint": "ran" if lint else "none",
    }


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
    lines = [
        f"## 디자인 검수 — {r['target']}",
        "",
        f"**{r['total']}/100 ({r['grade']})** · 기준 `{r['bar']}` {mark}"
        + ("" if r["pass"] else f" — {', '.join(r['fail_reasons'])}"),
        f"UX {r['ux']}/50 (휴리스틱 {r['heuristic_raw']}) · 완성도 {r['craft']}/50 · 상 {c['상']} · 중 {c['중']} · 하 {c['하']}"
        + f" · lint {'실행' if r['lint'] == 'ran' else '건너뜀'} · 검수 {r['runs']}회"
        + (f" (각 {' / '.join(map(str, r['run_totals']))}점, 평균)" if r.get("run_totals") else ""),
    ]
    if len(history) > 1:
        lines.append("추이: " + " → ".join(map(str, history)))
    if r["summary"]:
        lines += ["", r["summary"]]
    if r["strengths"]:
        lines += ["", "### 유지할 것"] + [f"- {s}" for s in r["strengths"]]
    for sev in ("상", "중", "하"):
        group = [x for x in r["issues"] if x["severity"] == sev]
        if not group:
            continue
        lines += ["", f"### {sev} ({len(group)})"]
        for x in group:
            gate = f"`{x['gate']}` " if x.get("gate") else ""
            times = f" ×{x['count']}" if x.get("count", 1) > 1 else ""
            lines.append(f"- {gate}{x['title']}{times} — {x['where']}")
            if x.get("fix"):
                lines.append(f"  - 수정: {x['fix']}")
    if r["lone_high"]:
        lines += ["", "### 재확인 필요 (한 번만 상으로 지적 → 중으로 계산)"]
        lines += [f"- {x['title']} — {x['where']}" for x in r["lone_high"]]
    if r["product"]:
        lines += ["", "### 제품 결정 필요 (점수 제외, prod 전까지 해결)"]
        lines += [f"- ({x['severity']}) {x['title']} — {x['where']}" for x in r["product"]]
    if r["waived"]:
        lines += ["", "### 면제됨"] + [f"- `{w['gate']}` ({w['severity']}) {w['reason']}" for w in r["waived"]]
    if r["rejected_waivers"]:
        lines += ["", "### 거부된 면제"] + [f"- `{w['gate']}` {w['why']}: {w['reason']}" for w in r["rejected_waivers"]]
    if r["unconfirmed_warns"]:
        lines += ["", f"미확인 lint WARN {len(r['unconfirmed_warns'])}건은 점수에서 뺐어요."]
    if r["suggestions"]:
        lines += ["", "### 추천 (점수 미반영)"] + [f"- {s}" for s in r["suggestions"]]
    if r["suggested_waivers"]:
        lines += ["", "### 면제 제안 (waivers.md에 넣을지 판단)"] + r["suggested_waivers"]
    if r["limits"]:
        lines += ["", f"검수 한계: {r['limits']}"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--review", required=True, action="append", help="once, or twice for two independent runs")
    ap.add_argument("--lint")
    ap.add_argument("--bar", choices=BARS, default="poc")
    ap.add_argument("--waivers")
    ap.add_argument("--out-dir")
    a = ap.parse_args()

    if len(a.review) > 2:
        die("pass --review once or twice")
    runs = [load_json(p, "review") for p in a.review]
    for p, rv in zip(a.review, runs):
        validate(rv, p)
    lint = load_json(a.lint, "lint") if a.lint else None
    waivers = parse_waivers(a.waivers)
    if len(runs) == 1:
        r = score(runs[0], lint, a.bar, waivers)
    else:  # report the merged list, score the mean of the two runs
        merged, adjusted = merge_reviews(*runs)
        r = score(merged, lint, a.bar, waivers)
        each = [score(x, lint, a.bar, waivers) for x in adjusted]
        r["total"] = round(sum(x["total"] for x in each) / 2)
        r["ux"] = round(sum(x["ux"] for x in each) / 2, 1)
        r["craft"] = sum(x["craft"] for x in each) / 2
        r["counts"] = {s: -(-sum(x["counts"][s] for x in each) // 2) for s in RANK}  # mean, rounded up
        r["run_totals"] = [x["total"] for x in each]
        r["grade"], r["fail_reasons"] = judge(r["total"], r["counts"], r["product"], a.bar)
        r["pass"] = not r["fail_reasons"]
    history = [r["total"]]
    if a.out_dir:
        out = Path(a.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        history = trend(out, r["target"], r["total"])
        slug = re.sub(r"[^A-Za-z0-9]+", "-", r["target"]).strip("-")[:60] or "target"
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        (out / f"{stamp}-{slug}.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    print(render(r, history))
    sys.exit(0 if r["pass"] else 1)


if __name__ == "__main__":
    main()
