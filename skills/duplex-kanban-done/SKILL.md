---
name: duplex-kanban-done
description: A4 duplex toast + kanban_done deep-link. Point at bridge-duplex; do not implement UI.
---
# duplex-kanban-done

## Intent
A4: duplex toast + `kanban_done` deep-link. Point at bridge-duplex. Do not implement UI.

## Do
1. Read locked SPEC: `01-Projects/Hermes/bridge-duplex/SPEC-bridge-duplex-v1.md`.
2. Notify: `%LOCALAPPDATA%\hermes\scripts\hermes-duplex-notify.ps1`.
3. Hook: `%LOCALAPPDATA%\hermes\agent-hooks\duplex-kanban-done.py`.
4. Webhook routine: `ops-visual-hermes-bot`.
5. Backup inbox: `Meta/bus/inbox.jsonl` → `grok-bot:825fb166`.
6. `kind=kanban_done` means card to done/review.
7. Payload min: `source`, `kind`, `status`, `ts`. Optional: `task_id`, `assignee`, `note`.
8. Deep-link the card id. Do not scrape Desktop as truth.

## Do-not
- Rebuild ops-console `:9120`.
- Second gateway.
- Crew bots calling Hermes MCP direct (crew → Sandhi).
- Invent `herdrId`.
