// What the service worker (public/wv-sw.js) needs to fetch a notification's text while the site is closed: the saved
// sign-in and whether amounts are hidden. Kept in IndexedDB because a service worker cannot read localStorage.
// Imports nothing from the app, so api.ts and the privacy switch can both call it.

const DB = 'wv-push'
const STORE = 'session'

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1)
    req.onupgradeneeded = () => req.result.createObjectStore(STORE)
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

/** Copies the current sign-in and hide-amounts choice for the worker; with no sign-in it clears them. Never throws. */
export async function saveSessionForWorker(): Promise<void> {
  try {
    if (typeof indexedDB === 'undefined') return
    const token = localStorage.getItem('wv_token')
    const db = await open()
    const store = db.transaction(STORE, 'readwrite').objectStore(STORE)
    if (token) store.put({ token, hide: localStorage.getItem('wv_hide_amounts') !== 'false' }, 'session')
    else store.delete('session')
  } catch {
    // no storage: the worker then shows its plain line
  }
}
