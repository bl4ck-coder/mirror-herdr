---
name: ports-health
description: Strip health for Mirror Ops ports 8642/9119/8766/9120 (A4).
---
# ports-health

## Ports
| port | role |
|------|------|
| 8642 | Hermes gateway |
| 9119 | Hermes dashboard |
| 8766 | Evidence hub |
| 9120 | Ops-console (out of Sessions v1 scope) |

## Do
Probe listening + optional HTTP; show strip on Sessions page; never block create on 9120 down.

## Do-not
Assume 9120 required for Sessions v1.
