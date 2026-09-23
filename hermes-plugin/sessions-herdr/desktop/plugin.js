/**
 * sessions-herdr — Hop C Sessions shell (Herdr-inside-Desktop).
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
    runId: uid('run'),
    herdrId: uid('herdr-stub'),
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

function SessionsPage(props) {
  const storage = props.storage
  const gatewayAtom = useValue(host.state.gateway)
  const [sessions, setSessions] = useState(function () { return storage.get(STORAGE_KEY, []) })
  const [form, setForm] = useState(emptyForm)
  const [gw, setGw] = useState(null)
  const [note, setNote] = useState('')
  const [mode, setMode] = useState('lite')
  const [ports, setPorts] = useState(null)

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
      setNote(
        'REAL kanban=' + sess.kanbanId +
        ' run=' + sess.runId +
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
      setNote('FALLBACK stub ids (backend off): ' + String(e && e.message ? e.message : e))
      host.notify({ kind: 'warning', message: 'sessions-herdr backend off — stub ids' })
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
                children: 'Herdr-inside-Desktop · Hop C · not a second board'
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
                placeholder: '# Title\nassignee: builder\\ngoal: ...\\n## acceptance\\n- ...\\n## do-not\\n- ...\\nevidence: https://...',
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
                children: 'Empty · Create a Session above (real kanbanId via hermes kanban create)'
              })
            : null
        ]
      }),
      jsx('div', {
        className: 'min-h-0 flex-1 space-y-2 overflow-auto',
        children: sessions.map(function (s) {
          return jsxs('div', {
            className: 'rounded border border-(--ui-stroke-secondary) p-2',
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
                children: 'id=' + s.id + ' · kanban=' + s.kanbanId + ' · run=' + s.runId + ' · herdr=' + s.herdrId + (s.herdrPartial ? ' (PARTIAL)' : '')
              }),
              s.goal ? jsx('div', { className: 'mt-1 text-xs text-(--ui-text-tertiary)', children: s.goal }) : null
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
  description: 'Sessions shell Hop C — real hermes kanban create, herdrId, ports strip, thin Jev gate. Not a second board.',
  defaultEnabled: true,
  register(ctx) {
    bindRest(ctx.rest)
    ctx.registerMany([
      {
        id: 'page',
        area: 'routes',
        data: { path: '/sessions' },
        render: function () { return jsx(SessionsPage, { storage: ctx.storage }) }
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
