# sessions-herdr (Hop C)

Hermes Desktop Sessions shell for Herdr-inside-Desktop.

## Install
1. Copy `plugin.js` → `%LOCALAPPDATA%\hermes\desktop-plugins\sessions-herdr\plugin.js`
2. Enable Python backend: `%LOCALAPPDATA%\hermes\plugins\sessions-herdr\` (plugin.yaml + dashboard/plugin_api.py)
3. Restart Hermes Desktop; open **/sessions**

## Hop C behavior
- Create → real `hermes kanban create` → `kanbanId` like `t_…`
- `herdrId` from `herdr session list` (PARTIAL if server stopped)
- Ports strip 8642/9119/8766/9120
- Thin Jev gate (non-blocking)
- Fallback stub ids if backend off

## Smoke
See `smoke-hopC.json` and `scripts/smoke_hopC_sessions.py`.
