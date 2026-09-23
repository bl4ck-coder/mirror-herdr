---
name: session-link-kanban-herdr
description: Create-time link Session → hermes kanbanId + runId + herdrId (A9). Gateway owns status.
---
# session-link-kanban-herdr

## Intent
When a Sessions row is created, mint **real** ids:
- `kanbanId` via `hermes kanban create … --json` (or plugin_api POST `/create`)
- `runId` = task.session_id if present else kanbanId until dispatch
- `herdrId` via `herdr session list --json` (session name); mark PARTIAL if server not running

## Do
1. Prefer backend `plugins/sessions-herdr` `/create`.
2. Persist link on Session object; never invent silent stubs when backend is up.
3. Status always from gateway `:8642/health` / host gateway atom (not local invent).

## Do-not
- Do not treat ops-console as Sessions.
- Do not auto-open full Encuentro.
- Do not SOUL promote.

## Owners
Sessions role / mbops. Judge: k3. Gate: jev (thin yes/no).
