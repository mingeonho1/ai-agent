#!/usr/bin/env python3
"""Render an example company profile into a Claude Code config dir.

A *profile* (e.g. ``examples/patsol``) is a sanitized bundle of skills,
commands, agents, hooks and automations where every environment-specific value
(domains, Jira site, account/cloud IDs, Slack/Notion IDs, repo paths, emails,
people) has been replaced by a ``{{VARIABLE}}`` placeholder. This renderer asks
the installing user for each variable, fills the placeholders in, and writes the
result into their Claude config dir.

Usage:
    python3 examples/render.py <profile> --out <dir> [options]

Options:
    --out <dir>        Claude config dir to render into
                       (default: $CLAUDE_CONFIG_DIR or ~/.claude)
    --answers <file>   JSON {"VAR": "value", ...}; non-interactive
    --yes              Non-interactive; use defaults / saved answers only
    --lang en|ko       Output language + which question text to show
                       (``question`` for en, ``question_ko`` for ko; default en)
    --dry-run          Print what would be written; change nothing
    --list-questions   Print the variable questions as JSON and exit
    -h, --help         Show this help

The renderer:
  * renders ``<profile>/claude/**``      -> ``<out>/**``
  * renders ``<profile>/routines/**``    -> ``<out>/example-profiles/<profile>/routines/**``
  * renders ``<profile>/scripts/**``     -> ``<out>/example-profiles/<profile>/scripts/**``
  * merges ``<profile>/settings.fragment.json`` hooks into ``<out>/settings.json``
  * saves the (non-secret) answers to ``<out>/example-profiles/<profile>/answers.json``

Existing files that would change are backed up to ``<name>.bak-<ts>``
first. Executable bits are preserved. The run FAILS (writing nothing) if a
required answer is missing or if any ``{{...}}`` placeholder is left unrendered.

Python 3.9+, standard library only.
"""
import argparse
import json
import os
import re
import shutil
import stat
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Z0-9_]+)\s*\}\}")
# Profile name: block path traversal (no separators / parent refs / absolute).
# 프로파일 이름: 경로 조작 방지(디렉터리 분리자·상위참조·절대경로 금지). 영숫자·_·- 만.
PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
SKIP_NAMES = {"__pycache__", ".DS_Store"}

# Active output language for t(); set once in main() from --lang.
# t() 가 보는 현재 출력 언어; main() 에서 --lang 로 1회 설정된다.
_LANG = "en"


def set_lang(lang):
    """Set the active output language ('en' or 'ko'). / 현재 출력 언어 설정."""
    global _LANG
    _LANG = "ko" if lang == "ko" else "en"


def t(en, ko):
    """Return the English or Korean string for the active language.
    현재 언어에 맞는 영어/한국어 문자열을 반환한다."""
    return ko if _LANG == "ko" else en


def is_skippable(name):
    return (
        name in SKIP_NAMES
        or name.endswith(".pyc")
        or ".bak" in name
    )


def load_profile(name):
    if not PROFILE_NAME_RE.match(name or ""):
        die(t("invalid profile name: %r (letters, digits, '_' and '-' only; "
              "no path separators or '..')",
              "invalid profile name: %r (영문/숫자/'_'/'-' 만, 경로 분리자·'..' 불가)")
            % name)
    pdir = os.path.join(HERE, name)
    pjson = os.path.join(pdir, "profile.json")
    if not os.path.isdir(pdir) or not os.path.isfile(pjson):
        die(t("profile not found: %s (expected %s)",
              "프로파일을 찾을 수 없습니다: %s (기대 경로 %s)") % (name, pjson))
    with open(pjson, encoding="utf-8") as f:
        prof = json.load(f)
    return pdir, prof


def die(msg, code=2):
    sys.stderr.write("ERROR: %s\n" % msg)
    sys.exit(code)


def variables(prof):
    """Declared variables that are asked (excludes auto-filled ones).
    질문으로 받는 선언 변수(자동 채움 변수는 제외)."""
    return [v for v in prof.get("variables", []) if not v.get("auto")]


def auto_variables(prof):
    return [v for v in prof.get("variables", []) if v.get("auto")]


def question_for(v, lang):
    """Question text for the chosen language: question_ko for ko (fallback to
    the English ``question``), else ``question``.
    선택 언어의 질문 문구: ko 면 question_ko(없으면 영어 question), 아니면 question."""
    if lang == "ko":
        q = v.get("question_ko")
        if q:
            return q
    return v.get("question", v["name"])


# ---------------------------------------------------------------- answers ---

def read_json_file(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def gather_answers(prof, out_dir, profile_name, answers_file, yes, interactive,
                   lang):
    """Resolve a value for every asked variable.
    질문 변수마다 값을 결정한다.

    Precedence: --answers file  >  interactive input  >  saved answers.json
    >  default. Required variables with no resolved value abort the run.
    우선순위: --answers 파일 > 대화형 입력 > 저장된 answers.json > default.
    값이 없는 필수 변수는 실행을 중단한다.
    """
    saved_path = os.path.join(
        out_dir, "example-profiles", profile_name, "answers.json"
    )
    saved = {}
    if os.path.isfile(saved_path):
        try:
            saved = read_json_file(saved_path)
        except (OSError, ValueError):
            saved = {}

    supplied = {}
    if answers_file:
        if answers_file == "-":
            supplied = json.load(sys.stdin)
        else:
            supplied = read_json_file(answers_file)

    resolved = {}
    missing = []
    for v in variables(prof):
        name = v["name"]
        default = v.get("default")
        prev = saved.get(name)
        # Default shown interactively: previously saved value, else declared default.
        # 대화형에서 보이는 기본값: 이전 저장값, 없으면 선언된 default.
        shown_default = prev if prev not in (None, "") else default

        if name in supplied:
            val = supplied[name]
        elif interactive and not yes and answers_file is None:
            val = prompt_one(v, shown_default, lang)
        elif prev not in (None, ""):
            val = prev
        else:
            val = default

        if val is None:
            val = "" if not v.get("required") else None

        if v.get("required") and (val is None or str(val).strip() == ""):
            missing.append(name)
            continue
        resolved[name] = "" if val is None else str(val)

    if missing:
        die(t("missing required answer(s): %s (nothing was written)",
              "필수 답변 누락: %s (아무것도 쓰지 않음)") % ", ".join(missing))

    return resolved, saved_path


def prompt_one(v, shown_default, lang="en"):
    name = v["name"]
    q = question_for(v, lang)
    example = v.get("example")
    req = v.get("required")
    hint = []
    if example:
        hint.append(t("e.g. %s", "예: %s") % example)
    if shown_default not in (None, ""):
        hint.append(t("default: %s", "기본값: %s") % shown_default)
    hint.append(t("required", "필수") if req else t("optional", "선택"))
    label = "\n%s\n  [%s] %s\n> " % (q, name, " · ".join(hint))
    while True:
        try:
            raw = input(label)
        except EOFError:
            raw = ""
        raw = raw.strip()
        if raw:
            return raw
        if shown_default not in (None, ""):
            return shown_default
        if not req:
            return ""
        sys.stderr.write(t("  (this field is required. Please enter a value.)\n",
                           "  (필수 항목입니다. 값을 입력하세요.)\n"))


# ----------------------------------------------------------------- render ---

def substitute(text, mapping):
    def repl(m):
        key = m.group(1)
        if key in mapping:
            return mapping[key]
        return m.group(0)  # leave unknown placeholders for the unrendered check
    return PLACEHOLDER_RE.sub(repl, text)


def unrendered(text):
    return [m.group(1) for m in PLACEHOLDER_RE.finditer(text)]


def _read_text_file(path):
    with open(path, "rb") as f:
        raw = f.read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def empty_routine_var_warnings(pdir, resolved):
    """Collect warnings for optional vars used in routines but left empty.
    routines 에서 쓰이는데 값이 빈 선택 변수들을 경고 문자열 리스트로 모은다.

    Required vars that are empty already abort, so only emptied optionals land
    here. E.g. an empty SLACK_USER_ID renders the slack-digest routine's ``<@>``.
    필수 변수가 비면 이미 중단되므로, 여기 걸리는 것은 비워 둔 선택 변수뿐이다.
    예: SLACK_USER_ID 를 비우면 slack-digest 루틴이 빈 ``<@>`` 로 렌더된다.
    """
    empty = {name for name, val in resolved.items() if val == ""}
    routines_root = os.path.join(pdir, "routines")
    if not empty or not os.path.isdir(routines_root):
        return []
    hits = {}  # var -> set(rel paths under pdir)
    for src, _dest, _mode in collect_tree(routines_root, routines_root):
        text = _read_text_file(src)
        if not text:
            continue
        for var in set(unrendered(text)):
            if var in empty:
                hits.setdefault(var, set()).add(os.path.relpath(src, pdir))
    lines = []
    for var in sorted(hits):
        files = ", ".join(sorted(hits[var]))
        lines.append(t(
            "warning: optional variable {{%s}} is empty, so routines render it "
            "blank (%s). Fill it in and re-render to use those routines.",
            "경고: 선택 변수 {{%s}} 가 비어 있어 routines 에서 빈 값으로 렌더됩니다 "
            "(%s). 해당 루틴을 쓰려면 값을 채워 다시 렌더하세요.") % (var, files))
    return lines


def collect_tree(src_root, dest_root):
    """Yield (src_path, dest_path, mode) for every renderable file under src_root."""
    for dirpath, dirnames, filenames in os.walk(src_root):
        dirnames[:] = [d for d in dirnames if not is_skippable(d)]
        for fn in filenames:
            if is_skippable(fn):
                continue
            src = os.path.join(dirpath, fn)
            rel = os.path.relpath(src, src_root)
            dest = os.path.join(dest_root, rel)
            mode = stat.S_IMODE(os.lstat(src).st_mode)
            yield src, dest, mode


def render_file(src, mapping):
    """Return (text_or_bytes, is_text, bad_placeholders)."""
    with open(src, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw, False, []
    rendered = substitute(text, mapping)
    return rendered, True, unrendered(rendered)


def merge_settings(existing, fragment):
    """Idempotently merge fragment['hooks'] into existing settings.
    fragment['hooks'] 를 기존 설정에 멱등 병합한다.

    A hook command is appended only if an identical command string is not
    already registered under the same event. Everything else is preserved.
    같은 event 에 동일 command 문자열이 없을 때만 추가하고, 나머지는 보존한다.
    """
    out = dict(existing)
    frag_hooks = fragment.get("hooks") or {}
    if not frag_hooks:
        return out, False
    hooks = dict(out.get("hooks") or {})
    changed = False
    for event, groups in frag_hooks.items():
        cur_groups = list(hooks.get(event) or [])
        present = set()
        for g in cur_groups:
            for h in (g.get("hooks") or []):
                if h.get("type") == "command" and "command" in h:
                    present.add(h["command"])
        for g in groups:
            new_hooks = [
                h for h in (g.get("hooks") or [])
                if not (h.get("type") == "command" and h.get("command") in present)
            ]
            if new_hooks:
                ng = dict(g)
                ng["hooks"] = new_hooks
                cur_groups.append(ng)
                changed = True
                for h in new_hooks:
                    if "command" in h:
                        present.add(h["command"])
        hooks[event] = cur_groups
    out["hooks"] = hooks
    return out, changed


# ------------------------------------------------------------------- main ---

def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True, description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("profile")
    ap.add_argument("--out", default=None)
    ap.add_argument("--answers", default=None)
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--lang", choices=["en", "ko"], default="en",
                    help="output language + which question text to show")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list-questions", action="store_true")
    args = ap.parse_args(argv)

    set_lang(args.lang)
    pdir, prof = load_profile(args.profile)

    if args.list_questions:
        # Include both question fields so callers can show either language.
        # 양쪽 question 필드를 모두 포함해 호출자가 어느 언어든 보일 수 있게 한다.
        qs = [
            {
                "name": v["name"],
                "question": v.get("question", v["name"]),
                "question_ko": v.get("question_ko"),
                "example": v.get("example"),
                "default": v.get("default"),
                "required": bool(v.get("required")),
                "secret": bool(v.get("secret")),
            }
            for v in variables(prof)
        ]
        print(json.dumps(qs, ensure_ascii=False, indent=2))
        return 0

    out_dir = args.out or os.environ.get("CLAUDE_CONFIG_DIR") \
        or os.path.expanduser("~/.claude")
    out_dir = os.path.abspath(out_dir)

    interactive = sys.stdin.isatty()
    resolved, saved_path = gather_answers(
        prof, out_dir, args.profile, args.answers, args.yes, interactive,
        args.lang
    )

    # Auto-filled variables (never asked). / 자동 채움 변수(묻지 않음).
    mapping = dict(resolved)
    for v in auto_variables(prof):
        if v["name"] == "CLAUDE_DIR":
            mapping["CLAUDE_DIR"] = out_dir
        else:
            mapping[v["name"]] = str(v.get("default") or "")

    routine_warnings = empty_routine_var_warnings(pdir, resolved)

    # --- Plan every write in memory first (atomic failure) -----------------
    # 모든 쓰기를 먼저 메모리에 계획한다(실패 시 원자적).
    plan = []        # (dest, content, is_text, mode)
    bad = {}         # dest -> [unresolved placeholders]

    trees = [
        (os.path.join(pdir, "claude"), out_dir),
        (os.path.join(pdir, "routines"),
         os.path.join(out_dir, "example-profiles", args.profile, "routines")),
        (os.path.join(pdir, "scripts"),
         os.path.join(out_dir, "example-profiles", args.profile, "scripts")),
    ]
    for src_root, dest_root in trees:
        if not os.path.isdir(src_root):
            continue
        for src, dest, mode in collect_tree(src_root, dest_root):
            content, is_text, leftover = render_file(src, mapping)
            if leftover:
                bad[dest] = sorted(set(leftover))
            plan.append((dest, content, is_text, mode))

    # settings fragment
    settings_dest = os.path.join(out_dir, "settings.json")
    settings_new = None
    frag_path = os.path.join(pdir, "settings.fragment.json")
    if os.path.isfile(frag_path):
        with open(frag_path, encoding="utf-8") as f:
            frag_text = substitute(f.read(), mapping)
        leftover = unrendered(frag_text)
        if leftover:
            bad[frag_path] = sorted(set(leftover))
        else:
            fragment = json.loads(frag_text)
            existing = {}
            if os.path.isfile(settings_dest):
                try:
                    existing = read_json_file(settings_dest)
                except ValueError:
                    die(t("existing settings.json is not valid JSON: %s",
                          "기존 settings.json 이 올바른 JSON 이 아닙니다: %s")
                        % settings_dest)
            settings_new, _ = merge_settings(existing, fragment)

    if bad:
        lines = [t("unrendered placeholders remain (nothing was written):",
                   "렌더되지 않은 자리표시자가 남았습니다 (아무것도 쓰지 않음):")]
        for dest in sorted(bad):
            lines.append("  %s -> %s" % (dest, ", ".join(bad[dest])))
        die("\n".join(lines))

    # --- Dry run -----------------------------------------------------------
    ts = time.strftime("%Y%m%d-%H%M%S")
    if args.dry_run:
        print(t("DRY RUN — would write %d file(s) into %s",
                "DRY RUN — %d개 파일을 %s 에 씁니다") % (len(plan), out_dir))
        for dest, _c, _t, _m in plan:
            print("  %s" % dest)
        if settings_new is not None:
            print("  %s %s" % (settings_dest, t("(hooks merged)", "(훅 병합)")))
        print("  %s %s" % (saved_path, t("(answers)", "(답변)")))
        for w in routine_warnings:
            sys.stderr.write(w + "\n")
        return 0

    # --- Write -------------------------------------------------------------
    written = 0
    for dest, content, is_text, mode in plan:
        write_file(dest, content, is_text, mode, ts)
        written += 1

    if settings_new is not None:
        backup_if_differs(settings_dest,
                          json.dumps(settings_new, ensure_ascii=False, indent=2),
                          ts)
        ensure_parent(settings_dest)
        with open(settings_dest, "w", encoding="utf-8") as f:
            json.dump(settings_new, f, ensure_ascii=False, indent=2)
            f.write("\n")

    # Save non-secret answers for re-runs. / 재실행을 위해 비밀이 아닌 답변 저장.
    secret_names = {v["name"] for v in prof.get("variables", []) if v.get("secret")}
    to_save = {k: val for k, val in resolved.items() if k not in secret_names}
    ensure_parent(saved_path)
    with open(saved_path, "w", encoding="utf-8") as f:
        json.dump(to_save, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(t("Rendered profile '%s' into %s (%d files).",
            "프로파일 '%s' 을(를) %s 에 렌더했습니다 (%d개 파일).")
          % (args.profile, out_dir, written))
    if settings_new is not None:
        print(t("Merged profile hooks into %s.",
                "프로파일 훅을 %s 에 병합했습니다.") % settings_dest)
    print(t("Saved answers to %s.", "답변을 %s 에 저장했습니다.") % saved_path)
    for w in routine_warnings:
        sys.stderr.write(w + "\n")
    return 0


def ensure_parent(path):
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)


def backup_if_differs(dest, new_text_or_bytes, ts):
    if not os.path.exists(dest):
        return
    with open(dest, "rb") as f:
        old = f.read()
    new_bytes = (new_text_or_bytes.encode("utf-8")
                 if isinstance(new_text_or_bytes, str) else new_text_or_bytes)
    if old == new_bytes:
        return
    shutil.copy2(dest, "%s.bak-%s" % (dest, ts))


def write_file(dest, content, is_text, mode, ts):
    if is_text:
        payload = content.encode("utf-8")
    else:
        payload = content
    backup_if_differs(dest, payload, ts)
    ensure_parent(dest)
    with open(dest, "wb") as f:
        f.write(payload)
    try:
        os.chmod(dest, mode)
    except OSError:
        pass


if __name__ == "__main__":
    sys.exit(main())
