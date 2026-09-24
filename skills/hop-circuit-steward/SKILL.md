---
name: hop-circuit-steward
description: Mirror Ops hop steward — locked SPEC+PLAN → builder (grok-4.6) → judge (k3) → Sandhi cut. Nous off.
---
# hop-circuit-steward

## Intent
Keep one hop in order. Steward hygiene only — no implement, no cut.

## Do
1. Locked SPEC+PLAN before builder.
2. Builder is grok-4.6. Builder does not approve product done.
3. Judge is k3. Judge does not cut.
4. IMPROVE / must-fix returns to planner — no blind re-build.
5. Sandhi is the hard-neutral cut.
6. Handoff in `Meta/bus/receipts/` (see `handoff-packet-hermes`).
7. Nous OFF on this circuit.

## Do-not
- Nous.
- SOUL.
- Out-of-order implement.
- Product OK from builder or judge.

## Owners
planner, builder, judge, sandhi.
