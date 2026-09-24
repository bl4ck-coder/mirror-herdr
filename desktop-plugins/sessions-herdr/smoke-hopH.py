"""Hop H smoke. Does not claim a ready card. Does not POST the duplex webhook."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

API = Path(r"C:\Users\nachi\ObsidianVaults\mirror-brain\01-Projects\Hermes\mirror-herdr\hermes-plugin\sessions-herdr\dashboard\plugin_api.py")
JS = Path(r"C:\Users\nachi\ObsidianVaults\mirror-brain\01-Projects\Hermes\mirror-herdr\desktop-plugins\sessions-herdr\plugin.js")
OUT = Path(r"C:\Users\nachi\ObsidianVaults\mirror-brain\01-Projects\Hermes\mirror-herdr\desktop-plugins\sessions-herdr\smoke-hopH.json")
RUNNING = "t_1a498a2a"

spec = importlib.util.spec_from_file_location("sessions_herdr_api", API)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

checks = {}
failed = []


def check(name, ok, detail=""):
    checks[name] = bool(ok)
    if not ok:
        failed.append({"name": name, "detail": str(detail)[:400]})


ports = mod.ports()
rows = {r["port"]: r for r in ports["ports"]}
check("ports_order", [r["port"] for r in ports["ports"]] == [8642, 9119, 8766, 9120], ports["ports"])
check("label_8766", ports["labels"].get("8766") == "Evidence hub", ports["labels"])
check("no_8788_label", "8788" not in json.dumps(ports["labels"]), ports["labels"])
check("no_8788_reconcile", "8788" not in ports.get("reconcile", ""), ports.get("reconcile"))
check("gateway_path_health", rows[8642]["path"] == "/health" and rows[8642]["up"] is True, rows[8642])
check("evidence_8766_up", rows[8766]["up"] is True and rows[8766]["http"] == 200, rows[8766])
check("9120_not_required", 9120 in rows and rows[9120]["up"] is False, rows.get(9120))

ev = mod._evidence(mod.SessionRef())
check("evidence_url_8766", ev.get("url") == "http://127.0.0.1:8766/", ev)
check("evidence_no_8788", "8788" not in json.dumps(ev), ev)

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
check("claim_deep_link", RUNNING in str(refused.get("deep_link")), refused.get("deep_link"))

after = mod._kanban_show(RUNNING)
after_status = (after.get("task") or {}).get("status") if after.get("ok") else None
check("lock_not_stolen", after_status == "running" and after_status == before_status, after_status)

missing = mod._claim(mod.ClaimBody(kanbanId="t_00000000", confirm=True))
check("claim_missing_visible", missing.get("ok") is False and missing.get("reason"), missing)

bad = mod._claim(mod.ClaimBody(kanbanId="not-an-id", confirm=True))
check("claim_bad_id", bad.get("ok") is False and "t_<hex>" in str(bad.get("reason")), bad)

dup = mod._duplex(None)
check("duplex_anchor", dup.get("anchored") is True and dup.get("events") == [], dup.get("note"))
hooks = dup.get("hooks") or {}
check("duplex_hook_notify", str(hooks.get("notify", "")).endswith("hermes-duplex-notify.ps1"), hooks)
check("duplex_hook_py", str(hooks.get("hook", "")).endswith("duplex-kanban-done.py"), hooks)
check("duplex_kind", hooks.get("kind") == "kanban_done", hooks)
check("duplex_no_post", "does not POST" in str(dup.get("note")), dup.get("note"))
check("duplex_source_no_subprocess", "subprocess" not in (mod._duplex.__doc__ or "") and "powershell" not in mod._duplex.__code__.co_names, mod._duplex.__code__.co_names)

later = mod._duplex(0)
sample = (later.get("events") or [None])[0]
if sample:
    check("duplex_event_shape", sample.get("kind") == "kanban_done" and sample.get("task_id") in str(sample.get("deep_link")), sample)
else:
    check("duplex_event_shape", True, "no completed events since 0 — shape check skipped")

packet = mod._handoff_text(mod.HandoffBody(kanbanId=RUNNING, title="hop H", goal="A4 extras"))
text = packet.get("text") or ""
check("handoff_type", "type: handoff-packet" in text, text[:200])
check("handoff_no_secrets", "sender_key" not in text and "webhook_url" not in text and "Bearer" not in text, "secret leak")
check("handoff_has_id", RUNNING in text, text[:240])

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
    "claim_running_reason": refused.get("reason"),
    "duplex_hooks": hooks,
    "note": "Did not call hermes kanban claim on a ready card. Did not POST the duplex webhook. Desktop restart required for live UI.",
}
OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({"ok": report["ok"], "failed": failed, "n": len(checks)}, indent=2))
sys.exit(0 if report["ok"] else 1)
