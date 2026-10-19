#!/usr/bin/env python3
"""jev.py — Jev (TypeSafe "System One" decision model) helper for Claude Code skills.

Standard library only.

Subcommands
  call   Generic primitive. Reads {"state":..., "questions":{...}} JSON from stdin,
         adds model "jev-latest", POSTs it, prints the response JSON.
  scope  Rank repo files by relevance to a coding task using one noul question per file.

Config
  API key:  env TYPESAFE_API_KEY, else file ~/.config/jev/api_key.
  Base URL: env JEV_BASE_URL overrides https://api.typesafe.ai (for gateways / testing).
"""

import argparse
import concurrent.futures
import json
import os
import random
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request


def _claudi_lang():
    # English: resolve output language — env CLAUDI_LANG, then
    # <CLAUDE_CONFIG_DIR or ~/.claude>/claudi/config.json {"lang"} (both optional;
    # only present with the claudi kit), else "en".
    # 한국어: 출력 언어 결정 — 환경변수 CLAUDI_LANG → claudi/config.json의 "lang" → 기본 "en".
    import os, json
    lang = os.environ.get("CLAUDI_LANG")
    if lang:
        return lang.strip().lower()
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    try:
        with open(os.path.join(base, "claudi", "config.json"), encoding="utf-8") as f:
            v = json.load(f).get("lang")
            if v:
                return str(v).strip().lower()
    except (OSError, ValueError):
        pass
    return "en"


def t(en, ko):
    # English: pick the string for the active output language (default English).
    # 한국어: 활성 출력 언어에 맞는 문자열 선택 (기본 영어).
    return ko if _claudi_lang() == "ko" else en


DEFAULT_BASE_URL = "https://api.typesafe.ai"
MODEL = "jev-latest"
KEY_PATH = os.path.expanduser("~/.config/jev/api_key")

MAX_FILE_BYTES = 200 * 1024
PREFILTER_LIMIT = 400
BATCH_SIZE = 40
MAX_WORKERS = 4
DESC_SYMBOL_CHARS = 500

# python.org macOS builds ship without a CA bundle; fall back to the system one.
_SYSTEM_CA = "/etc/ssl/cert.pem"
SSL_CTX = ssl.create_default_context(
    cafile=None if os.environ.get("SSL_CERT_FILE") or not os.path.exists(_SYSTEM_CA) else _SYSTEM_CA
)


class JevError(Exception):
    pass


# --------------------------------------------------------------------------- #
# Config / HTTP
# --------------------------------------------------------------------------- #

def base_url():
    return os.environ.get("JEV_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def get_api_key():
    key = os.environ.get("TYPESAFE_API_KEY")
    if key and key.strip():
        return key.strip()
    try:
        with open(KEY_PATH, "r", encoding="utf-8") as fh:
            key = fh.read().strip()
        if key:
            return key
    except OSError:
        pass
    sys.stderr.write(t(
        "No TypeSafe API key found.\n"
        "Issue a key in the TypeSafe console and save it to:\n"
        f"  {KEY_PATH}\n"
        "Then restrict its permissions:  chmod 600 " + KEY_PATH + "\n"
        "Or set an environment variable:  export TYPESAFE_API_KEY=<KEY>\n",
        "TypeSafe API 키가 없습니다.\n"
        "TypeSafe 콘솔에서 키를 발급받아 아래 경로에 저장하세요:\n"
        f"  {KEY_PATH}\n"
        "저장 후 권한을 좁히세요:  chmod 600 " + KEY_PATH + "\n"
        "또는 환경변수로 지정:  export TYPESAFE_API_KEY=<KEY>\n",
    ))
    sys.exit(1)


def api_request(payload, api_key, timeout=120, max_retries=5):
    """POST to /v1/systemone with exponential backoff on 429/529."""
    url = base_url() + "/v1/systemone"
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }
    attempt = 0
    while True:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            if exc.code in (429, 529) and attempt < max_retries:
                time.sleep(min(2 ** attempt, 30) + random.random())
                attempt += 1
                continue
            if exc.code == 401:
                raise JevError(t(
                    "401: API key rejected. Check your key.",
                    "401: API 키가 거부되었습니다. 키를 확인하세요.",
                ))
            raise JevError(f"HTTP {exc.code}: {body[:500]}")
        except urllib.error.URLError as exc:
            if attempt < max_retries:
                time.sleep(min(2 ** attempt, 30) + random.random())
                attempt += 1
                continue
            raise JevError(t(f"Request failed: {exc}", f"요청 실패: {exc}"))


# --------------------------------------------------------------------------- #
# call
# --------------------------------------------------------------------------- #

def cmd_call(_args):
    api_key = get_api_key()
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        sys.stderr.write(t(
            f"Failed to parse stdin JSON: {exc}\n",
            f"stdin JSON 파싱 실패: {exc}\n",
        ))
        sys.exit(1)
    if not isinstance(payload, dict) or "questions" not in payload:
        sys.stderr.write(t(
            'stdin must be of the form {"state":..., "questions":{...}}.\n',
            'stdin 은 {"state":..., "questions":{...}} 형태여야 합니다.\n',
        ))
        sys.exit(1)
    payload.setdefault("model", MODEL)
    try:
        resp = api_request(payload, api_key)
    except JevError as exc:
        sys.stderr.write(str(exc) + "\n")
        sys.exit(1)
    json.dump(resp, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


# --------------------------------------------------------------------------- #
# scope: candidate selection
# --------------------------------------------------------------------------- #

LOCKFILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "npm-shrinkwrap.json",
    "poetry.lock", "pipfile.lock", "gemfile.lock", "composer.lock",
    "cargo.lock", "go.sum", "flake.lock", "bun.lockb", "podfile.lock",
}

BINARY_EXTS = {
    # images / assets
    "png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "bmp", "tif", "tiff",
    "heic", "avif", "psd", "ai", "sketch", "fig",
    # fonts
    "woff", "woff2", "ttf", "otf", "eot",
    # media
    "mp3", "mp4", "mov", "avi", "webm", "mkv", "wav", "flac", "ogg", "m4a",
    # archives / binaries
    "zip", "tar", "gz", "tgz", "bz2", "xz", "rar", "7z",
    "so", "dylib", "dll", "exe", "bin", "o", "a", "wasm", "class", "jar",
    "pyc", "pyd", "node",
    # docs / data blobs
    "pdf", "xlsx", "xls", "docx", "doc", "pptx", "ppt",
    "parquet", "db", "sqlite", "sqlite3", "pack", "idx",
}

DROP_DIR_SEGMENTS = {
    "node_modules", "vendor", "dist", "build", "out", "target",
    ".next", ".nuxt", ".svelte-kit", ".turbo", "coverage",
    "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache",
    "generated", "gen", "__generated__", "snapshots",
    "__snapshots__", ".git", ".idea", ".gradle",
}


def git_ls_files(repo):
    proc = subprocess.run(
        ["git", "-C", repo, "ls-files"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise JevError(t(
            f"git ls-files failed (is {repo} a git repository?): {proc.stderr.strip()}",
            f"git ls-files 실패 ({repo} 가 git 저장소가 맞나요?): {proc.stderr.strip()}",
        ))
    return [line for line in proc.stdout.splitlines() if line.strip()]


def is_candidate(repo, path):
    base = os.path.basename(path)
    if base.lower() in LOCKFILES:
        return False
    if ".min." in base.lower():
        return False
    ext = os.path.splitext(base)[1].lower().lstrip(".")
    if ext in BINARY_EXTS:
        return False
    segs = path.lower().split("/")
    for seg in segs[:-1]:
        if seg in DROP_DIR_SEGMENTS:
            return False
    try:
        if os.path.getsize(os.path.join(repo, path)) > MAX_FILE_BYTES:
            return False
    except OSError:
        return False
    return True


# --------------------------------------------------------------------------- #
# scope: prefilter
# --------------------------------------------------------------------------- #

# Common trailing Korean particles, longest first, so a stripped noun also
# becomes a keyword ("어댑터에서" -> "어댑터") and git grep -F can match it.
KO_PARTICLES = (
    "에서는", "으로는", "에서", "으로", "에게", "까지", "부터", "처럼",
    "하고", "이랑", "과", "와", "은", "는", "이", "가", "을", "를",
    "에", "의", "도", "로", "만",
)


def extract_keywords(task):
    words = re.findall(r"\w+", task, re.UNICODE)
    seen, out = set(), []

    def add(token):
        if token and token not in seen:
            seen.add(token)
            out.append(token)

    for w in words:
        wl = w.lower()
        # ASCII tokens keep the >= 3 rule; non-ASCII (e.g. Korean) allow >= 2.
        if len(wl) < (3 if wl.isascii() else 2):
            continue
        add(wl)
        if not wl.isascii():
            for suf in KO_PARTICLES:
                if wl.endswith(suf) and len(wl) - len(suf) >= 2:
                    add(wl[: -len(suf)])
                    break
    return out


def git_grep_files(repo, keyword):
    proc = subprocess.run(
        ["git", "-C", repo, "grep", "-l", "-i", "-I", "-F", "-e", keyword],
        capture_output=True, text=True,
    )
    if proc.returncode not in (0, 1):  # 1 == no match, >1 == error
        return set()
    return {line for line in proc.stdout.splitlines() if line.strip()}


def prefilter(repo, candidates, task, limit=PREFILTER_LIMIT):
    if len(candidates) <= limit:
        return candidates
    keywords = extract_keywords(task)
    hits = {c: 0 for c in candidates}
    cand_lower = {c: c.lower() for c in candidates}
    for kw in keywords:
        for f in git_grep_files(repo, kw):
            if f in hits:
                hits[f] += 1
        for c in candidates:
            if kw in cand_lower[c]:
                hits[c] += 1
    # Rank by hits desc (0-hit files sort last and backfill up to the limit).
    ranked = sorted(candidates, key=lambda c: (-hits[c], c))
    return ranked[:limit]


# --------------------------------------------------------------------------- #
# scope: descriptors
# --------------------------------------------------------------------------- #

SYMBOL_PATTERNS = [
    re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)", re.M),                       # python
    re.compile(r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)", re.M),
    re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+\*?\s*([A-Za-z_$][\w$]*)", re.M),
    re.compile(r"^\s*(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)", re.M),
    re.compile(r"^\s*(?:export\s+)?type\s+([A-Za-z_$][\w$]*)", re.M),
    re.compile(r"^\s*(?:export\s+)?enum\s+([A-Za-z_$][\w$]*)", re.M),
    re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)", re.M),
    re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)", re.M),                   # go
    re.compile(r"^\s*(?:public\s+|private\s+|internal\s+|open\s+|static\s+)*(?:fun|fn)\s+([A-Za-z_]\w*)", re.M),  # kotlin/rust
]


def descriptor(repo, path, char_limit=DESC_SYMBOL_CHARS):
    names, seen = [], set()
    try:
        with open(os.path.join(repo, path), "r", encoding="utf-8", errors="ignore") as fh:
            text = fh.read(MAX_FILE_BYTES)
    except OSError:
        text = ""
    for pat in SYMBOL_PATTERNS:
        for m in pat.finditer(text):
            name = m.group(1)
            if name and name not in seen:
                seen.add(name)
                names.append(name)
    sym = ", ".join(names)
    if len(sym) > char_limit:
        sym = sym[:char_limit].rstrip(", ") + "…"
    return f"{path}\nsymbols: {sym}" if sym else path


# --------------------------------------------------------------------------- #
# scope: Jev requests
# --------------------------------------------------------------------------- #

def build_question(desc):
    return {
        "type": "noul",
        "instructions": (
            "Would implementing this task require modifying, or closely reading "
            "to understand, this file?\n\n" + desc
        ),
        "criteria": {
            "true": "This file would need to be edited, or carefully read, to complete the task.",
            "false": "This file is unrelated to the task and would not be touched or read.",
        },
    }


def run_scope_requests(task, descs, api_key, batch_size=BATCH_SIZE, workers=MAX_WORKERS):
    batches = [list(range(i, min(i + batch_size, len(descs))))
               for i in range(0, len(descs), batch_size)]

    def do_batch(chunk):
        questions = {f"f{idx}": build_question(descs[idx]) for idx in chunk}
        payload = {"model": MODEL, "state": task, "questions": questions}
        return chunk, api_request(payload, api_key)

    probs, total_input_tokens, errors = {}, 0, []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(do_batch, b) for b in batches]
        for fut in concurrent.futures.as_completed(futures):
            try:
                chunk, resp = fut.result()
            except JevError as exc:
                errors.append(str(exc))
                continue
            answers = resp.get("answers", {}) or {}
            usage = resp.get("usage", {}) or {}
            total_input_tokens += int(usage.get("input_tokens", 0) or 0)
            for idx in chunk:
                ans = answers.get(f"f{idx}")
                if isinstance(ans, dict) and ans.get("noul") is not None:
                    probs[idx] = float(ans["noul"])
    return probs, total_input_tokens, errors


# --------------------------------------------------------------------------- #
# scope: command
# --------------------------------------------------------------------------- #

def cmd_scope(args):
    repo = os.path.abspath(args.repo)
    parts = []
    if args.task:
        parts.append(args.task.strip())
    if args.task_file:
        try:
            with open(args.task_file, "r", encoding="utf-8") as fh:
                parts.append(fh.read().strip())
        except OSError as exc:
            sys.stderr.write(t(
                f"Failed to read --task-file: {exc}\n",
                f"--task-file 읽기 실패: {exc}\n",
            ))
            sys.exit(1)
    task = "\n".join(p for p in parts if p).strip()
    if not task:
        sys.stderr.write(t(
            "Task description is empty. Provide --task or --task-file.\n",
            "작업 설명이 비어 있습니다. --task 또는 --task-file 을 주세요.\n",
        ))
        sys.exit(1)

    api_key = get_api_key()

    try:
        all_files = git_ls_files(repo)
    except JevError as exc:
        sys.stderr.write(str(exc) + "\n")
        sys.exit(1)

    candidates = [f for f in all_files if is_candidate(repo, f)]
    if not candidates:
        sys.stderr.write(t("No candidate files found.\n", "후보 파일이 없습니다.\n"))
        sys.exit(1)
    files = prefilter(repo, candidates, task)
    descs = [descriptor(repo, f) for f in files]

    try:
        probs, total_input_tokens, errors = run_scope_requests(task, descs, api_key)
    except JevError as exc:
        sys.stderr.write(str(exc) + "\n")
        sys.exit(1)

    if errors and not probs:
        sys.stderr.write(
            t("All requests failed:\n  ", "모든 요청이 실패했습니다:\n  ")
            + "\n  ".join(errors) + "\n"
        )
        sys.exit(1)
    if errors:
        sys.stderr.write(t(
            f"Warning: {len(errors)} batch(es) failed (partial results only)\n",
            f"경고: {len(errors)}개 배치 실패 (부분 결과만 표시)\n",
        ))

    ranked = sorted(probs.items(), key=lambda kv: (-kv[1], files[kv[0]]))
    selected = [(prob, files[idx]) for idx, prob in ranked if prob >= args.min][: args.top]
    unscored = [files[i] for i in range(len(files)) if i not in probs]

    if args.json:
        out = {
            "task": task,
            "repo": repo,
            "candidates": len(files),
            "input_tokens": total_input_tokens,
            "min": args.min,
            "top": args.top,
            "results": [{"path": path, "probability": round(prob, 4)}
                        for prob, path in selected],
            "unscored": unscored,
            "failed_batches": len(errors),
        }
        json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return

    for prob, path in selected:
        sys.stdout.write(f"{prob:>4.2f}  {path}\n")
    if not selected:
        sys.stdout.write(t(
            f"(no files with prob ≥ {args.min:.2f})\n",
            f"(prob ≥ {args.min:.2f} 인 파일 없음)\n",
        ))
    footer = t(
        f"# {len(files)} candidates · {total_input_tokens:,} input tokens",
        f"# 후보 {len(files)}개 · 입력 토큰 {total_input_tokens:,}",
    )
    if errors:
        footer += t(
            f" · {len(errors)} failed batch(es) ({len(unscored)} unscored)",
            f" · 실패 배치 {len(errors)}개(미채점 {len(unscored)}개)",
        )
    sys.stdout.write(footer + "\n")


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(prog="jev.py", description="Jev (TypeSafe System One) helper.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("call", help='stdin {"state":..,"questions":{..}} -> response JSON')

    sc = sub.add_parser("scope", help="rank repo files by relevance to a task")
    sc.add_argument("--task", help="task text")
    sc.add_argument("--task-file", help="read task text from a file")
    sc.add_argument("--repo", default=os.getcwd(), help="repo dir (default: cwd)")
    sc.add_argument("--top", type=int, default=15, help="max files to list (default 15)")
    sc.add_argument("--min", type=float, default=0.3, help="min probability (default 0.3)")
    sc.add_argument("--json", action="store_true", help="machine-readable output")

    args = parser.parse_args()
    if args.cmd == "call":
        cmd_call(args)
    elif args.cmd == "scope":
        cmd_scope(args)


if __name__ == "__main__":
    main()
