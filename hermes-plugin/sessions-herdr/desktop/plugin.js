/**
 * sessions-herdr — Hop G A3 action pack (Herdr-inside-Desktop).
 * Disk: $HERMES_HOME/desktop-plugins/sessions-herdr/plugin.js
 * Backend: $HERMES_HOME/plugins/sessions-herdr/dashboard/plugin_api.py
 * Canonical: mirror-herdr/desktop-plugins/sessions-herdr/
 */
import { cn, haptic, host, Tip, useValue } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx, jsxs, Fragment } from 'react/jsx-runtime'

const ID = 'sessions-herdr'
const STORAGE_KEY = 'sessions'
const POLL_MS = 8000
let rest = null
function bindRest(r) { rest = r }

async function restCreate(packet) {
  if (!rest) throw new Error('sessions-herdr backend off — enable Python plugin sessions-herdr')
  return rest('/create', { method: 'POST', body: packet })
}
async function restPorts() {
  if (!rest) return null
  try { return await rest('/ports') } catch (e) {
    return { ok: false, error: String(e && e.message ? e.message : e) }
  }
}
async function restJevGate(packet) {
  if (!rest) return { ok: false, verdict: 'skip', error: 'backend off' }
  try {
    return await rest('/jev-gate', { method: 'POST', body: { title: packet.title || '', goal: packet.goal || '' } })
  } catch (e) {
    return { ok: false, verdict: 'skip', error: String(e && e.message ? e.message : e) }
  }
}
async function restCapabilities(session) {
  if (!rest) return { ok: false, error: 'backend off' }
  return rest('/capabilities', { method: 'POST', body: sessionRef(session) })
}
async function restAct(action, session, extra) {
  if (!rest) throw new Error('sessions-herdr backend off — actions disabled')
  return rest('/act', {
    method: 'POST',
    body: Object.assign({ action: action, session: sessionRef(session) }, extra || {})
  })
}

function sessionRef(s) {
  s = s || {}
  return {
    id: s.id || '',
    title: s.title || '',
    kanbanId: s.kanbanId || '',
    runId: s.runId || '',
    herdrId: s.herdrId || '',
    herdrPartial: Boolean(s.herdrPartial),
    receiptPath: s.receiptPath || '',
    evidenceUrl: s.evidenceUrl || '',
    profile: s.profile || '',
    model: s.model || '',
    herdrAgent: s.herdrAgent || '',
    goal: s.goal || ''
  }
}

function uid(prefix) {
  return prefix + '-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8)
}

function parsePacketMarkdown(md) {
  const text = String(md || '')
  const grab = (re) => {
    const m = text.match(re)
    return m ? m[1].trim() : ''
  }
  const bullets = (labelRe) => {
    const re = new RegExp('^#+\s*(?:' + labelRe + ').*$', 'im')
    const parts = text.split(re)
    let block = parts[1] || ''
    const nextHd = block.search(/^#+\s+/m)
    if (nextHd >= 0) block = block.slice(0, nextHd)
    return block
      .split(/\n/)
      .map((l) => l.replace(/^\s*[-*]\s*/, '').trim())
      .filter((l) => l && !l.startsWith('#') && !/^evidence:/i.test(l))
      .slice(0, 12)
  }
  return {
    title: grab(/^#\s+(.+)$/m) || grab(/^title:\s*(.+)$/im) || 'untitled',
    assignee: grab(/^assignee:\s*(.+)$/im) || 'builder',
    goal: grab(/^goal:\s*(.+)$/im) || '',
    acceptance: bullets('acceptance'),
    doNot: bullets('do-?not|do_not'),
    evidenceUrl: grab(/^evidence:\s*(.+)$/im) || ''
  }
}

function emptyForm() {
  return {
    title: '',
    assignee: 'builder',
    goal: '',
    acceptanceText: '',
    doNotText: '',
    evidenceUrl: '',
    markdown: ''
  }
}

function formToPacket(form) {
  if (form.markdown && form.markdown.trim()) return parsePacketMarkdown(form.markdown)
  return {
    title: form.title.trim() || 'untitled',
    assignee: form.assignee.trim() || 'builder',
    goal: form.goal.trim(),
    acceptance: form.acceptanceText.split(/\n/).map((l) => l.replace(/^\s*[-*]\s*/, '').trim()).filter(Boolean),
    doNot: form.doNotText.split(/\n/).map((l) => l.replace(/^\s*[-*]\s*/, '').trim()).filter(Boolean),
    evidenceUrl: form.evidenceUrl.trim()
  }
}

function createLinkedSession(packet, gatewaySnap) {
  const id = uid('sess')
  return {
    id,
    title: packet.title,
    status: gatewaySnap && gatewaySnap.ok ? 'ready' : 'todo',
    statusSource: 'gateway',
    profile: packet.assignee,
    model: '',
    kanbanId: uid('k'),
    runId: '',
    herdrId: '',
    herdrAgent: '',
    receiptPath: '',
    evidenceUrl: packet.evidenceUrl || '',
    goal: packet.goal || '',
    acceptance: packet.acceptance || [],
    doNot: packet.doNot || [],
    createdAt: new Date().toISOString(),
    gateway: gatewaySnap || { ok: false, detail: 'unknown' },
    badge: 'linked',
    herdrPartial: true
  }
}

async function probeGatewayStatus() {
  let rpcErr = null
  try {
    if (typeof host !== 'undefined' && host.request) {
      await Promise.race([
        host.request('profiles.list', {}),
        new Promise((_, rej) => setTimeout(() => rej(new Error('rpc-timeout')), 2500))
      ])
    }
  } catch (e) {
    rpcErr = String(e && e.message ? e.message : e)
  }
  let http = null
  try {
    const r = await fetch('http://127.0.0.1:8642/health', { method: 'GET' })
    http = { ok: r.ok, status: r.status, body: await r.text() }
  } catch (e) {
    http = { ok: false, error: String(e && e.message ? e.message : e) }
  }
  const ok = Boolean((http && http.ok) || !rpcErr)
  return {
    ok,
    status: ok ? 'ready' : 'todo',
    detail: http && http.ok ? ('health ' + http.status) : JSON.stringify(http).slice(0, 160),
    rpcOk: !rpcErr,
    rpcErr,
    at: new Date().toISOString()
  }
}

function confirmAction(action, session) {
  const title = (session && session.title) || 'session'
  const kanban = (session && session.kanbanId) || '(sin kanban)'
  const herdr = (session && session.herdrId) || '(sin herdrId)'
  if (action === 'stop') {
    return 'Stop «' + title + '»?\n\nSi hay un run de gateway en curso, se para ese run. Si no, Herdr session stop solo cuando el herdrId es propio.\nNo se para la sesión shared default (' + herdr + ').'
  }
  if (action === 'detach') {
    return 'Detach «' + title + '»?\n\nHerdr v0.9.0 no tiene comando detach. Si confirmás, la acción queda rechazada con motivo visible — no es un no-op silencioso.'
  }
  if (action === 'eliminar') {
    return 'Eliminar «' + title + '»?\n\nArchiva la card kanban ' + kanban + ' si existe.\nNo borra la sesión Herdr shared default (' + herdr + ').\nLa fila se saca solo si un lado linkeado se limpió de verdad.'
  }
  if (action === 'mesh') {
    return 'Encolar un stub mesh a Sandhi para «' + title + '»?\n\nUn solo POST. No se repite en el poll.'
  }
  if (action === 'steer') {
    return 'Steer al run de gateway de «' + title + '»?'
  }
  if (action === 'prompt') {
    return 'Enviar prompt al agente Herdr propio de «' + title + '»?'
  }
  return 'Confirmar ' + action + '?'
}

function ActionPack(props) {
  const session = props.session
  const os = props.os
  const focused = props.focused
  const onFocus = props.onFocus
  const onRemove = props.onRemove
  const onPatch = props.onPatch
  const [cap, setCap] = useState(null)
  const [msg, setMsg] = useState('')
  const [steerText, setSteerText] = useState('')
  const [promptText, setPromptText] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(function () {
    let dead = false
    restCapabilities(session).then(function (c) {
      if (!dead) setCap(c)
    }).catch(function (e) {
      if (!dead) setCap({ ok: false, error: String(e && e.message ? e.message : e) })
    })
    return function () { dead = true }
  }, [session.kanbanId, session.runId, session.herdrId, session.herdrAgent, session.receiptPath, session.evidenceUrl])

  const actions = (cap && cap.actions) || {}
  const info = (cap && cap.info) || {}

  function reasonFor(name) {
    const row = actions[name]
    if (!row) return rest ? '' : 'backend off — acción deshabilitada'
    if (row.enabled) return ''
    return row.reason || 'disabled'
  }

  async function run(action, extra) {
    if (busy) return
    if (action === 'stop' || action === 'detach' || action === 'eliminar' || action === 'mesh' || action === 'steer' || action === 'prompt') {
      if (!window.confirm(confirmAction(action, session))) {
        setMsg(action + ': cancelado')
        return
      }
    }
    setBusy(true)
    setMsg(action + '…')
    try {
      const res = await restAct(action, session, extra)
      const reason = (res && res.reason) || (res && res.error) || (res && res.ok ? 'ok' : 'sin motivo')
      setMsg(action + ': ' + reason)
      if (action === 'focus' && res && res.info && onPatch) {
        onPatch({ profile: res.info.profile, model: res.info.model })
      }
      if (action === 'focus' && res && res.focus && res.focus.gatewaySessionId && host.openSession) {
        host.openSession(res.focus.gatewaySessionId, { profile: (res.info && res.info.profile) || session.profile })
      }
      if (action === 'receipt' && res && res.path && os && os.revealPath) {
        const opened = await os.revealPath(res.path)
        setMsg('receipt: ' + reason + (opened ? '' : ' (revealPath no disponible — path arriba)'))
      }
      if (action === 'evidence' && res && res.url && os && os.openExternal) {
        const opened = await os.openExternal(res.url)
        setMsg('evidence: ' + (res.url) + (opened ? '' : ' (openExternal no disponible)'))
      }
      if (action === 'eliminar' && res && res.cleared && res.cleared.ui && onRemove) {
        onRemove(session.id)
      }
      if (action !== 'receipt' && action !== 'evidence') {
        restCapabilities(session).then(setCap).catch(function () {})
      }
    } catch (e) {
      setMsg(action + ': ' + String(e && e.message ? e.message : e))
    } finally {
      setBusy(false)
    }
  }

  const btn = 'rounded border border-(--ui-stroke-secondary) px-1.5 py-0.5 text-[0.7rem] text-foreground'
  const off = ' opacity-60'
  function Btn(p) {
    const why = reasonFor(p.name)
    return jsx('button', {
      type: 'button',
      className: btn + (why && p.name !== 'detach' && p.name !== 'stop' && p.name !== 'eliminar' ? off : ''),
      title: why || (actions[p.name] && actions[p.name].reason) || p.name,
      disabled: busy,
      onClick: p.onClick,
      children: p.label
    })
  }

  return jsxs('div', {
    className: 'mt-2 space-y-1',
    children: [
      jsx('div', {
        className: 'text-[0.7rem] text-(--ui-text-tertiary)',
        children: 'LLM ' + (info.llm || info.model || '…') + ' · profile ' + (info.profile || session.profile || '…')
          + (info.modelSource ? ' (' + info.modelSource + ')' : '')
          + (focused ? ' · focused' : '')
      }),
      jsxs('div', {
        className: 'flex flex-wrap gap-1',
        children: [
          jsx(Btn, { name: 'focus', label: 'Focus', onClick: function () { onFocus(session.id); run('focus') } }),
          jsx(Btn, { name: 'stop', label: 'Stop', onClick: function () { run('stop', { confirm: true }) } }),
          jsx(Btn, { name: 'detach', label: 'Detach', onClick: function () { run('detach', { confirm: true }) } }),
          jsx(Btn, { name: 'eliminar', label: 'Eliminar', onClick: function () { run('eliminar', { confirm: true }) } }),
          jsx(Btn, { name: 'receipt', label: 'Receipt', onClick: function () { run('receipt') } }),
          jsx(Btn, { name: 'evidence', label: 'Evidence', onClick: function () { run('evidence') } }),
          jsx(Btn, { name: 'mesh', label: 'Mesh', onClick: function () { run('mesh', { confirm: true }) } })
        ]
      }),
      jsx('div', {
        className: 'text-[0.65rem] text-(--ui-text-quaternary)',
        children: [
          reasonFor('stop') ? ('Stop — ' + reasonFor('stop')) : null,
          reasonFor('detach') ? ('Detach — ' + reasonFor('detach')) : null,
          reasonFor('steer') ? ('Steer — ' + reasonFor('steer')) : null,
          reasonFor('prompt') ? ('Prompt — ' + reasonFor('prompt')) : null
        ].filter(Boolean).join(' · ') || (cap ? 'action pack listo' : 'cargando acciones…')
      }),
      jsxs('div', {
        className: 'flex gap-1',
        children: [
          jsx('input', {
            className: 'min-w-0 flex-1 rounded border border-(--ui-stroke-secondary) bg-transparent px-1.5 py-0.5 text-[0.7rem]',
            placeholder: actions.steer && actions.steer.enabled ? 'steer al run en curso' : 'steer deshabilitado',
            value: steerText,
            onChange: function (e) { setSteerText(e.target.value) }
          }),
          jsx(Btn, {
            name: 'steer',
            label: 'Steer',
            onClick: function () { run('steer', { confirm: true, text: steerText }) }
          })
        ]
      }),
      jsxs('div', {
        className: 'flex gap-1',
        children: [
          jsx('input', {
            className: 'min-w-0 flex-1 rounded border border-(--ui-stroke-secondary) bg-transparent px-1.5 py-0.5 text-[0.7rem]',
            placeholder: actions.prompt && actions.prompt.enabled ? 'prompt al agente propio' : 'prompt deshabilitado',
            value: promptText,
            onChange: function (e) { setPromptText(e.target.value) }
          }),
          jsx(Btn, {
            name: 'prompt',
            label: 'Prompt',
            onClick: function () { run('prompt', { confirm: true, text: promptText }) }
          })
        ]
      }),
      msg ? jsx('div', { className: 'text-[0.7rem] text-(--ui-text-tertiary)', children: msg }) : null
    ]
  })
}

function SessionsPage(props) {
  const storage = props.storage
  const os = props.os
  const gatewayAtom = useValue(host.state.gateway)
  const [sessions, setSessions] = useState(function () { return storage.get(STORAGE_KEY, []) })
  const [form, setForm] = useState(emptyForm)
  const [gw, setGw] = useState(null)
  const [note, setNote] = useState('')
  const [mode, setMode] = useState('lite')
  const [ports, setPorts] = useState(null)
  const [focusedId, setFocusedId] = useState('')

  function persist(next) {
    setSessions(next)
    storage.set(STORAGE_KEY, next)
  }

  async function refreshGatewayStatuses() {
    const snap = await probeGatewayStatus()
    setGw(snap)
    setSessions(function (prev) {
      const next = prev.map(function (s) {
        return Object.assign({}, s, {
          status: snap.status,
          gateway: snap,
          statusSource: 'gateway'
        })
      })
      storage.set(STORAGE_KEY, next)
      return next
    })
  }

  useEffect(function () {
    refreshGatewayStatuses()
    restPorts().then(setPorts)
    const t = setInterval(function () {
      refreshGatewayStatuses()
      restPorts().then(setPorts)
    }, POLL_MS)
    return function () { clearInterval(t) }
  }, [])

  async function onCreate() {
    const packet = formToPacket(form)
    setNote('creating...')
    try {
      const res = await restCreate(packet)
      const sess = res.session
      persist([sess].concat(sessions))
      setForm(emptyForm())
      setFocusedId(sess.id)
      setNote(
        'REAL kanban=' + sess.kanbanId +
        ' run=' + (sess.runId || '(none)') +
        ' herdr=' + sess.herdrId +
        (sess.herdrPartial ? ' (herdr PARTIAL)' : '')
      )
      haptic('tap')
      host.notify({ kind: 'info', message: 'Session linked: ' + sess.title })
      restJevGate(packet).then(function (g) {
        if (g && g.verdict) {
          setNote(function (n) { return n + ' | jev:' + g.verdict })
        }
      })
    } catch (e) {
      const sess = createLinkedSession(packet, gw)
      persist([sess].concat(sessions))
      setForm(emptyForm())
      setNote('FALLBACK sin ids reales (backend off): ' + String(e && e.message ? e.message : e))
      host.notify({ kind: 'warning', message: 'sessions-herdr backend off — sin herdrId inventado' })
    }
  }

  const inputCls = 'mb-1 w-full rounded border border-(--ui-stroke-secondary) bg-transparent px-2 py-1 text-xs'
  const taCls = 'mb-1 w-full rounded border border-(--ui-stroke-secondary) bg-transparent p-2 text-xs'
  const portRows = (ports && ports.ports)
    ? ports.ports
    : [8642, 9119, 8766, 9120].map(function (p) { return { port: p, listening: null } })

  return jsxs('div', {
    className: 'flex h-full min-h-0 flex-col gap-3 p-3 text-sm text-(--ui-text-secondary)',
    children: [
      jsxs('div', {
        className: 'flex items-baseline justify-between gap-2',
        children: [
          jsxs('div', {
            children: [
              jsx('div', { className: 'text-base text-foreground', children: 'Sessions' }),
              jsx('div', {
                className: 'text-(--ui-text-tertiary)',
                children: 'Herdr-inside-Desktop · Hop G action pack · not a second board'
              })
            ]
          }),
          jsx('div', {
            className: 'text-(--ui-text-quaternary)',
            children: 'gateway atom: ' + String(gatewayAtom) + ' · probe: ' + (gw ? (gw.ok ? 'up' : 'down') : '...') + ' (' + (gw ? gw.status : '') + ')'
          })
        ]
      }),
      jsx('div', {
        className: 'flex flex-wrap gap-2 text-[0.7rem] text-(--ui-text-quaternary)',
        children: portRows.map(function (row) {
          const lab = (ports && ports.labels && ports.labels[String(row.port)]) || ''
          const st = row.listening === true ? 'up' : (row.listening === false ? 'down' : '?')
          return jsx('span', {
            className: 'rounded border border-(--ui-stroke-secondary) px-1.5 py-0.5',
            children: ':' + row.port + ' ' + st + (lab ? ' ' + lab : '')
          }, row.port)
        })
      }),
      ports && ports.reconcile
        ? jsx('div', { className: 'text-[0.65rem] text-(--ui-text-quaternary)', children: ports.reconcile })
        : null,
      jsxs('div', {
        className: 'rounded-lg border border-(--ui-stroke-secondary) p-3',
        children: [
          jsxs('div', {
            className: 'mb-2 flex gap-2',
            children: [
              jsx('button', {
                type: 'button',
                className: cn('px-2 py-1 text-xs', mode === 'lite' && 'text-foreground underline'),
                onClick: function () { setMode('lite') },
                children: 'packet-lite'
              }),
              jsx('button', {
                type: 'button',
                className: cn('px-2 py-1 text-xs', mode === 'markdown' && 'text-foreground underline'),
                onClick: function () { setMode('markdown') },
                children: 'markdown shortcut'
              })
            ]
          }),
          mode === 'markdown'
            ? jsx('textarea', {
                className: taCls + ' h-28',
                placeholder: '# Title\nassignee: builder\ngoal: ...\n## acceptance\n- ...\n## do-not\n- ...\nevidence: https://...',
                value: form.markdown,
                onChange: function (e) { setForm(Object.assign({}, form, { markdown: e.target.value })) }
              })
            : jsxs(Fragment, {
                children: [
                  jsx('input', { className: inputCls, placeholder: 'title', value: form.title, onChange: function (e) { setForm(Object.assign({}, form, { title: e.target.value })) } }),
                  jsx('input', { className: inputCls, placeholder: 'assignee', value: form.assignee, onChange: function (e) { setForm(Object.assign({}, form, { assignee: e.target.value })) } }),
                  jsx('input', { className: inputCls, placeholder: 'goal', value: form.goal, onChange: function (e) { setForm(Object.assign({}, form, { goal: e.target.value })) } }),
                  jsx('textarea', { className: taCls + ' h-14', placeholder: 'acceptance bullets', value: form.acceptanceText, onChange: function (e) { setForm(Object.assign({}, form, { acceptanceText: e.target.value })) } }),
                  jsx('textarea', { className: taCls + ' h-14', placeholder: 'do-not bullets', value: form.doNotText, onChange: function (e) { setForm(Object.assign({}, form, { doNotText: e.target.value })) } }),
                  jsx('input', { className: inputCls, placeholder: 'evidence URL', value: form.evidenceUrl, onChange: function (e) { setForm(Object.assign({}, form, { evidenceUrl: e.target.value })) } })
                ]
              }),
          jsxs('div', {
            className: 'flex items-center gap-2',
            children: [
              jsx('button', {
                type: 'button',
                className: 'rounded bg-(--chrome-action-hover) px-3 py-1 text-xs text-foreground',
                onClick: onCreate,
                children: 'Create + link'
              }),
              note ? jsx('span', { className: 'text-(--ui-text-quaternary) text-xs', children: note }) : null
            ]
          }),
          sessions.length === 0
            ? jsx('div', {
                className: 'mt-3 text-center text-(--ui-text-tertiary)',
                children: 'Empty · Create a Session above — the action pack appears on the row'
              })
            : null
        ]
      }),
      jsx('div', {
        className: 'min-h-0 flex-1 space-y-2 overflow-auto',
        children: sessions.map(function (s) {
          return jsxs('div', {
            className: 'rounded border p-2 ' + (focusedId === s.id ? 'border-foreground' : 'border-(--ui-stroke-secondary)'),
            children: [
              jsxs('div', {
                className: 'flex justify-between gap-2',
                children: [
                  jsx('div', { className: 'text-foreground', children: s.title }),
                  jsx('div', { className: 'text-xs text-(--ui-text-quaternary)', children: s.badge + ' · status=' + s.status + ' (gateway)' })
                ]
              }),
              jsx('div', {
                className: 'mt-1 text-[0.7rem] text-(--ui-text-quaternary)',
                children: 'id=' + s.id + ' · kanban=' + s.kanbanId + ' · run=' + (s.runId || '(none)') + ' · herdr=' + (s.herdrId || '(none)') + (s.herdrPartial ? ' (PARTIAL)' : '')
              }),
              s.goal ? jsx('div', { className: 'mt-1 text-xs text-(--ui-text-tertiary)', children: s.goal }) : null,
              jsx(ActionPack, {
                session: s,
                os: os,
                focused: focusedId === s.id,
                onFocus: setFocusedId,
                onRemove: function (id) {
                  setSessions(function (prev) {
                    const next = prev.filter(function (row) { return row.id !== id })
                    storage.set(STORAGE_KEY, next)
                    return next
                  })
                },
                onPatch: function (patch) {
                  setSessions(function (prev) {
                    const next = prev.map(function (row) {
                      return row.id === s.id ? Object.assign({}, row, patch) : row
                    })
                    storage.set(STORAGE_KEY, next)
                    return next
                  })
                }
              })
            ]
          }, s.id)
        })
      })
    ]
  })
}

export default {
  id: ID,
  name: 'Sessions (Herdr)',
  description: 'Sessions shell Hop G — A3 action pack (stop/detach/eliminar/steer/receipt/evidence/focus/mesh). Not a second board.',
  defaultEnabled: true,
  register(ctx) {
    bindRest(ctx.rest)
    ctx.registerMany([
      {
        id: 'page',
        area: 'routes',
        data: { path: '/sessions' },
        render: function () { return jsx(SessionsPage, { storage: ctx.storage, os: ctx.os }) }
      },
      {
        id: 'nav',
        area: 'sidebar.nav',
        order: 45,
        data: { codicon: 'comment-discussion', label: 'Sessions', path: '/sessions' }
      },
      {
        id: 'chip',
        area: 'statusBar.right',
        order: 120,
        render: function () {
          return jsx(Tip, {
            label: 'Sessions — Herdr-inside-Desktop',
            children: jsx('button', {
              type: 'button',
              className: cn(
                'inline-flex h-full items-center px-1.5 text-[0.6875rem]',
                'text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground'
              ),
              onClick: function () { host.navigate('/sessions') },
              children: 'sessions'
            })
          })
        }
      }
    ])
  }
}
