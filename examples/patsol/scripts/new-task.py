#!/usr/bin/env python3
"""Deterministic executor for the /new-task pipeline.

The LLM generates the *content* (Jira body, Notion plan, OKR) and passes
it in as a JSON file. This script does only the mechanical, error-prone work:
discover the active sprint, create the Jira ticket + comment, create the Notion
page, and cut the git branch — using cached IDs from task-config.json so there
is zero trial-and-error against the APIs.

Requires the `requests` package.

Usage:
    python3 new-task.py content.json [--repo /path/to/repo]
    cat content.json | python3 new-task.py -

content.json schema:
{
  "summary":      "Jira title",                # required
  "jira_wiki":    "h3. Background (Why)\n- ...", # required, Jira wiki markup (v2)
  "jira_comment": "Core goal + technical concern", # required
  "label":        "backend",                   # backend | frontend (default backend)
  "notion_title": "...",                       # default = summary
  "notion_md":    "## 1. Background...\n- ...",  # required, simple markdown
  "work_type":    ["Feature"],                 # optional, Notion work-type multi-select;
                                               # values must match the Notion multi-select
                                               # options verbatim (Korean in the default
                                               # workspace, e.g. "기능 개발")
  "branch_slug":  "short-kebab-description",   # required
  "branch_type":  "feature"                    # feature | hotfix (default feature)
}
"""
import base64
import datetime
import json
import os
import re
import subprocess
import sys

import requests


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


HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.expanduser("{{AGENT_RULES_ENV}}")
CONFIG_PATH = os.path.join(HERE, "task-config.json")


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def load_env(path):
    env = {}
    with open(path) as f:
        for line in f:
            line = re.sub(r"^export\s+", "", line.strip())
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def md_to_notion_blocks(md):
    """Lightweight markdown -> Notion block objects. Handles headings, bullets,
    numbered lists, and paragraphs with **bold** inline."""
    def rich(text):
        out = []
        for i, part in enumerate(text.split("**")):
            if part == "":
                continue
            out.append({
                "type": "text",
                "text": {"content": part},
                "annotations": {"bold": i % 2 == 1},
            })
        return out or [{"type": "text", "text": {"content": ""}}]

    def block(btype, text):
        return {"object": "block", "type": btype, btype: {"rich_text": rich(text)}}

    blocks = []
    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("#### "):
            blocks.append(block("heading_3", line[5:]))
        elif line.startswith("### "):
            blocks.append(block("heading_3", line[4:]))
        elif line.startswith("## "):
            blocks.append(block("heading_2", line[3:]))
        elif line.startswith("# "):
            blocks.append(block("heading_1", line[2:]))
        elif re.match(r"^\s*[-*]\s+", line):
            blocks.append(block("bulleted_list_item", re.sub(r"^\s*[-*]\s+", "", line)))
        elif re.match(r"^\s*\d+\.\s+", line):
            blocks.append(block("numbered_list_item", re.sub(r"^\s*\d+\.\s+", "", line)))
        else:
            blocks.append(block("paragraph", line.strip()))
    return blocks


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    repo_override = None
    if "--repo" in args:
        i = args.index("--repo")
        repo_override = args[i + 1] if i + 1 < len(args) else ""
        del args[i:i + 2]
    argv = [a for a in args if a != "--dry-run"]
    if not argv:
        die("usage: new-task.py [--dry-run] [--repo <path>] <content.json | ->")
    if repo_override is not None and not os.path.isdir(repo_override):
        die(f"--repo path not found: {repo_override}")
    src = argv[0]
    content = json.load(sys.stdin if src == "-" else open(src))

    for req in ("summary", "jira_wiki", "jira_comment", "notion_md", "branch_slug"):
        if not content.get(req):
            die(f"content missing required field: {req}")

    env = load_env(ENV_PATH)
    cfg = json.load(open(CONFIG_PATH))
    jc, nc, gc = cfg["jira"], cfg["notion"], cfg["git"]

    base = env["JIRA_BASE_URL"].rstrip("/")
    auth = base64.b64encode(
        f"{env['JIRA_EMAIL']}:{env['JIRA_API_TOKEN']}".encode()
    ).decode()
    jh = {
        "Authorization": f"Basic {auth}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    label = content.get("label", "backend")

    # 1) Active sprint (runtime — changes weekly)
    sprint_id = None
    sr = requests.get(
        f"{base}/rest/agile/1.0/board/{jc['board_id']}/sprint",
        headers=jh, params={"state": "active"},
    )
    if sr.ok:
        vals = sr.json().get("values", [])
        if vals:
            sprint_id = vals[0]["id"]
    if sprint_id is None:
        print("WARN: no active sprint found; ticket created without sprint",
              file=sys.stderr)

    # 2) Create Jira issue (v2 — accepts wiki markup string directly)
    fields = {
        "project": {"key": jc["project_key"]},
        "issuetype": {"id": jc["issuetype_id"]},
        "summary": content["summary"],
        "description": content["jira_wiki"],
        "assignee": {"accountId": jc["assignee_account_id"]},
        "labels": [label],
        jc["team_field"]: jc["team_id"],
    }
    if sprint_id is not None:
        fields[jc["sprint_field"]] = sprint_id

    if dry_run:
        today = datetime.date.today().isoformat()
        preview = {
            "sprint_id": sprint_id,
            "jira_payload": {"fields": fields},
            "jira_comment": content["jira_comment"],
            "notion_props_keys": list({
                nc["prop_title"], nc["prop_url"], nc["prop_start_date"],
            }),
            "notion_block_count": len(md_to_notion_blocks(content["notion_md"])),
            "notion_blocks_sample": md_to_notion_blocks(content["notion_md"])[:4],
            "branch": f"{gc['feature_prefix']}-{jc['project_key']}-XXX/{content['branch_slug']}",
            "repo": repo_override or gc["repo"],
        }
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return

    r = requests.post(f"{base}/rest/api/2/issue", headers=jh,
                      data=json.dumps({"fields": fields}))
    if not r.ok:
        die(f"Jira issue create failed [{r.status_code}]: {r.text}")
    key = r.json()["key"]
    jira_url = f"{base}/browse/{key}"

    # 3) Jira comment
    cr = requests.post(f"{base}/rest/api/2/issue/{key}/comment", headers=jh,
                       data=json.dumps({"body": content["jira_comment"]}))
    if not cr.ok:
        print(f"WARN: Jira comment failed [{cr.status_code}]: {cr.text}",
              file=sys.stderr)

    # 4) Notion page
    nh = {
        "Authorization": f"Bearer {env['NOTION_API_TOKEN']}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    today = datetime.date.today().isoformat()
    props = {
        nc["prop_title"]: {"title": [
            {"text": {"content": content.get("notion_title") or content["summary"]}}
        ]},
        nc["prop_url"]: {"url": jira_url},
        nc["prop_start_date"]: {"date": {"start": today}},
    }
    wt = content.get("work_type")
    if wt:
        wt = wt if isinstance(wt, list) else [wt]
        key_name = "multi_select" if nc.get("work_type_is_multi") else "select"
        val = [{"name": w} for w in wt] if nc.get("work_type_is_multi") else {"name": wt[0]}
        props[nc["prop_work_type"]] = {key_name: val}

    blocks = md_to_notion_blocks(content["notion_md"])
    npage = requests.post(
        "https://api.notion.com/v1/pages", headers=nh,
        data=json.dumps({
            "parent": {"database_id": env["NOTION_PLAN_DB_ID"]},
            "properties": props,
            "children": blocks[:100],  # Notion caps children at 100 per request
        }),
    )
    if not npage.ok:
        die(f"Notion page create failed [{npage.status_code}]: {npage.text}\n"
            f"(Jira ticket {key} was already created)")
    notion_url = npage.json().get("url", "")

    # 5) Git branch
    prefix = gc["hotfix_prefix"] if content.get("branch_type") == "hotfix" else gc["feature_prefix"]
    branch = f"{prefix}-{key}/{content['branch_slug']}"
    repo = repo_override or gc["repo"]
    git_log = []
    try:
        for cmd in (
            ["git", "-C", repo, "checkout", gc["base_branch"]],
            ["git", "-C", repo, "pull", "origin", gc["base_branch"]],
            ["git", "-C", repo, "checkout", "-b", branch],
        ):
            p = subprocess.run(cmd, capture_output=True, text=True)
            git_log.append((" ".join(cmd[3:]), p.returncode, p.stderr.strip()))
    except Exception as e:
        git_log.append(("exception", 1, str(e)))

    branch_ok = git_log and git_log[-1][1] == 0
    if not branch_ok:
        print(f"WARN: branch creation may have failed: {git_log}", file=sys.stderr)

    # Result (machine + human)
    result = {"jira_key": key, "jira_url": jira_url, "notion_url": notion_url,
              "branch": branch, "sprint_id": sprint_id, "branch_ok": branch_ok}
    print(json.dumps(result, ensure_ascii=False))
    print(f"\nJIRA: {key} | {jira_url}")
    print(f"NOTION: {notion_url}")
    print(f"BRANCH: {branch}" + ("" if branch_ok else t("  (needs verification)", "  (확인 필요)")))


if __name__ == "__main__":
    main()
