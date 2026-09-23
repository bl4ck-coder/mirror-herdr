---
name: desktop-sessions-tab
description: Hermes Desktop Sessions surface — routes /sessions, sidebar nav, status chip; not a second board.
---
# desktop-sessions-tab

## Intent
Native Sessions tab inside Hermes Desktop via `HermesPlugin` (`sessions-herdr`).

## Surfaces
- route `/sessions`
- sidebar.nav "Sessions"
- statusBar chip
- packet-lite + markdown shortcut
- ports strip `:8642/:9119/:8766/:9120`

## Install
- Disk: `$HERMES_HOME/desktop-plugins/sessions-herdr/plugin.js`
- Unified: `$HERMES_HOME/plugins/sessions-herdr/{desktop,dashboard}`
- Canonical: `mirror-herdr/desktop-plugins/sessions-herdr/`

## Do-not
Full Superpowers dump; Phase C mount-all; second kanban board UI.
