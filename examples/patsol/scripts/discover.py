#!/usr/bin/env python3
"""One-shot discovery of stable Jira/Notion IDs for the new-task pipeline.

Prints a JSON report of everything we need to cache so the runtime script
never has to rediscover field IDs by trial-and-error. Paste the relevant IDs
into task-config.json (or your answers.json) afterwards.

Requires the `requests` package. Reads credentials from the .env pointed to by
AGENT_RULES_ENV (rendered at install time).
"""
import base64
import json
import os
import re
import sys

import requests

ENV_PATH = os.path.expanduser("{{AGENT_RULES_ENV}}")
PROJECT_KEY = "{{JIRA_PROJECT_KEY}}"
ASSIGNEE_EMAIL = "{{USER_EMAIL}}"


def load_env(path):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            line = re.sub(r"^export\s+", "", line)
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def main():
    env = load_env(ENV_PATH)
    base = env["JIRA_BASE_URL"].rstrip("/")
    auth = base64.b64encode(
        f"{env['JIRA_EMAIL']}:{env['JIRA_API_TOKEN']}".encode()
    ).decode()
    jh = {"Authorization": f"Basic {auth}", "Accept": "application/json"}

    report = {}

    # --- Fields: find Sprint + Team custom fields ---
    fields = requests.get(f"{base}/rest/api/3/field", headers=jh).json()
    interesting = []
    for fld in fields:
        name = (fld.get("name") or "").lower()
        schema = fld.get("schema") or {}
        custom = schema.get("custom") or ""
        # "팀" is the Korean display name of the Jira team field — must match the workspace Jira schema.
        if (
            name in ("sprint", "team", "팀")
            or "sprint" in custom
            or "team" in custom.lower()
        ):
            interesting.append(
                {"id": fld["id"], "name": fld.get("name"), "custom": custom}
            )
    report["candidate_fields"] = interesting

    # --- Assignee accountId ---
    users = requests.get(
        f"{base}/rest/api/3/user/search",
        headers=jh,
        params={"query": ASSIGNEE_EMAIL},
    ).json()
    report["assignee_candidates"] = [
        {"accountId": u.get("accountId"), "displayName": u.get("displayName"),
         "email": u.get("emailAddress")}
        for u in users
    ]

    # --- Board + active sprint ---
    boards = requests.get(
        f"{base}/rest/agile/1.0/board",
        headers=jh,
        params={"projectKeyOrId": PROJECT_KEY},
    ).json()
    report["boards"] = [
        {"id": b["id"], "name": b.get("name"), "type": b.get("type")}
        for b in boards.get("values", [])
    ]
    if report["boards"]:
        bid = report["boards"][0]["id"]
        sprints = requests.get(
            f"{base}/rest/agile/1.0/board/{bid}/sprint",
            headers=jh,
            params={"state": "active"},
        ).json()
        report["active_sprints"] = [
            {"id": s["id"], "name": s.get("name")} for s in sprints.get("values", [])
        ]

    # --- createmeta: what fields are required/allowed for the project's Task ---
    meta = requests.get(
        f"{base}/rest/api/3/issue/createmeta",
        headers=jh,
        params={"projectKeys": PROJECT_KEY, "expand": "projects.issuetypes.fields"},
    ).json()
    try:
        proj = meta["projects"][0]
        for it in proj["issuetypes"]:
            # "작업" is the Korean display name of the Task issue type — must match the workspace Jira schema.
            if it["name"] in ("Task", "작업"):
                flds = it["fields"]
                # Team field allowed values if present
                for fid, f in flds.items():
                    nm = (f.get("name") or "").lower()
                    # "팀" is the Korean display name of the Jira team field — must match the workspace Jira schema.
                    if nm in ("team", "팀"):
                        report["team_field"] = {
                            "id": fid,
                            "name": f.get("name"),
                            "allowedValues": f.get("allowedValues", [])[:20],
                        }
                report["task_issuetype_id"] = it["id"]
                report["task_required_fields"] = [
                    fid for fid, f in flds.items() if f.get("required")
                ]
                break
    except Exception as e:
        report["createmeta_error"] = str(e)

    # --- Notion DB property schema ---
    nh = {
        "Authorization": f"Bearer {env['NOTION_API_TOKEN']}",
        "Notion-Version": "2022-06-28",
    }
    db = requests.get(
        f"https://api.notion.com/v1/databases/{env['NOTION_PLAN_DB_ID']}",
        headers=nh,
    ).json()
    props = {}
    for pname, p in db.get("properties", {}).items():
        entry = {"type": p.get("type")}
        if p.get("type") == "select":
            entry["options"] = [o["name"] for o in p["select"].get("options", [])]
        if p.get("type") == "status":
            entry["options"] = [o["name"] for o in p["status"].get("options", [])]
        props[pname] = entry
    report["notion_properties"] = props
    report["notion_db_title"] = "".join(
        t.get("plain_text", "") for t in db.get("title", [])
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
