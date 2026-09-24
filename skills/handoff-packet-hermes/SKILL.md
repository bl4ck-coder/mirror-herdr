---
name: handoff-packet-hermes
description: Write/read Meta/bus handoff packets for the hop circuit. Template in receipts/. Not product OK.
---
# handoff-packet-hermes

## Intent
Write and read hop handoff packets under `Meta/bus/receipts/`.

## Do
1. Copy `Meta/bus/receipts/_template-handoff-packet.md`.
2. Example in use: `Meta/bus/receipts/2026-09-23-handoff-herdr-hopE.md`.
3. Frontmatter: `type: handoff-packet`, `date`, `from`, `to`, `status` (`pending`|`accepted`|`rejected`), `expires`.
4. Body fields: goal, done, remaining, context_pointers, acceptance, on_reject, do-not.

## Do-not
- Transcript dump.
- Keys.
- Treat the packet as product OK.
- Vault-commit of `mirror-herdr/` (nested repo).
