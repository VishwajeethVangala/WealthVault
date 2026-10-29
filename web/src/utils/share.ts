/**
 * "Share WealthVault": the device's share sheet where there is one (phones), otherwise the message is copied.
 * The same message is in the Android app (ui/ShareApp.kt). Nothing about the person's portfolio is ever in it, and
 * the link carries a campaign tag so installs that came from a share can be counted.
 */
import { track } from './analytics'

const PLAY_LINK =
  'https://play.google.com/store/apps/details?id=com.vangala.wealthvault&referrer=utm_source%3Dwealthvault_share%26utm_medium%3Dweb'

export const SHARE_MESSAGE =
  'I keep all my stocks, mutual funds and NPS in one place with WealthVault. It reads holdings from my brokers, ' +
  'locks behind my fingerprint, and never shows amounts on the lock screen.\n' +
  `Android: ${PLAY_LINK}\n` +
  'iOS coming soon.'

/** Returns 'shared', 'copied', or 'failed' (and 'cancelled' when the person closes the share sheet). */
export const shareApp = async (from: string): Promise<'shared' | 'copied' | 'cancelled' | 'failed'> => {
  if (typeof navigator.share === 'function') {
    try {
      await navigator.share({ title: 'WealthVault', text: SHARE_MESSAGE })
      track('share_app', { from, method: 'share_sheet' })
      return 'shared'
    } catch (err) {
      if ((err as DOMException)?.name === 'AbortError') return 'cancelled'
      // fall through to copying
    }
  }
  try {
    await navigator.clipboard.writeText(SHARE_MESSAGE)
    track('share_app', { from, method: 'copy' })
    return 'copied'
  } catch {
    return 'failed'
  }
}
