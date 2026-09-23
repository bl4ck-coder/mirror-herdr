"""sessions-herdr plugin API — Hop C: real kanban create, herdrId, ports, thin jev gate."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

PORTS = (8642, 9119, 8766, 9120)


class CreateBody(BaseModel):
    title: str = "untitled"
    assignee: str = "builder"
    goal: str = ""
    acceptance: list[str] = Field(default_factory=list)
    doNot: list[str] = Field(default_factory=list)
    evidenceUrl: str = ""
    markdown: str = ""


class JevGateBody(BaseModel):
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


def _probe_port(port: int) -> dict[str, Any]:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.5):
            listening = True
    except OSError:
        listening = False
    http = None
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            http = resp.status
    except Exception as e:
        http = str(getattr(e, "code", None) or type(e).__name__)
    return {"port": port, "listening": listening, "http": http}


@router.get("/ports")
def ports() -> dict[str, Any]:
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
        # Prefer a running session; else first named (often "default")
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
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except Exception as e:
        raise HTTPException(500, f"hermes kanban create failed to spawn: {e}") from e
    if proc.returncode != 0:
        raise HTTPException(500, f"hermes kanban create rc={proc.returncode}: {(proc.stderr or proc.stdout)[:500]}")
    try:
        task = json.loads(proc.stdout)
    except Exception as e:
        raise HTTPException(500, f"bad kanban json: {e}: {proc.stdout[:300]}") from e
    kanban_id = task.get("id")
    run_id = task.get("session_id") or task.get("id")  # gateway/run pointer; session_id often null until dispatch
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
            "kanbanId": kanban_id,
            "runId": run_id,
            "herdrId": herdr_id,
            "herdrPartial": bool(herdr.get("partial")),
            "herdrNote": herdr.get("note"),
            "badge": "linked",
            "evidenceUrl": body.evidenceUrl,
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


@router.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "plugin": "sessions-herdr", "hop": "C"}
