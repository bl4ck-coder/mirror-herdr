---
name: herdr-bridge-os
description: Runtime contract for Herdr CLI/socket — session list/attach; UI still owns fork (A11).
---
# herdr-bridge-os

## Intent
Bridge skill for **runtime** Herdr control (`herdr.exe` on Ignacio). UI ownership remains **A11 fork**.

## Commands (thin)
- `herdr session list --json` → herdrId
- `herdr api snapshot` when server running
- `herdr session attach|stop|delete` as needed

## Gap (Hop C)
If Herdr server is stopped, use session **name** as herdrId and mark **PARTIAL**.

## Do-not
Replace Desktop Sessions with ops-console panel.
