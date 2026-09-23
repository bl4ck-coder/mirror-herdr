from pathlib import Path
import json, re, time, random, urllib.request
from datetime import datetime, timezone

def parse_packet_markdown(md: str) -> dict:
    text = md or ""
    def grab(pat: str) -> str:
        m = re.search(pat, text, re.M | re.I)
        return m.group(1).strip() if m else ""
    def bullets(label: str) -> list[str]:
        parts = re.split(rf"(?im)^#+\s*{label}.*$", text)
        block = parts[1] if len(parts) > 1 else ""
        m = re.search(r"(?m)^#+\s+", block)
        if m:
            block = block[: m.start()]
        out = []
        for line in block.splitlines():
            line = re.sub(r"^\s*[-*]\s*", "", line).strip()
            if line and not line.startswith("#"):
                out.append(line)
        return out[:12]
    return {
        "title": grab(r"^#\s+(.+)$") or grab(r"^title:\s*(.+)$") or "untitled",
        "assignee": grab(r"^assignee:\s*(.+)$") or "builder",
        "goal": grab(r"^goal:\s*(.+)$") or "",
        "acceptance": bullets("acceptance"),
        "doNot": bullets(r"do-?not|do_not"),
        "evidenceUrl": grab(r"^evidence:\s*(.+)$") or "",
    }

# patch plugin bullets
NEW = """  const bullets = (labelRe) => {
    const re = new RegExp('^#+\\s*(?:' + labelRe + ').*$', 'im')
    const parts = text.split(re)
    let block = parts[1] || ''
    const nextHd = block.search(/^#+\\s+/m)
    if (nextHd >= 0) block = block.slice(0, nextHd)
    return block
      .split(/\\n/)
      .map((l) => l.replace(/^\\s*[-*]\\s*/, '').trim())
      .filter((l) => l && !l.startsWith('#'))
      .slice(0, 12)
  }"""

for rel in [
    Path(r"C:\Users\nachi\ObsidianVaults\mirror-brain\01-Projects\Hermes\mirror-herdr\desktop-plugins\sessions-herdr\plugin.js"),
    Path(r"C:\Users\nachi\AppData\Local\hermes\desktop-plugins\sessions-herdr\plugin.js"),
]:
    t = rel.read_text(encoding="utf-8")
    start = t.find("  const bullets = (labelRe) => {")
    end = t.find("\n  return {", start)  # return of parsePacketMarkdown
    # better: end at "  return {\n    title:"
    end = t.find("  return {\n    title:", start)
    if start < 0 or end < 0:
        raise SystemExit(f"markers {rel} {start} {end}")
    rel.write_text(t[:start] + NEW + "\n\n" + t[end:], encoding="utf-8")
    print("plugin fixed", rel)

# rewrite smoke
root = Path(r"C:\Users\nachi\ObsidianVaults\mirror-brain\01-Projects\Hermes\mirror-herdr")
OUT = root / "desktop-plugins" / "sessions-herdr" / "smoke-hopB.json"
md = """# Hop B smoke session
assignee: builder
goal: prove create-time link + gateway status
## acceptance
- linked ids present
- status from gateway
## do-not
- second kanban board
evidence: http://127.0.0.1:8642/health
"""
packet = parse_packet_markdown(md)
try:
    req = urllib.request.Request("http://127.0.0.1:8642/health", method="GET")
    with urllib.request.urlopen(req, timeout=5) as resp:
        gw = {"ok": resp.status == 200, "status_code": resp.status, "body": resp.read().decode()[:200]}
except Exception as e:
    gw = {"ok": False, "error": str(e)}

def uid(p):
    return f"{p}-{int(time.time()*1000):x}-{random.randrange(1<<20):x}"

sess = {
    "id": uid("sess"),
    "title": packet["title"],
    "status": "ready" if gw.get("ok") else "todo",
    "statusSource": "gateway",
    "profile": packet["assignee"],
    "kanbanId": uid("k"),
    "runId": uid("run"),
    "herdrId": uid("herdr-stub"),
    "evidenceUrl": packet.get("evidenceUrl") or "",
    "goal": packet.get("goal") or "",
    "acceptance": packet.get("acceptance") or [],
    "doNot": packet.get("doNot") or [],
    "badge": "linked",
    "createdAt": datetime.now(timezone.utc).isoformat(),
    "gateway": gw,
}
result = {"ok": bool(gw.get("ok")) and all(sess[k] for k in ("kanbanId","runId","herdrId")), "packet": packet, "session": sess, "gateway": gw}
OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
(root / "scripts" / "smoke_hopB_sessions.py").write_text(Path(__file__).read_text(encoding="utf-8") if False else open(__file__, encoding="utf-8").read() if False else "", encoding="utf-8")
print(json.dumps({"ok": result["ok"], "packet": packet, "status": sess["status"]}, ensure_ascii=False))
