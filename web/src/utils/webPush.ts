// Browser notifications through Firebase Cloud Messaging: the same server pushes, the same notification text.
// The Firebase pieces load only when the person turns this on (or already had), so they cost nothing otherwise.
import { saveSessionForWorker } from './pushSession'

// Public identifiers by design (they ship in every web app). The VAPID key is the public half of the key pair made in
// Firebase console > Project settings > Cloud Messaging > Web Push certificates; empty means "not set up yet".
const FIREBASE_CONFIG = {
  apiKey: 'AIzaSyBAktp8gdue5yUjAqWp5OAaFiwuFev7-9g',
  authDomain: 'wealthvault-2026.firebaseapp.com',
  projectId: 'wealthvault-2026',
  storageBucket: 'wealthvault-2026.firebasestorage.app',
  messagingSenderId: '180858187533',
  appId: '1:180858187533:web:8c628d76965dec9b6e0a44',
}
export const VAPID_PUBLIC_KEY = 'BGs3KCe9KKaT2sCsCXeAbn1tdhOpxdpPDUdba9IfGXTT1drqqJvtBLeFEUXROKT6HzdjpPMqSvLqjsTWPCKs8z0'

const TOKEN_KEY = 'wv_webpush_token'

export type WebPushState = 'unsupported' | 'unavailable' | 'blocked' | 'off' | 'on'

export const webPushSupported = () =>
  typeof window !== 'undefined' && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window

export function webPushState(): WebPushState {
  if (!webPushSupported()) return 'unsupported'
  if (!VAPID_PUBLIC_KEY) return 'unavailable'
  if (Notification.permission === 'denied') return 'blocked'
  return Notification.permission === 'granted' && localStorage.getItem(TOKEN_KEY) ? 'on' : 'off'
}

const authHeaders = () => ({ 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('wv_token') ?? ''}` })

async function currentToken(): Promise<string> {
  const [{ initializeApp, getApps }, { getMessaging, getToken }] = await Promise.all([import('firebase/app'), import('firebase/messaging')])
  const app = getApps()[0] ?? initializeApp(FIREBASE_CONFIG)
  const registration = await navigator.serviceWorker.register('/wv-sw.js')
  await navigator.serviceWorker.ready
  return getToken(getMessaging(app), { vapidKey: VAPID_PUBLIC_KEY, serviceWorkerRegistration: registration })
}

async function tellServer(path: string, token: string): Promise<void> {
  const res = await fetch(`/api/v1/notifications/${path}`, { method: 'POST', headers: authHeaders(), body: JSON.stringify({ token }) })
  if (!res.ok) throw new Error(`The server refused the browser's notification address (${res.status}).`)
}

/** Asks permission, then registers this browser with the signed-in account. Returns the new state. */
export async function enableWebPush(): Promise<WebPushState> {
  if (webPushState() === 'unsupported' || webPushState() === 'unavailable') return webPushState()
  const permission = await Notification.requestPermission()
  if (permission !== 'granted') return permission === 'denied' ? 'blocked' : 'off'
  await saveSessionForWorker()
  const token = await currentToken()
  await tellServer('devices', token)
  localStorage.setItem(TOKEN_KEY, token)
  return 'on'
}

/** Forgets this browser on the server and here. */
export async function disableWebPush(): Promise<WebPushState> {
  const token = localStorage.getItem(TOKEN_KEY)
  localStorage.removeItem(TOKEN_KEY)
  if (token) {
    try {
      await tellServer('devices/remove', token)
    } catch {
      // the server drops unreachable addresses by itself on the next send
    }
    try {
      const { getMessaging, deleteToken } = await import('firebase/messaging')
      const { getApps } = await import('firebase/app')
      const app = getApps()[0]
      if (app) await deleteToken(getMessaging(app))
    } catch {
      // nothing more to clean up
    }
  }
  return webPushState()
}

/** On sign-out: stop this browser's alerts for the account that is leaving. Call before the sign-in is cleared. */
export async function webPushSignOut(): Promise<void> {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token && localStorage.getItem('wv_token')) {
    try {
      await tellServer('devices/remove', token)
    } catch {
      // see disableWebPush
    }
  }
  localStorage.removeItem(TOKEN_KEY)
}

/** When the app opens: keep the worker's saved sign-in fresh, and re-register if Firebase has rotated this browser's address. */
export async function refreshWebPush(): Promise<void> {
  await saveSessionForWorker()
  if (webPushState() !== 'on') return
  try {
    const token = await currentToken()
    if (token !== localStorage.getItem(TOKEN_KEY)) {
      await tellServer('devices', token)
      localStorage.setItem(TOKEN_KEY, token)
    }
  } catch {
    // try again at the next opening
  }
}
