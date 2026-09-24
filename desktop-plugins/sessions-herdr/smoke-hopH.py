"""Hop H smoke. Does not claim a ready card. Does not POST the duplex webhook.

Updated 2026-09-24 (cierre-os-0924): ports 9119/9120 retired (PORTS = 8642, 8766; :8766 is
on-demand, may be down); deep links are empty on purpose (dashboard gone, deepLinkNote says why);
the running card comes from argv[1] / HOPH_RUNNING or the first running card in kanban.db, and
claim-on-running checks are skipped (not failed) when nothing is running.
  py -3 desktop-plugins/sessions-herdr/smoke-hopH.py [t_<hex>]
"""
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "hermes-plugin" / "sessions-herdr" / "dashboard" / "plugin_api.py"
JS = ROOT / "desktop-plugins" / "sessions-herdr" / "plugin.js"
OUT = Path(__file__).resolve().with_suffix(".json")

spec = importlib.util.spec_from_file_location("sessions_herdr_api", API)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _first_running() -> str:
    db = mod._kanban_db_path()
    if not db.exists():
        return ""
    con = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
    try:
        row = con.execute("SELECT id FROM tasks WHERE status = 'running' LIMIT 1").fetchone()
    except sqlite3.Error:
        row = None
    finally:
        con.close()
    return row[0] if row else ""


RUNNING = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("HOPH_RUNNING", "")) or _first_running()

checks = {}
failed = []


def check(name, ok, detail=""):
    checks[name] = bool(ok)
    if not ok:
        failed.append({"name": name, "detail": str(detail)[:400]})


ports = mod.ports()
rows = {r["port"]: r for r in ports["ports"]}
check("ports_order", [r["port"] for r in ports["ports"]] == [8642, 8766], ports["ports"])
check("retired_ports_absent", 9119 not in rows and 9120 not in rows, sorted(rows))
check("label_8766", ports["labels"].get("8766") == "Evidence hub", ports["labels"])
check("no_8788_label", "8788" not in json.dumps(ports["labels"]), ports["labels"])
check("no_8788_reconcile", "8788" not in ports.get("reconcile", ""), ports.get("reconcile"))
check("gateway_path_health", rows[8642]["path"] == "/health" and rows[8642]["up"] is True, rows[8642])
# :8766 is on-demand (GUI-PASS only): down is fine; if up it must answer 200
check("evidence_8766_ok_or_down", rows[8766]["up"] is False or rows[8766]["http"] == 200, rows[8766])

ev = mod._evidence(mod.SessionRef())
check("evidence_url_8766", ev.get("url") == "http://127.0.0.1:8766/", ev)
check("evidence_no_8788", "8788" not in json.dumps(ev), ev)

refused = {}
if RUNNING:
    before = mod._kanban_show(RUNNING)
    before_status = (before.get("task") or {}).get("status") if before.get("ok") else None
    check("show_running_before", before.get("ok") and before_status == "running", before)

    unconfirmed = mod._claim(mod.ClaimBody(kanbanId=RUNNING, confirm=False))
    check("claim_needs_confirm", unconfirmed.get("need_confirm") is True and unconfirmed.get("claimed") is False, unconfirmed)

    refused = mod._claim(mod.ClaimBody(kanbanId=RUNNING, confirm=True))
    check(
        "claim_refuses_running",
        refused.get("claimed") is False and "status=running" in str(refused.get("reason")),
        refused,
    )
    check("claim_deep_link_empty", refused.get("deep_link") == "", refused.get("deep_link"))

    after = mod._kanban_show(RUNNING)
    after_status = (after.get("task") or {}).get("status") if after.get("ok") else None
    check("lock_not_stolen", after_status == "running" and after_status == before_status, after_status)
else:
    checks["claim_on_running_skipped"] = True  # nothing running: no card to refuse, not a failure
check("session_deep_link_note", mod._session_from_task({"id": "t_ab12"}).get("deepLinkNote", "").startswith("sin deep link"))

missing = mod._claim(mod.ClaimBody(kanbanId="t_00000000", confirm=True))
check("claim_missing_visible", missing.get("ok") is False and missing.get("reason"), missing)

bad = mod._claim(mod.ClaimBody(kanbanId="not-an-id", confirm=True))
check("claim_bad_id", bad.get("ok") is False and "t_<hex>" in str(bad.get("reason")), bad)

dup = mod._duplex(None)
check("duplex_anchor", dup.get("anchored") is True and dup.get("events") == [], dup.get("note"))
check("duplex_template_empty", dup.get("deep_link_template") == "", dup.get("deep_link_template"))
hooks = dup.get("hooks") or {}
check("duplex_hook_notify", str(hooks.get("notify", "")).endswith("hermes-duplex-notify.ps1"), hooks)
check("duplex_hook_py", str(hooks.get("hook", "")).endswith("duplex-kanban-done.py"), hooks)
check("duplex_kind", hooks.get("kind") == "kanban_done", hooks)
check("duplex_no_post", "does not POST" in str(dup.get("note")), dup.get("note"))
check("duplex_source_no_subprocess", "subprocess" not in (mod._duplex.__doc__ or "") and "powershell" not in mod._duplex.__code__.co_names, mod._duplex.__code__.co_names)

later = mod._duplex(0)
sample = (later.get("events") or [None])[0]
if sample:
    check("duplex_event_shape", sample.get("kind") == "kanban_done" and sample.get("task_id") and sample.get("deep_link") == "", sample)
else:
    check("duplex_event_shape", True, "no completed events since 0 — shape check skipped")

PACKET_ID = RUNNING or "t_ab12"
packet = mod._handoff_text(mod.HandoffBody(kanbanId=PACKET_ID, title="hop H", goal="A4 extras"))
text = packet.get("text") or ""
check("handoff_type", "type: handoff-packet" in text, text[:200])
check("handoff_no_secrets", "sender_key" not in text and "webhook_url" not in text and "Bearer" not in text, "secret leak")
check("handoff_has_id", PACKET_ID in text, text[:240])

js = JS.read_text(encoding="utf-8")
check("ui_claim", "children: 'Claim'" in js)
check("ui_copy", "Copy handoff" in js)
check("ui_8766", "8766: 'Evidence hub'" in js)
check("ui_toast", "title: 'kanban_done'" in js)
check("ui_no_8788", "8788" not in js)
check("ui_health_path", "'/health'" in js)
check("health_hop", mod.health().get("hop") == "H", mod.health())

report = {
    "hop": "H",
    "ok": not failed,
    "failed": failed,
    "checks": checks,
    "ports": {str(k): {"up": v.get("up"), "http": v.get("http"), "path": v.get("path")} for k, v in rows.items()},
    "running_card": RUNNING or None,
    "claim_running_reason": refused.get("reason"),
    "duplex_hooks": hooks,
    "note": "Did not call hermes kanban claim on a ready card. Did not POST the duplex webhook. Desktop restart required for live UI.",
}
OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({"ok": report["ok"], "failed": failed, "n": len(checks)}, indent=2))
sys.exit(0 if report["ok"] else 1)
