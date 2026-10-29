/**
 * Usage analytics (Google Analytics 4). Nothing is loaded or sent until the person says yes, and it can be turned
 * off again at any time. Events carry no amounts, holdings, emails or names; people are known only by a hashed id.
 */

const MEASUREMENT_ID = 'G-S1EF9MNYLG'
const CONSENT_KEY = 'wv_analytics_consent'

export type Consent = 'granted' | 'denied' | null

type GtagWindow = Window & { dataLayer?: unknown[]; gtag?: (...args: unknown[]) => void; [k: string]: unknown }
const w = window as unknown as GtagWindow

let loaded = false
let userHash: string | null = null

export const getConsent = (): Consent => {
  try {
    const v = localStorage.getItem(CONSENT_KEY)
    return v === 'granted' || v === 'denied' ? v : null
  } catch {
    return null
  }
}

const gtag = (...args: unknown[]) => {
  w.dataLayer = w.dataLayer || []
  w.dataLayer.push(args)
}

const load = () => {
  if (loaded) return
  loaded = true
  w.gtag = gtag
  gtag('js', new Date())
  gtag('config', MEASUREMENT_ID, {
    send_page_view: false, // screens are reported by name, see trackScreen
    allow_google_signals: false,
    allow_ad_personalization_signals: false,
  })
  const s = document.createElement('script')
  s.async = true
  s.src = `https://www.googletagmanager.com/gtag/js?id=${MEASUREMENT_ID}`
  document.head.appendChild(s)
}

const sha256 = async (text: string): Promise<string | null> => {
  try {
    const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))
    return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, '0')).join('')
  } catch {
    return null
  }
}

export const setConsent = (value: 'granted' | 'denied') => {
  try {
    localStorage.setItem(CONSENT_KEY, value)
  } catch {
    /* the choice just will not be remembered */
  }
  w[`ga-disable-${MEASUREMENT_ID}`] = value !== 'granted'
  if (value === 'granted') load()
}

/** Call once at start-up: loads analytics only if the person already agreed. */
export const initAnalytics = () => {
  if (getConsent() === 'granted') {
    w[`ga-disable-${MEASUREMENT_ID}`] = false
    load()
  }
}

/** Identify the signed-in person by a hash of the internal user id, never by email or name. */
export const identify = async (userId: string | null | undefined) => {
  if (!userId) {
    userHash = null
    if (loaded) gtag('set', { user_id: null })
    return
  }
  userHash = (await sha256(`wv:${userId}`))?.slice(0, 32) ?? null
  if (loaded && userHash) gtag('set', { user_id: userHash })
}

export const track = (event: string, params: Record<string, string | number | boolean | null | undefined> = {}) => {
  if (getConsent() !== 'granted' || !loaded) return
  const clean: Record<string, string | number | boolean> = { platform: 'web' }
  Object.entries(params).forEach(([k, v]) => {
    if (v !== null && v !== undefined) clean[k] = v
  })
  gtag('event', event, clean)
}

const SCREENS: Record<string, string> = {
  '/': 'overview',
  '/holdings': 'holdings',
  '/brokers': 'brokers',
  '/signals': 'signals',
  '/momentum': 'momentum',
  '/strategy': 'ath_strategy',
  '/account': 'account',
}

export const screenName = (path: string) => SCREENS[path] ?? 'other'

export const trackScreen = (path: string) => track('screen_view', { screen_name: screenName(path) })

/**
 * What a person typed into a search box, made safe to send: upper-cased, cut to 100 characters, and dropped
 * altogether when it looks like an email address or a long number.
 */
export const cleanSearchTerm = (raw: string): string | null => {
  const t = raw.trim().replace(/\s+/g, ' ').toUpperCase().slice(0, 100)
  if (t.length < 2) return null
  if (/@/.test(t) || /\d{6,}/.test(t.replace(/[\s-]/g, ''))) return null
  return t
}
