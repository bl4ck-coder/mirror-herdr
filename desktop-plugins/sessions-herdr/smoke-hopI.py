"""Hop I visual smoke. Does not drive the GUI. Does not touch kanban."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\nachi\ObsidianVaults\mirror-brain\01-Projects\Hermes\mirror-herdr")
JS = ROOT / "desktop-plugins" / "sessions-herdr" / "plugin.js"
TWIN = ROOT / "hermes-plugin" / "sessions-herdr" / "desktop" / "plugin.js"
API = ROOT / "hermes-plugin" / "sessions-herdr" / "dashboard" / "plugin_api.py"
OUT = ROOT / "desktop-plugins" / "sessions-herdr" / "smoke-hopI.json"

checks = {}
failed = []


def check(name, ok, detail=""):
    checks[name] = bool(ok)
    if not ok:
        failed.append({"name": name, "detail": str(detail)[:400]})


js = JS.read_text(encoding="utf-8")
twin = TWIN.read_text(encoding="utf-8")
check("twins_identical", js == twin, "desktop-plugins vs hermes-plugin desktop")
check("cta", "Abrí un agente en Sessions" in js)
check("empty_class", "sessions-empty" in js and "sessions-glass-illu" in js)
check("glass_root", "sessions-aizurg-glass" in js and "sessions-aizurg-glass-style" in js)
check("gold_hi", "#e8c35a" in js)
check("gold_deep", "#d4a017" in js)
check("glass_blur", "--glass-blur: 22px" in js)
check("not_night_bg", "#040405" not in js, "night theme bg")
check("not_night_gold", "#d4b056" not in js, "night gold-hi")
check("hop_label", "Hop I · liquid-glass AIZURG" in js)
check("create_above_copy", "El formulario de create está arriba." in js)
check("ui_claim", "children: 'Claim'" in js)
check("ui_copy", "Copy handoff" in js)
check("ui_8766", "8766: 'Evidence hub'" in js)
check("ui_toast", "title: 'kanban_done'" in js)
check("ui_health", "'/health'" in js)
check("ui_no_8788", "8788" not in js)
check("create_label", "children: 'Create + link'" in js)
check("not_second_board", "not a second board" in js)

spec = importlib.util.spec_from_file_location("sessions_herdr_api", API)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
check("api_import", hasattr(mod, "health"))
health = mod.health()
check("api_health_hop_h", health.get("hop") == "H", health)

report = {
    "hop": "I",
    "kind": "visual-dom-notes",
    "ok": not failed,
    "failed": failed,
    "checks": checks,
    "sha256": hashlib.sha256(JS.read_bytes()).hexdigest(),
    "dom": {
        "root": "div.sessions-aizurg-glass",
        "style": "style#sessions-aizurg-glass-style",
        "form": ".sessions-form",
        "ports": ".sessions-port",
        "create": "button.sessions-create text Create + link",
        "empty": ".sessions-empty > svg.sessions-glass-illu + .sessions-cta",
        "cta": "Abrí un agente en Sessions",
        "rows": ".sessions-row / .sessions-row-focused",
        "toasts": ".sessions-toasts",
        "tokens": "default AIZURG liquid-glass (#e8c35a / #d4a017 / blur 22px), not night #040405/#d4b056, not flat Desktop stroke on those panels",
    },
    "note": "No GUI screenshot. Desktop restart required before the live Sessions tab shows Hop I.",
}
OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"ok": report["ok"], "failed": failed, "n": len(checks)}, indent=2))
sys.exit(0 if report["ok"] else 1)
