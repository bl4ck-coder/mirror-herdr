"""sessions-herdr plugin API — Hop H: A4 extras on top of Hop G actions.

Router (SPEC A9): prompt/steer/stop → runId→gateway else herdrId→Herdr;
mesh→Sandhi; receipt/evidence→vault/URL; Eliminar confirms and clears linked
sides that exist.

Safety: never invent a herdrId. Never stop or delete the shared Herdr session
named "default". A kanban task id is not a gateway /v1/runs id — steer/stop
stay disabled with a visible reason until GET /v1/runs/{id} is in-progress.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

PORTS = (8642, 9119, 8766, 9120)
EVIDENCE_PORT = 8766
# Gateway source of truth is GET /health. Bare / may 404 while the gateway is up.
PROBE_PATH = {8642: "/health", 9119: "/", 8766: "/", 9120: "/"}
DASHBOARD_ORIGIN = "http://127.0.0.1:9119"
VAULT = Path(r"C:\Users\nachi\ObsidianVaults\mirror-brain")
FORK = VAULT / "01-Projects" / "Hermes" / "mirror-herdr"
RECEIPTS = VAULT / "Meta" / "bus" / "receipts"
MESH_CONFIG = VAULT / "01-Projects" / "Hermes" / "ops-console" / "config.json"
KANBAN_ID_RE = re.compile(r"^t_[0-9a-fA-F]+$")
_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_S = 5.0


class CreateBody(BaseModel):
    title: str = "untitled"
    assignee: str = "builder"
    goal: str = ""
    acceptance: list[str] = Field(default_factory=list)
    doNot: list[str] = Field(default_factory=list)
    evidenceUrl: str = ""
    markdown: str = ""
    # Smoke only: park the card blocked so a verify create does not dispatch a worker.
    hold: bool = False


class JevGateBody(BaseModel):
    title: str = ""
    goal: str = ""


class SessionRef(BaseModel):
    id: str = ""
    title: str = ""
    kanbanId: str = ""
    runId: str = ""
    herdrId: str = ""
    herdrPartial: bool = False
    receiptPath: str = ""
    evidenceUrl: str = ""
    profile: str = ""
    model: str = ""
    # Owned Herdr agent target (pane id or agent name) stored on the row.
    # Never filled by guessing the shared world-seed agent.
    herdrAgent: str = ""
    goal: str = ""


class ActBody(BaseModel):
    action: str
    confirm: bool = False
    text: str = ""
    session: SessionRef = Field(default_factory=SessionRef)


class ClaimBody(BaseModel):
    kanbanId: str = ""
    confirm: bool = False


class HandoffBody(BaseModel):
    kanbanId: str = ""
    title: str = ""
    goal: str = ""


def _hermes_bin() -> str:
    found = shutil.which("hermes")
    if found:
        return found
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "bin" / "hermes.exe"
    return str(local) if local.is_file() else "hermes"


def _herdr_bin() -> Optional[Path]:
    p = Path(os.environ.get("LOCALAPPDATA", "")) / "Herdr" / "v0.9.0" / "herdr.exe"
    return p if p.is_file() else None


def _load_api_key() -> Optional[str]:
    env = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / ".env"
    if not env.is_file():
        return None
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("API_SERVER_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _redact(text: str) -> str:
    key = _load_api_key() or ""
    out = text or ""
    if key and key in out:
        out = out.replace(key, "[redacted]")
    return out[:400]


def _hermes_env() -> dict[str, str]:
    env = os.environ.copy()
    # Dashboard or a fenced worker must not be blocked from user-initiated kanban clears.
    env.pop("HERMES_DELEGATED_CHILD_CONTEXT", None)
    return env


def _probe_port(port: int) -> dict[str, Any]:
    path = PROBE_PATH.get(port, "/")
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.5):
            listening = True
    except OSError:
        listening = False
    http: Any = None
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            http = resp.status
    except Exception as e:
        http = getattr(e, "code", None) or type(e).__name__
    return {
        "port": port,
        "listening": listening,
        "http": http,
        "path": path,
        "up": http == 200,
    }


def _cached(name: str, loader):
    now = time.time()
    hit = _CACHE.get(name)
    if hit and now - hit[0] < _CACHE_S:
        return hit[1]
    value = loader()
    _CACHE[name] = (now, value)
    return value


def _stub_herdr(herdr_id: Optional[str]) -> bool:
    h = (herdr_id or "").strip()
    if not h:
        return True
    return h.startswith("herdr-stub") or h.startswith("sess-")


def _shared_default(herdr_id: Optional[str]) -> bool:
    return (herdr_id or "").strip().lower() == "default"


def _run_herdr(args: list[str], timeout: int = 15) -> dict[str, Any]:
    exe = _herdr_bin()
    if not exe:
        return {"ok": False, "error": "herdr.exe not found", "stdout": "", "rc": None}
    try:
        proc = subprocess.run(
            [str(exe), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as e:
        return {"ok": False, "error": _redact(str(e)), "stdout": "", "rc": None}
    stdout = proc.stdout or ""
    data: Any = None
    try:
        data = json.loads(stdout) if stdout.strip() else None
    except Exception:
        data = None
    return {
        "ok": proc.returncode == 0,
        "rc": proc.returncode,
        "stdout": stdout[:800],
        "stderr": _redact((proc.stderr or "")[:400]),
        "data": data,
        "error": None if proc.returncode == 0 else _redact((proc.stderr or proc.stdout or "herdr failed")[:300]),
    }


def _herdr_sessions() -> dict[str, Any]:
    def load() -> dict[str, Any]:
        ran = _run_herdr(["session", "list", "--json"])
        data = ran.get("data") if isinstance(ran.get("data"), dict) else {}
        sessions = data.get("sessions") if isinstance(data, dict) else None
        if not isinstance(sessions, list):
            sessions = []
        return {"ok": bool(ran.get("ok")), "sessions": sessions, "error": ran.get("error")}

    return _cached("herdr_sessions", load)


def _herdr_agents() -> dict[str, Any]:
    def load() -> dict[str, Any]:
        ran = _run_herdr(["agent", "list"])
        data = ran.get("data") if isinstance(ran.get("data"), dict) else {}
        result = data.get("result") if isinstance(data, dict) else {}
        agents = result.get("agents") if isinstance(result, dict) else None
        if not isinstance(agents, list):
            agents = []
        thin = []
        for a in agents:
            if not isinstance(a, dict):
                continue
            thin.append(
                {
                    "name": a.get("name"),
                    "agent": a.get("agent"),
                    "status": a.get("agent_status"),
                    "pane_id": a.get("pane_id"),
                    "focused": bool(a.get("focused")),
                    "title": a.get("terminal_title_stripped") or a.get("terminal_title"),
                }
            )
        return {"ok": bool(ran.get("ok")), "agents": thin, "error": ran.get("error")}

    return _cached("herdr_agents", load)


def _match_agent(target: str, agents: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    want = (target or "").strip()
    if not want:
        return None
    for a in agents:
        if want in {str(a.get("name") or ""), str(a.get("pane_id") or ""), str(a.get("agent") or "")}:
            return a
    return None


def _gateway_run(run_id: str) -> dict[str, Any]:
    rid = (run_id or "").strip()
    if not rid:
        return {"exists": False, "reason": "no runId"}
    key = _load_api_key()
    if not key:
        return {"exists": False, "reason": "no API_SERVER_KEY — cannot query gateway run"}
    url = "http://127.0.0.1:8642/v1/runs/" + urllib.parse.quote(rid, safe="")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"exists": False, "reason": "gateway has no /v1/runs/" + rid}
        return {"exists": False, "reason": f"gateway run lookup HTTP {e.code}"}
    except Exception as e:
        return {"exists": False, "reason": "gateway run lookup failed: " + type(e).__name__}
    status = str(data.get("status") or "")
    return {
        "exists": True,
        "status": status or "unknown",
        "accepting_steer": status == "running",
        "reason": None if status == "running" else f"gateway run status={status or 'unknown'}",
    }


def _gateway_post(run_id: str, action: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    key = _load_api_key()
    if not key:
        return {"ok": False, "reason": "no API_SERVER_KEY"}
    url = "http://127.0.0.1:8642/v1/runs/" + urllib.parse.quote(run_id, safe="") + "/" + action
    body = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                data = json.loads(raw) if raw else {}
            except Exception:
                data = {"raw": raw[:200]}
            return {"ok": True, "http": resp.status, "data": data}
    except urllib.error.HTTPError as e:
        detail = _redact(e.read().decode("utf-8", "replace")[:240])
        return {"ok": False, "http": e.code, "reason": f"gateway {action} HTTP {e.code}: {detail}"}
    except Exception as e:
        return {"ok": False, "reason": "gateway " + action + " failed: " + type(e).__name__}


def _kanban_show(kanban_id: str) -> dict[str, Any]:
    kid = (kanban_id or "").strip()
    if not KANBAN_ID_RE.fullmatch(kid):
        return {"ok": False, "reason": "no kanbanId"}
    try:
        proc = subprocess.run(
            [_hermes_bin(), "kanban", "show", kid, "--json"],
            capture_output=True,
            text=True,
            timeout=30,
            env=_hermes_env(),
        )
    except Exception as e:
        return {"ok": False, "reason": _redact(str(e))}
    if proc.returncode != 0:
        return {"ok": False, "reason": _redact((proc.stderr or proc.stdout or "kanban show failed")[:300])}
    try:
        data = json.loads(proc.stdout or "{}")
    except Exception as e:
        return {"ok": False, "reason": f"bad kanban json: {e}"}
    task = data.get("task") if isinstance(data, dict) and isinstance(data.get("task"), dict) else data
    if not isinstance(task, dict):
        task = {}
    return {"ok": True, "task": task}


def _kanban_archive(kanban_id: str) -> dict[str, Any]:
    kid = (kanban_id or "").strip()
    if not KANBAN_ID_RE.fullmatch(kid):
        return {"ok": False, "reason": "no kanbanId to archive"}
    try:
        proc = subprocess.run(
            [_hermes_bin(), "kanban", "archive", kid],
            capture_output=True,
            text=True,
            timeout=40,
            env=_hermes_env(),
        )
    except Exception as e:
        return {"ok": False, "reason": _redact(str(e))}
    text = _redact(((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()[:300])
    if proc.returncode != 0:
        return {"ok": False, "reason": text or f"archive rc={proc.returncode}"}
    return {"ok": True, "reason": text or "archived"}


def _info(session: SessionRef) -> dict[str, Any]:
    profile = (session.profile or "").strip()
    model = (session.model or "").strip()
    model_source = "session" if model else ""
    gateway_session_id = ""
    kanban_status = ""
    show = _kanban_show(session.kanbanId) if session.kanbanId else {"ok": False, "reason": "no kanbanId"}
    if show.get("ok"):
        task = show["task"]
        profile = str(task.get("assignee") or profile or "")
        kanban_status = str(task.get("status") or "")
        if task.get("model_override"):
            model = str(task.get("model_override"))
            model_source = "kanban"
        sid = task.get("session_id")
        if isinstance(sid, str) and sid.strip() and sid.strip() != session.kanbanId:
            gateway_session_id = sid.strip()
    agents = _herdr_agents()
    if not model:
        model_source = model_source or "unavailable"
    return {
        "profile": profile or "unavailable",
        "model": model or "unavailable",
        "modelSource": model_source or "unavailable",
        "llm": model or "unavailable",
        "kanbanStatus": kanban_status or None,
        "gatewaySessionId": gateway_session_id or None,
        "agents": agents.get("agents") or [],
        "agentsError": agents.get("error"),
        "note": "Herdr agent list has no model field. LLM comes from kanban model_override or the row, else unavailable.",
    }


def _evidence(session: SessionRef) -> dict[str, Any]:
    custom = (session.evidenceUrl or "").strip()
    if custom.startswith("http://") or custom.startswith("https://"):
        return {"ok": True, "wired": True, "url": custom, "source": "session", "disabled": False}
    probe = _probe_port(EVIDENCE_PORT)
    up = bool(probe.get("up"))
    return {
        "ok": up,
        "wired": True,
        "url": f"http://127.0.0.1:{EVIDENCE_PORT}/",
        "port": EVIDENCE_PORT,
        "listening": bool(probe.get("listening")),
        "http": probe.get("http"),
        "path": probe.get("path") or "/",
        "up": up,
        "disabled": not up,
        "reason": None if up else f":{EVIDENCE_PORT} evidence hub not up (need HTTP 200)",
        "reconcile": "Evidence hub is :8766. Gateway SoT is GET /health, not bare /.",
    }


def _receipt(session: SessionRef) -> dict[str, Any]:
    raw = (session.receiptPath or "").strip()
    receipts = RECEIPTS.resolve()
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            p = VAULT / raw
        try:
            p = p.resolve()
        except Exception as e:
            return {"ok": False, "disabled": True, "reason": _redact(str(e))}
        if receipts != p and receipts not in p.parents:
            return {"ok": False, "disabled": True, "reason": "receiptPath outside Meta/bus/receipts"}
        if not p.is_file():
            return {"ok": False, "disabled": True, "reason": "receiptPath is not a file"}
        return {"ok": True, "wired": True, "path": str(p), "kind": "file", "disabled": False}
    if receipts.is_dir():
        return {
            "ok": True,
            "wired": True,
            "path": str(receipts),
            "kind": "pointer",
            "disabled": False,
            "reason": "no per-session receiptPath — folder pointer only",
        }
    return {"ok": False, "disabled": True, "wired": False, "reason": "no receiptPath and receipts folder missing"}


def _mesh_configured() -> bool:
    if not MESH_CONFIG.is_file():
        return False
    try:
        cfg = json.loads(MESH_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return False
    url = cfg.get("webhook_url") or cfg.get("webhookUrl")
    key = cfg.get("sender_key") or cfg.get("senderKey")
    return bool(url and key)


def _owned_herdr_reason(herdr_id: str) -> Optional[str]:
    if _stub_herdr(herdr_id):
        return "no real herdrId (missing or stub) — not inventing one"
    if _shared_default(herdr_id):
        return "herdrId is the shared default session — refusing stop/delete"
    sessions = _herdr_sessions().get("sessions") or []
    names = {str(s.get("name")) for s in sessions if isinstance(s, dict)}
    if herdr_id not in names:
        return "herdrId is not in herdr session list"
    return None


def _capabilities(session: SessionRef) -> dict[str, Any]:
    run = _gateway_run(session.runId) if (session.runId or "").strip() else {"exists": False, "reason": "no runId"}
    steer_ok = bool(run.get("exists") and run.get("accepting_steer"))
    stop_gateway = steer_ok
    herdr_block = _owned_herdr_reason(session.herdrId)
    stop_herdr = herdr_block is None
    if stop_gateway:
        stop = {"enabled": True, "reason": "gateway run in progress — stop will POST /v1/runs/{id}/stop"}
    elif stop_herdr:
        stop = {"enabled": True, "reason": "no gateway run; stop will call herdr session stop on owned herdrId"}
    else:
        stop = {
            "enabled": False,
            "reason": (run.get("reason") or "no in-progress gateway run") + "; " + (herdr_block or "no herdr stop"),
        }
    agent = (session.herdrAgent or "").strip()
    agents = _herdr_agents().get("agents") or []
    matched = _match_agent(agent, agents) if agent else None
    if agent and matched:
        prompt = {"enabled": True, "reason": "owned herdrAgent is in the live agent list"}
        focus_herdr = {"enabled": True, "reason": "herdr agent focus on owned target"}
    elif agent and not matched:
        prompt = {"enabled": False, "reason": "herdrAgent is not in the live agent list"}
        focus_herdr = {"enabled": False, "reason": "herdrAgent is not in the live agent list"}
    else:
        prompt = {
            "enabled": False,
            "reason": "no owned herdrAgent on this row — prompt disabled (would hit the shared agent)",
        }
        focus_herdr = {
            "enabled": False,
            "reason": "no owned herdrAgent — UI focus only, not focusing the shared agent",
        }
    info = _info(session)
    evidence = _evidence(session)
    receipt = _receipt(session)
    mesh_on = _mesh_configured()
    eliminar_enabled = bool(KANBAN_ID_RE.fullmatch(session.kanbanId or "")) or stop_herdr
    return {
        "ok": True,
        "hop": "G",
        "info": info,
        "evidence": evidence,
        "receipt": receipt,
        "actions": {
            "stop": stop,
            "detach": {
                "enabled": False,
                "reason": "Herdr v0.9.0 CLI has session list/attach/stop/delete only — no detach. Not a silent no-op.",
            },
            "eliminar": {
                "enabled": eliminar_enabled,
                "reason": (
                    "confirm archives the kanban card if it exists; shared default Herdr session is not deleted"
                    if eliminar_enabled
                    else "nothing owned to clear (no kanbanId, no unique herdrId)"
                ),
            },
            "steer": {
                "enabled": steer_ok,
                "reason": "gateway run accepting steer" if steer_ok else ("steer disabled: " + (run.get("reason") or "not in progress")),
            },
            "prompt": prompt,
            "focus": {
                "enabled": True,
                "reason": "UI focus always; " + focus_herdr["reason"],
                "herdr": focus_herdr,
                "gatewaySessionId": info.get("gatewaySessionId"),
            },
            "receipt": {
                "enabled": bool(receipt.get("ok")),
                "reason": receipt.get("reason") or ("open " + str(receipt.get("kind"))),
            },
            "evidence": {
                "enabled": bool(evidence.get("ok")),
                "reason": evidence.get("reason") or evidence.get("reconcile"),
                "url": evidence.get("url"),
            },
            "mesh": {
                "enabled": mesh_on,
                "reason": "one-shot Sandhi webhook stub (click only, not on poll)" if mesh_on else "webhook config missing",
            },
        },
    }


def _need_confirm(action: str, confirm: bool) -> Optional[dict[str, Any]]:
    if confirm:
        return None
    return {"ok": False, "disabled": False, "wired": False, "reason": "confirm required", "action": action}


def _act_stop(session: SessionRef, confirm: bool) -> dict[str, Any]:
    blocked = _need_confirm("stop", confirm)
    if blocked:
        return blocked
    run = _gateway_run(session.runId) if (session.runId or "").strip() else {"exists": False, "reason": "no runId"}
    if run.get("exists") and run.get("status") == "running":
        posted = _gateway_post(session.runId.strip(), "stop", {})
        return {
            "ok": bool(posted.get("ok")),
            "wired": "gateway",
            "disabled": False,
            "reason": posted.get("reason") or "gateway stop posted",
            "detail": posted.get("data"),
        }
    herdr_block = _owned_herdr_reason(session.herdrId)
    gw_reason = run.get("reason") or "no in-progress gateway run"
    if herdr_block:
        return {
            "ok": False,
            "wired": False,
            "disabled": True,
            "reason": gw_reason + "; " + herdr_block,
        }
    ran = _run_herdr(["session", "stop", session.herdrId.strip(), "--json"])
    return {
        "ok": bool(ran.get("ok")),
        "wired": "herdr",
        "disabled": False,
        "reason": ran.get("error") or "herdr session stop",
    }


def _act_detach(confirm: bool) -> dict[str, Any]:
    blocked = _need_confirm("detach", confirm)
    if blocked:
        blocked["reason"] = "confirm required; detach is not implemented in Herdr CLI"
        return blocked
    return {
        "ok": False,
        "wired": False,
        "disabled": True,
        "reason": "Herdr v0.9.0 CLI has session list/attach/stop/delete only — no detach. Not a silent no-op.",
    }


def _act_eliminar(session: SessionRef, confirm: bool) -> dict[str, Any]:
    blocked = _need_confirm("eliminar", confirm)
    if blocked:
        return blocked
    cleared = {"kanban": False, "herdr": False, "ui": False}
    reasons: list[str] = []
    kid = (session.kanbanId or "").strip()
    if KANBAN_ID_RE.fullmatch(kid):
        arch = _kanban_archive(kid)
        cleared["kanban"] = bool(arch.get("ok"))
        reasons.append(arch.get("reason") or ("archived " + kid))
    else:
        reasons.append("no kanbanId to archive")
    herdr_block = _owned_herdr_reason(session.herdrId)
    if herdr_block:
        reasons.append(herdr_block)
    else:
        stop = _run_herdr(["session", "stop", session.herdrId.strip(), "--json"])
        delete = _run_herdr(["session", "delete", session.herdrId.strip(), "--json"])
        cleared["herdr"] = bool(delete.get("ok"))
        if not delete.get("ok"):
            reasons.append(delete.get("error") or stop.get("error") or "herdr delete failed")
        else:
            reasons.append("herdr session deleted")
    cleared["ui"] = bool(cleared["kanban"] or cleared["herdr"])
    if not cleared["ui"]:
        reasons.append("row kept — no linked side was cleared")
    return {
        "ok": bool(cleared["kanban"] or cleared["herdr"]),
        "wired": True,
        "disabled": False,
        "cleared": cleared,
        "reason": "; ".join(reasons),
        "reasons": reasons,
    }


def _act_steer(session: SessionRef, text: str, confirm: bool) -> dict[str, Any]:
    run = _gateway_run(session.runId) if (session.runId or "").strip() else {"exists": False, "reason": "no runId"}
    if not (run.get("exists") and run.get("accepting_steer")):
        return {
            "ok": False,
            "wired": False,
            "disabled": True,
            "reason": "steer disabled: " + (run.get("reason") or "not an in-progress gateway run"),
        }
    if not (text or "").strip():
        return {"ok": False, "disabled": False, "accepting": True, "reason": "empty steer text"}
    blocked = _need_confirm("steer", confirm)
    if blocked:
        blocked["accepting"] = True
        return blocked
    posted = _gateway_post(session.runId.strip(), "steer", {"input": text.strip()})
    return {
        "ok": bool(posted.get("ok")),
        "wired": "gateway",
        "disabled": False,
        "reason": posted.get("reason") or "steer accepted",
        "detail": posted.get("data"),
    }


def _act_prompt(session: SessionRef, text: str, confirm: bool) -> dict[str, Any]:
    target = (session.herdrAgent or "").strip()
    agents = _herdr_agents().get("agents") or []
    if not target or not _match_agent(target, agents):
        return {
            "ok": False,
            "wired": False,
            "disabled": True,
            "reason": "prompt disabled: no owned herdrAgent in the live list (refusing the shared agent)",
        }
    if not (text or "").strip():
        return {"ok": False, "reason": "empty prompt"}
    blocked = _need_confirm("prompt", confirm)
    if blocked:
        return blocked
    # Herdr wants the text as one argv. Keep it one argument.
    ran = _run_herdr(["agent", "prompt", target, text.strip()], timeout=20)
    return {
        "ok": bool(ran.get("ok")),
        "wired": "herdr",
        "disabled": False,
        "reason": ran.get("error") or "herdr agent prompt submitted",
    }


def _act_focus(session: SessionRef) -> dict[str, Any]:
    info = _info(session)
    focus: dict[str, Any] = {"ui": True, "herdr": False}
    target = (session.herdrAgent or "").strip()
    agents = info.get("agents") or []
    if target and _match_agent(target, agents):
        ran = _run_herdr(["agent", "focus", target])
        focus["herdr"] = bool(ran.get("ok"))
        focus["herdrReason"] = ran.get("error") or "herdr agent focus"
    else:
        focus["herdrReason"] = "no owned herdrAgent — UI focus only, shared agent left alone"
    if info.get("gatewaySessionId"):
        focus["gatewaySessionId"] = info["gatewaySessionId"]
    return {"ok": True, "wired": True, "disabled": False, "focus": focus, "info": info, "reason": focus["herdrReason"]}


def _act_mesh(session: SessionRef, confirm: bool) -> dict[str, Any]:
    blocked = _need_confirm("mesh", confirm)
    if blocked:
        return blocked
    if not MESH_CONFIG.is_file():
        return {"ok": False, "disabled": True, "wired": False, "reason": "webhook config missing"}
    try:
        cfg = json.loads(MESH_CONFIG.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "disabled": True, "reason": "webhook config unreadable: " + type(e).__name__}
    url = cfg.get("webhook_url") or cfg.get("webhookUrl")
    key = cfg.get("sender_key") or cfg.get("senderKey")
    if not url or not key:
        return {"ok": False, "disabled": True, "wired": False, "reason": "webhook config missing url or key"}
    payload = {
        "source": "hermes",
        "kind": "probe",
        "status": "mesh_stub",
        "hop": "G",
        "role": "sessions-herdr",
        "task_id": (session.kanbanId or None),
        "note": "sessions-herdr mesh enqueue stub (not a hop close) title=" + (session.title or "")[:80],
    }
    req = urllib.request.Request(
        str(url),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "X-Automation-Key": str(key),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            code = resp.status
    except urllib.error.HTTPError as e:
        return {"ok": False, "wired": True, "http": e.code, "reason": f"mesh webhook HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "wired": True, "reason": "mesh webhook failed: " + type(e).__name__}
    return {"ok": code == 200, "wired": True, "http": code, "reason": f"mesh stub posted http={code}", "spam": False}


def act(body: ActBody) -> dict[str, Any]:
    action = (body.action or "").strip().lower()
    session = body.session
    if action == "capabilities":
        return _capabilities(session)
    if action == "stop":
        return _act_stop(session, body.confirm)
    if action == "detach":
        return _act_detach(body.confirm)
    if action == "eliminar":
        return _act_eliminar(session, body.confirm)
    if action == "steer":
        return _act_steer(session, body.text, body.confirm)
    if action == "prompt":
        return _act_prompt(session, body.text, body.confirm)
    if action == "focus":
        return _act_focus(session)
    if action == "receipt":
        rec = _receipt(session)
        rec["action"] = "receipt"
        return rec
    if action == "evidence":
        ev = _evidence(session)
        ev["action"] = "evidence"
        return ev
    if action == "mesh":
        return _act_mesh(session, body.confirm)
    if action == "info":
        return {"ok": True, "info": _info(session)}
    return {"ok": False, "disabled": True, "reason": "unknown action: " + action}


@router.get("/ports")
def ports() -> dict[str, Any]:
    """Strip only. Never blocks create. 9120 down is informational."""
    rows = [_probe_port(p) for p in PORTS]
    return {
        "ok": True,
        "ports": rows,
        "labels": {
            "8642": "Hermes gateway",
            "9119": "Hermes dashboard",
            "8766": "Evidence hub",
            "9120": "Ops-console (out of Sessions v1 scope)",
        },
        "evidencePort": EVIDENCE_PORT,
        "gatewayHealthPath": "/health",
        "reconcile": "Evidence hub is :8766. Gateway SoT is GET /health, not bare /.",
    }


@router.get("/herdr")
def herdr_status() -> dict[str, Any]:
    exe = _herdr_bin()
    if not exe:
        return {"ok": False, "error": "herdr.exe not found", "herdrId": None, "partial": True}
    try:
        proc = subprocess.run(
            [str(exe), "session", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        data = json.loads(proc.stdout or "{}")
        sessions = data.get("sessions") or []
        running = [s for s in sessions if s.get("running")]
        pick = running[0] if running else (sessions[0] if sessions else None)
        if not pick:
            return {"ok": False, "partial": True, "herdrId": None, "error": "no herdr sessions", "raw": data}
        return {
            "ok": True,
            "partial": not bool(pick.get("running")),
            "herdrId": pick.get("name"),
            "running": bool(pick.get("running")),
            "socket_path": pick.get("socket_path"),
            "note": None if pick.get("running") else "Herdr server not running — using session name as herdrId (PARTIAL live socket)",
        }
    except Exception as e:
        return {"ok": False, "partial": True, "herdrId": None, "error": str(e)}


@router.post("/create")
def create_session(body: CreateBody) -> dict[str, Any]:
    title = (body.title or "untitled").strip()
    assignee = (body.assignee or "builder").strip()
    parts = [body.goal] if body.goal else []
    if body.acceptance:
        parts.append("acceptance:\n" + "\n".join(f"- {x}" for x in body.acceptance))
    if body.doNot:
        parts.append("do-not:\n" + "\n".join(f"- {x}" for x in body.doNot))
    if body.evidenceUrl:
        parts.append(f"evidence: {body.evidenceUrl}")
    if body.markdown.strip():
        parts.append(body.markdown.strip())
    post = "\n\n".join(p for p in parts if p) or "sessions-herdr create"
    idem = f"sessions-herdr-{assignee}-{title}"[:80]
    cmd = [
        _hermes_bin(),
        "kanban",
        "create",
        title,
        "--assignee",
        assignee,
        "--body",
        post,
        "--json",
        "--idempotency-key",
        idem,
        "--created-by",
        "sessions-herdr",
    ]
    if body.hold:
        cmd.extend(["--initial-status", "blocked"])
    env = _hermes_env()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
    except Exception as e:
        raise HTTPException(500, f"hermes kanban create failed to spawn: {e}") from e
    if proc.returncode != 0:
        raise HTTPException(500, f"hermes kanban create rc={proc.returncode}: {(proc.stderr or proc.stdout)[:500]}")
    try:
        task = json.loads(proc.stdout)
    except Exception as e:
        raise HTTPException(500, f"bad kanban json: {e}: {proc.stdout[:300]}") from e
    kanban_id = task.get("id")
    # Do not stuff the kanban id into runId. Steer/stop need a real gateway /v1/runs id.
    run_id = task.get("session_id") or ""
    herdr = herdr_status()
    herdr_id = herdr.get("herdrId") or f"herdr-stub-{kanban_id}"
    return {
        "ok": True,
        "session": {
            "id": f"sess-{kanban_id}",
            "title": task.get("title") or title,
            "status": task.get("status") or "ready",
            "statusSource": "gateway",
            "profile": task.get("assignee") or assignee,
            "model": task.get("model_override") or "",
            "kanbanId": kanban_id,
            "runId": run_id,
            "herdrId": herdr_id,
            "herdrAgent": "",
            "herdrPartial": bool(herdr.get("partial")),
            "herdrNote": herdr.get("note"),
            "badge": "linked",
            "evidenceUrl": body.evidenceUrl,
            "receiptPath": "",
            "goal": body.goal,
            "acceptance": body.acceptance,
            "doNot": body.doNot,
            "task": task,
        },
        "herdr": herdr,
    }


@router.post("/jev-gate")
def jev_gate(body: JevGateBody) -> dict[str, Any]:
    """Thin non-blocking gate: yes/no readiness for Sessions hop packet."""
    key = _load_api_key()
    if not key:
        return {"ok": False, "error": "no API_SERVER_KEY", "verdict": "skip"}
    prompt = (
        "Jev gate ONLY (yes/no). Sessions hop packet ready to dispatch?\n"
        f"title: {body.title[:200]}\ngoal: {body.goal[:400]}\n"
        "Reply exactly:\nverdict: yes|no\none_line: ...\n"
    )
    payload = json.dumps(
        {
            "model": "default",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 80,
        }
    ).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:8642/p/jev/v1/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode())
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    except Exception as e:
        return {"ok": False, "error": str(e), "verdict": "skip"}
    verdict = "yes" if "verdict: yes" in text.lower() else ("no" if "verdict: no" in text.lower() else "unclear")
    return {"ok": True, "verdict": verdict, "raw": text[:400]}


@router.post("/capabilities")
def capabilities(body: SessionRef) -> dict[str, Any]:
    return _capabilities(body)


@router.post("/act")
def act_route(body: ActBody) -> dict[str, Any]:
    return act(body)


def _deep_link(kanban_id: str) -> str:
    return f"{DASHBOARD_ORIGIN}/api/plugins/kanban/tasks/{kanban_id}"


def _public_task(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": task.get("id"),
        "title": task.get("title"),
        "status": task.get("status"),
        "assignee": task.get("assignee"),
    }


def _session_from_task(task: dict[str, Any]) -> dict[str, Any]:
    kid = str(task.get("id") or "")
    return {
        "id": f"sess-{kid}",
        "title": task.get("title") or kid or "untitled",
        "status": task.get("status") or "ready",
        "statusSource": "gateway",
        "profile": task.get("assignee") or "",
        "model": task.get("model_override") or "",
        "kanbanId": kid,
        "runId": task.get("session_id") or "",
        "herdrId": "",
        "herdrAgent": "",
        "herdrPartial": True,
        "herdrNote": "claim does not invent herdrId",
        "badge": "board",
        "evidenceUrl": "",
        "receiptPath": "",
        "goal": "",
        "deepLink": _deep_link(kid) if kid else "",
    }


def _claim(body: ClaimBody) -> dict[str, Any]:
    """Worker-lock claim. Refuses unless the card is ready — does not steal a running lock."""
    kid = (body.kanbanId or "").strip()
    deep = _deep_link(kid) if KANBAN_ID_RE.fullmatch(kid) else ""
    if not KANBAN_ID_RE.fullmatch(kid):
        return {
            "ok": False,
            "disabled": True,
            "claimed": False,
            "reason": "kanbanId must look like t_<hex>",
            "deep_link": deep,
        }
    show = _kanban_show(kid)
    if not show.get("ok"):
        return {
            "ok": False,
            "disabled": True,
            "claimed": False,
            "reason": show.get("reason") or "kanban show failed",
            "deep_link": deep,
        }
    task = show["task"]
    status = str(task.get("status") or "")
    if not body.confirm:
        return {
            "ok": False,
            "need_confirm": True,
            "claimed": False,
            "reason": "confirm required — hermes kanban claim locks ready→running; dispatcher will not spawn until the lock expires",
            "status": status,
            "deep_link": deep,
            "task": _public_task(task),
        }
    if status != "ready":
        return {
            "ok": False,
            "claimed": False,
            "disabled": True,
            "reason": f"claim refused: status={status} (need ready). Lock not taken.",
            "status": status,
            "deep_link": deep,
            "task": _public_task(task),
        }
    try:
        proc = subprocess.run(
            [_hermes_bin(), "kanban", "claim", kid],
            capture_output=True,
            text=True,
            timeout=40,
            env=_hermes_env(),
        )
    except Exception as e:
        return {"ok": False, "claimed": False, "reason": _redact(str(e)), "deep_link": deep, "status": status}
    text = _redact(((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()[:400])
    if proc.returncode != 0:
        return {
            "ok": False,
            "claimed": False,
            "reason": text or f"claim rc={proc.returncode}",
            "deep_link": deep,
            "status": status,
        }
    show2 = _kanban_show(kid)
    task2 = show2.get("task") if show2.get("ok") and isinstance(show2.get("task"), dict) else task
    return {
        "ok": True,
        "claimed": True,
        "reason": text or "claimed",
        "deep_link": deep,
        "status": str(task2.get("status") or "running"),
        "session": _session_from_task(task2),
        "task": _public_task(task2),
    }


def _kanban_db_path() -> Path:
    env_db = os.environ.get("HERMES_KANBAN_DB")
    if env_db:
        return Path(env_db)
    return Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "kanban.db"


def _duplex_hooks() -> dict[str, str]:
    return {
        "notify": r"%LOCALAPPDATA%\hermes\scripts\hermes-duplex-notify.ps1",
        "hook": r"%LOCALAPPDATA%\hermes\agent-hooks\duplex-kanban-done.py",
        "spec": "01-Projects/Hermes/bridge-duplex/SPEC-bridge-duplex-v1.md",
        "plan": "01-Projects/Hermes/bridge-duplex/PLAN-bridge-duplex-v1.md",
        "kind": "kanban_done",
        "inbox": "Meta/bus/inbox.jsonl → grok-bot:825fb166",
        "webhook_routine": "ops-visual-hermes-bot",
    }


def _duplex(since: Optional[int]) -> dict[str, Any]:
    """Read completed events. Does not POST the webhook — the shell hook owns notify."""
    hooks = _duplex_hooks()
    template = f"{DASHBOARD_ORIGIN}/api/plugins/kanban/tasks/{{task_id}}"
    db = _kanban_db_path()
    if not db.exists():
        return {"ok": False, "reason": "kanban.db missing", "hooks": hooks, "events": [], "deep_link_template": template}
    uri = db.resolve().as_uri() + "?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True, timeout=2)
        con.row_factory = sqlite3.Row
    except Exception as e:
        return {"ok": False, "reason": type(e).__name__, "hooks": hooks, "events": [], "deep_link_template": template}
    try:
        latest = int(con.execute("SELECT COALESCE(MAX(id), 0) FROM task_events").fetchone()[0])
        if since is None:
            return {
                "ok": True,
                "anchored": True,
                "latest_event_id": latest,
                "events": [],
                "hooks": hooks,
                "deep_link_template": template,
                "note": "no backfill — toast fires on later completed events only. This poll does not POST the webhook.",
            }
        rows = con.execute(
            """
            SELECT e.id, e.task_id, e.created_at, e.payload, t.title, t.assignee
            FROM task_events e
            LEFT JOIN tasks t ON t.id = e.task_id
            WHERE e.kind = 'completed' AND e.id > ?
            ORDER BY e.id ASC
            LIMIT 20
            """,
            (int(since),),
        ).fetchall()
    finally:
        con.close()
    events = []
    for r in rows:
        summary = ""
        try:
            payload = json.loads(r["payload"] or "{}")
            summary = str(payload.get("summary") or "")[:200]
        except Exception:
            summary = ""
        tid = str(r["task_id"] or "")
        events.append({
            "event_id": r["id"],
            "source": "hermes",
            "kind": "kanban_done",
            "status": "completed",
            "ts": r["created_at"],
            "task_id": tid,
            "assignee": r["assignee"] or "",
            "title": r["title"] or "",
            "note": summary,
            "deep_link": _deep_link(tid) if tid else "",
            "navigate": "/kanban",
        })
    return {
        "ok": True,
        "anchored": False,
        "latest_event_id": latest,
        "events": events,
        "hooks": hooks,
        "deep_link_template": template,
        "note": "poll does not POST the webhook — duplex-kanban-done.py owns notify",
    }


def _fork_sha() -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(FORK), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception:
        return ""
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def _handoff_text(body: HandoffBody) -> dict[str, Any]:
    kid = (body.kanbanId or "").strip()
    title = (body.title or "").strip() or kid or "session"
    sha = _fork_sha()
    deep = _deep_link(kid) if KANBAN_ID_RE.fullmatch(kid) else ""
    day = time.strftime("%Y-%m-%d")
    text = (
        "---\n"
        "type: handoff-packet\n"
        f"date: {day}\n"
        "from: sessions-herdr\n"
        "to: judge\n"
        "status: pending\n"
        "expires: 2026-09-24\n"
        "---\n\n"
        "# Handoff packet\n\n"
        f"**goal:** {body.goal or title}\n\n"
        "**done:**\n"
        "- copied from Sessions (not a product OK)\n\n"
        "**remaining:**\n"
        "- judge k3, then Sandhi cut\n\n"
        "**context_pointers:**\n"
        f"- kanban: {kid or '(none)'}\n"
        f"- deep_link: {deep or '(none)'}\n"
        f"- fork: 01-Projects/Hermes/mirror-herdr @ {sha or '(uncommitted)'}\n"
        "- spec: 01-Projects/Hermes/SPEC-herdr-inside-desktop-v1.md\n"
        "- duplex: 01-Projects/Hermes/bridge-duplex/SPEC-bridge-duplex-v1.md\n\n"
        "**acceptance:** ports strip shows 8766 for evidence when up; toast or hook pointers; claim or a visible reason.\n\n"
        "**on_reject:** fix A4 only.\n\n"
        "**do-not:** No transcript dump. No keys. No ops-console rebuild. No SOUL. No Nous.\n"
    )
    return {"ok": True, "text": text, "sha": sha, "deep_link": deep, "kanbanId": kid}


def _hop_diff() -> dict[str, Any]:
    try:
        status = subprocess.run(
            ["git", "-C", str(FORK), "status", "-sb"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        logp = subprocess.run(
            ["git", "-C", str(FORK), "log", "-3", "--oneline"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception as e:
        return {"ok": False, "reason": type(e).__name__}
    return {
        "ok": status.returncode == 0,
        "status": (status.stdout or "")[:1500],
        "log": (logp.stdout or "")[:800],
        "note": "read-only. Commit stays with the builder, not this button.",
    }


@router.post("/claim")
def claim(body: ClaimBody) -> dict[str, Any]:
    return _claim(body)


@router.get("/duplex")
def duplex(since: Optional[int] = None) -> dict[str, Any]:
    return _duplex(since)


@router.post("/handoff")
def handoff(body: HandoffBody) -> dict[str, Any]:
    return _handoff_text(body)


@router.get("/diff")
def hop_diff() -> dict[str, Any]:
    return _hop_diff()


@router.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "plugin": "sessions-herdr", "hop": "H", "actions": [
        "stop", "detach", "eliminar", "steer", "prompt", "focus", "receipt", "evidence", "mesh",
        "claim", "duplex", "handoff", "diff",
    ]}
