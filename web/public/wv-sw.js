/* WealthVault's service worker: shows push notifications, even when the site is closed.
 *
 * A push message holds only a type and an id. The text is fetched from WealthVault's own server with the saved sign-in
 * (kept in IndexedDB by src/utils/pushSession.ts), so stock names and amounts never ride on Google's push service.
 * Chrome requires every push to show something, so a plain line is shown whenever the text cannot be fetched.
 */

const DB = 'wv-push'
const STORE = 'session'

function readSession() {
  return new Promise((resolve) => {
    try {
      const open = indexedDB.open(DB, 1)
      open.onupgradeneeded = () => open.result.createObjectStore(STORE)
      open.onerror = () => resolve({})
      open.onsuccess = () => {
        const get = open.result.transaction(STORE, 'readonly').objectStore(STORE).get('session')
        get.onsuccess = () => resolve(get.result || {})
        get.onerror = () => resolve({})
      }
    } catch (e) {
      resolve({})
    }
  })
}

/** 'strategy:NSE:RELIANCE' -> '/strategy?symbol=RELIANCE'; 'holdings' -> '/holdings'; 'overview' -> '/'. */
function pathFor(route) {
  const page = String(route || 'overview').split(':')[0]
  if (page === 'overview') return '/'
  if (['holdings', 'signals', 'momentum', 'strategy', 'brokers', 'account'].indexOf(page) < 0) return '/'
  const stock = String(route).indexOf(':') >= 0 ? String(route).split(':').pop() : ''
  return '/' + page + (stock && (page === 'strategy' || page === 'momentum') ? '?symbol=' + encodeURIComponent(stock) : '')
}

/** The week as a row of bars, from the indexed series the server sends. */
function bars(series) {
  const lo = Math.min.apply(null, series)
  const hi = Math.max.apply(null, series)
  const span = hi - lo || 1
  return series.map((v) => '▁▂▃▄▅▆▇█'.charAt(Math.min(7, Math.floor(((v - lo) / span) * 8)))).join('')
}

async function fetchNote(id, token) {
  const res = await fetch('/api/v1/notifications/' + encodeURIComponent(id), { headers: { Authorization: 'Bearer ' + token } })
  if (!res.ok) throw new Error('status ' + res.status)
  return res.json()
}

function build(note, hide, id, kind) {
  let extra = {}
  try {
    extra = JSON.parse(note.extra || '{}')
  } catch (e) {
    extra = {}
  }
  let body = hide && note.body_masked ? note.body_masked : note.body
  if (Array.isArray(extra.series) && extra.series.length >= 3) body += '\nThe week: ' + bars(extra.series)
  const max = (self.Notification && self.Notification.maxActions) || 2
  const actions = (Array.isArray(extra.actions) ? extra.actions : []).slice(0, Math.min(max, 2)).map((a) => ({ action: a.route, title: a.label }))
  return {
    title: note.title || 'WealthVault',
    options: { body, tag: id, icon: '/icon-192.png', badge: '/icon-192.png', actions, data: { route: note.route || 'overview', kind } },
  }
}

self.addEventListener('push', (event) => {
  let payload = {}
  try {
    payload = event.data ? event.data.json() : {}
  } catch (e) {
    payload = {}
  }
  const data = payload.data || payload
  const id = data.id
  const kind = data.type || ''
  event.waitUntil(
    (async () => {
      const session = await readSession()
      if (id && session.token) {
        try {
          const shown = build(await fetchNote(id, session.token), session.hide !== false, id, kind)
          return self.registration.showNotification(shown.title, shown.options)
        } catch (e) {
          /* fall through to the plain line */
        }
      }
      return self.registration.showNotification('WealthVault', { body: 'Open WealthVault to see the latest.', tag: id || 'wv', icon: '/icon-192.png', data: { route: 'overview', kind } })
    })(),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const route = event.action || (event.notification.data && event.notification.data.route) || 'overview'
  const target = new URL(pathFor(route), self.location.origin).href
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      for (const w of windows) {
        if (w.url.indexOf(self.location.origin) === 0 && 'focus' in w) {
          await w.focus()
          if ('navigate' in w) return w.navigate(target)
          return undefined
        }
      }
      return self.clients.openWindow(target)
    })(),
  )
})
