# UI-VERIFY-CHECKLIST — Sessions (Nacho)

Hermes Desktop is on Ignacio Windows — agents cannot GUI-click it. After runbook §1–3:

1. **Open** Hermes Desktop → sidebar **Sessions** (`/sessions`). Confirm ports strip shows `:8642` / `:9119` / `:8766` (9120 may be down).
2. **Create + link** with title `ui-verify-nacho`, assignee `builder`, short goal. Read the note line: must show `REAL kanban=t_…` and `herdr=…` **without** `(herdr PARTIAL)` and **without** `FALLBACK stub`.
3. **Optional:** in a terminal, `hermes kanban show <that-t_id>` (or `hermes kanban list`) and confirm the task exists with `created_by` / body from Sessions.

Mark: **CHECKLIST-READY** until Nacho ticks the three steps (then GUI-PASS by human).
