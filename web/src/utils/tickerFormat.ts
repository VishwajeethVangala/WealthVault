/**
 * Robust ticker and company name formatting for Indian equities and multi-broker feeds.
 */

const KNOWN_TICKER_MAP: Record<string, string> = {
  'SHIPPING CORPORATION OF INDIA': 'SCI',
  'HINDUSTAN CONSTRUCTION COMPANY': 'HCC',
  'GARDEN REACH SHIPBUILDERS': 'GRSE',
  'GARDEN REACH SHIPBUILDERS & ENGINEERS': 'GRSE',
  'PREMIER EXPLOSIVES': 'PREMEXPLN',
  'JINDAL WORLDWIDE': 'JINDWORLD',
  'ZYDUS WELLNESS': 'ZYDUSWELL',
  'NACL INDUSTRIES': 'NACLIND',
  'KELLTON TECH SOLUTIONS': 'KELLTONTEC',
  'KELLTON TECH': 'KELLTONTEC',
  'SHAKTI PUMPS (INDIA)': 'SHAKTIPUMP',
  'SHAKTI PUMPS': 'SHAKTIPUMP',
  'GTL INFRASTRUCTURE': 'GTLINFRA',
  'OLA ELECTRIC MOBILITY': 'OLAELEC',
  'OLA ELECTRIC': 'OLAELEC',
  'TATA MOTORS': 'TATAMOTORS',
  'STATE BANK OF INDIA': 'SBIN',
  'LIFE INSURANCE CORPORATION': 'LICI',
  'PASHUPATI COTSPIN': 'PASHUPATI',
  'IDEAFORGE TECHNOLOGY': 'IDEAFORGE',
  'PARAS DEFENCE AND SPACE TECHNOLOGIES': 'PARAS',
  'PARAS DEFENCE & SPACE TECHNOLOGIES': 'PARAS',
  'PARAS DEFENCE': 'PARAS',
  'BHARAT HEAVY ELECTRICALS': 'BHEL',
  'MAWANA SUGARS': 'MAWANASUG',
  'DIAMOND POWER INFRASTRUCTURE': 'DIACABS',
  'LLOYDS ENGINEERING WORKS': 'LLOYDSENGG',
  'ADANI TOTAL GAS': 'ATGL',
  'ANLON HEALTHCARE': 'ANLON',
  'TRANSFORMERS & RECTIFIERS INDIA': 'TARIL',
  'TRANSFORMERS & RECTIFIERS (INDIA)': 'TARIL',
  'TRANSFORMERS AND RECTIFIERS INDIA': 'TARIL',
  'TRANSFORMERS & RECTIFIERS': 'TARIL',
  'TATA TECHNOLOGIES': 'TATATECH',
  'AZAD ENGINEERING': 'AZAD',
  'UGAR SUGAR WORKS': 'UGARSUGAR',
  'MAGADH SUGAR & ENERGY': 'MAGADSUGAR',
  'MAGADH SUGAR AND ENERGY': 'MAGADSUGAR',
  'DHAMPUR SUGAR MILLS': 'DHAMPURSUG',
  'MOTISONS JEWELLERS': 'MOTISONS',
  'DEE DEVELOPMENT ENGINEERS': 'DEEDEV',
  'SONA BLW PRECISION FORGINGS': 'SONACOMS',
  'IND-SWIFT LABORATORIES': 'INDSWFTLAB',
  'IND SWIFT LABORATORIES': 'INDSWFTLAB',
  'BHARAT BIJLEE': 'BBL',
  'NETWEB TECHNOLOGIES INDIA': 'NETWEB',
  'NETWEB TECHNOLOGIES': 'NETWEB',
  'VA TECH WABAG': 'WABAG',
  'WOCKHARDT': 'WOCKPHARMA',
  'ONE MOBIKWIK SYSTEMS': 'MOBIKWIK',
  'MOBIKWIK': 'MOBIKWIK',
  'KROSS': 'KROSS',
  'CUPID': 'CUPID',
  'ADANI POWER': 'ADANIPOWER',
  'PC JEWELLER': 'PCJEWELLER',
  'GTL': 'GTL',
  'GACM TECHNOLOGIES': 'GATECH',
}

/**
 * Returns a canonical, short uppercase ticker code (e.g. SHAKTIPUMP, OLAELEC).
 */
export function formatTicker(rawSymbol?: string | null, dossierSymbol?: string | null): string {
  if (dossierSymbol && dossierSymbol.trim() && !dossierSymbol.toUpperCase().startsWith('INDS')) {
    return dossierSymbol.replace(/-(BE|EQ|BZ|SM|ST)$/i, '').trim().toUpperCase()
  }

  const s = (rawSymbol || '').trim()
  if (!s) return 'UNKNOWN'

  // Match parenthesized text, e.g. "INDS02405 (Shakti Pumps (India) Ltd)"
  const match = s.match(/\(([^)]+)\)/)
  if (match && match[1]) {
    const inside = match[1].trim()
    const insideUpper = inside.toUpperCase()

    // Check direct static map
    if (KNOWN_TICKER_MAP[insideUpper]) {
      return KNOWN_TICKER_MAP[insideUpper]
    }

    // Strip Ltd/Limited/Pvt
    const cleaned = insideUpper.replace(/\b(LTD|LIMITED|PVT|PRIVATE)\b/gi, '').replace(/\s+/g, ' ').trim()
    if (KNOWN_TICKER_MAP[cleaned]) {
      return KNOWN_TICKER_MAP[cleaned]
    }

    // Check if prefix is a clean ticker (e.g. "MSFT (Microsoft)")
    const prefix = s.slice(0, match.index).trim()
    if (prefix && !prefix.toUpperCase().startsWith('INDS')) {
      const cleanPrefix = prefix.includes(':') ? prefix.split(':').pop() || prefix : prefix
      return cleanPrefix.replace(/-(BE|EQ|BZ|SM|ST)$/i, '').trim().toUpperCase()
    }

    // Fallback: use alphanumeric token of cleaned name
    const token = cleaned.replace(/[^A-Z0-9]/g, '')
    if (token) return token.slice(0, 10)
  }

  // Handle "NSE:OLAELEC" or "MOREPENLAB-BE"
  let clean = s.includes(':') ? s.split(':').pop() || s : s
  clean = clean.replace(/-(BE|EQ|BZ|SM|ST)$/i, '').trim().toUpperCase()

  // If it still starts with INDS, try to check KNOWN_TICKER_MAP
  return clean
}

/**
 * Returns a human-friendly clean company name (e.g. "Shakti Pumps (India) Ltd").
 */
export function formatCompanyName(rawSymbol?: string | null, displayName?: string | null): string {
  if (displayName && displayName.trim()) {
    // If displayName has "(Company Name)", extract inside
    const m = displayName.match(/\(([^)]+)\)/)
    if (m && m[1]) return m[1].trim()
    return displayName.trim()
  }

  const s = (rawSymbol || '').trim()
  if (!s) return ''

  const match = s.match(/\(([^)]+)\)/)
  if (match && match[1]) {
    return match[1].trim()
  }

  let clean = s.includes(':') ? s.split(':').pop() || s : s
  clean = clean.replace(/-(BE|EQ|BZ|SM|ST)$/i, '').trim()
  return clean
}
