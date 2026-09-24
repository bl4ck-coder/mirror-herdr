# sessions-herdr (Hop G)

Hermes Desktop Sessions shell for Herdr-inside-Desktop.

## Install
1. Copy `plugin.js` → `%LOCALAPPDATA%\hermes\desktop-plugins\sessions-herdr\plugin.js`
2. Enable Python backend: `%LOCALAPPDATA%\hermes\plugins\sessions-herdr\` (plugin.yaml + dashboard/plugin_api.py)
3. Restart Hermes Desktop; open **/sessions**

## Hop G action pack
On each session row after create:
- Stop / Detach / Eliminar — confirm dialog. Stop hits gateway `/v1/runs/{id}/stop` only if that run is in progress; otherwise Herdr `session stop` only for an owned herdrId. Shared session `default` is never stopped. Detach is refused with a visible reason (CLI has no detach).
- Steer — enabled only for an in-progress gateway run; otherwise visible reason.
- Receipt — vault file, or folder pointer if the row has no receiptPath.
- Evidence — `:8766` (8788 is fleet-bridge, not evidence).
- Focus — UI highlight + LLM/profile from kanban show. Does not focus the shared Herdr agent unless the row stores `herdrAgent`.
- Mesh — one confirmed stub POST. Not on the poll.

## Hop C behavior (still)
- Create → real `hermes kanban create` → `kanbanId` like `t_…`
- `runId` stays empty until gateway has a session id (kanban id is not a run id)
- `herdrId` from `herdr session list` (PARTIAL if server stopped)
- Ports strip 8642/9119/8766/9120
- Thin Jev gate (non-blocking)

## Smoke
`smoke-hopG.json` next to this file. Not a GUI click.
