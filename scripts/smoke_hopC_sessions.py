"""Hop C smoke: sessions-herdr create_session must return a real board kanbanId.

hold=True parks the card blocked so this verify does not dispatch a worker.
Prints only ids and status. No secrets.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes"
API = ROOT / "plugins" / "sessions-herdr" / "dashboard" / "plugin_api.py"
DB = ROOT / "kanban.db"
OUT = Path(__file__).resolve().parents[1] / "desktop-plugins" / "sessions-herdr" / "smoke-hopC-verify.json"

# Kanban lives on the machine root, not the builder profile home.
os.environ["HERMES_HOME"] = str(ROOT)


def load_api():
    spec = importlib.util.spec_from_file_location("sessions_herdr_api", API)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {API}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = load_api()
    body = mod.CreateBody(
        title="herdr-hopC-smoke-verify",
        assignee="sessions-smoke",
        goal="prove sessions-herdr create returns a real kanbanId",
        acceptance=["kanbanId exists in kanban.db", "id matches t_* not stub k-*"],
        doNot=["dispatch a builder worker", "SOUL promote"],
        hold=True,
    )
    result = mod.create_session(body)
    sess = result.get("session") or {}
    kid = sess.get("kanbanId") or ""
    real = isinstance(kid, str) and kid.startswith("t_") and not kid.startswith("k-")
    row = None
    if real and DB.is_file():
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        got = con.execute(
            "select id, title, status, created_by, assignee from tasks where id=?",
            (kid,),
        ).fetchone()
        row = dict(got) if got else None
        con.close()
    ok = bool(real and row and row.get("created_by") == "sessions-herdr")
    payload = {
        "ok": ok,
        "kanbanId": kid,
        "runId": sess.get("runId"),
        "herdrId": sess.get("herdrId"),
        "herdrPartial": sess.get("herdrPartial"),
        "status": sess.get("status"),
        "db_row": row,
        "stub": (not real),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": ok, "kanbanId": kid, "status": (row or {}).get("status"), "created_by": (row or {}).get("created_by")}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
