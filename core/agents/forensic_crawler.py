"""Zero-Cost, Multi-Source Forensic Intelligence Crawler.

Gathers free public news, corporate filings, balance sheet financials, and market beta
decomposition without requiring any paid subscriptions or external API keys.

Sources:
- Google News Real-Time RSS (zero-cost, no auth, real-time headlines & sentiment)
- Screener.in Public Company Ratios & Results (free, transparent quarterly financial statements)
- Yahoo Finance / Kite / Groww public indices for Nifty 50 market beta comparison
"""

import asyncio
import logging
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from core.agents.models import (
    FundamentalVitals,
    InvestigationDossier,
    MoveCausality,
    NewsCatalyst,
)

logger = logging.getLogger("wealthvault.agents.forensic_crawler")

# Caching to avoid redundant network calls (TTL seconds)
_NEWS_CACHE: Dict[str, Tuple[float, List[NewsCatalyst]]] = {}
_FUNDAMENTALS_CACHE: Dict[str, Tuple[float, FundamentalVitals]] = {}
_MOMENTUM_CACHE: Dict[str, Tuple[float, Optional[str], Optional[int], Optional[int]]] = {}

NEWS_CACHE_TTL = 3600.0        # 1 hour
FUNDAMENTALS_CACHE_TTL = 14400.0  # 4 hours

# Concurrency semaphore to avoid overwhelming public free endpoints
_CRAWLER_SEMAPHORE = asyncio.Semaphore(3)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# Known ticker mappings for INDmoney Indian stocks to ensure 100% precision
_IND_TICKER_MAP = {
    "SHIPPING CORPORATION OF INDIA": "SCI",
    "SHIPPING CORPORATION OF INDIA LTD": "SCI",
    "HINDUSTAN CONSTRUCTION COMPANY": "HCC",
    "HINDUSTAN CONSTRUCTION COMPANY LTD": "HCC",
    "GARDEN REACH SHIPBUILDERS": "GRSE",
    "GARDEN REACH SHIPBUILDERS & ENGINEERS": "GRSE",
    "GARDEN REACH SHIPBUILDERS & ENGINEERS LTD": "GRSE",
    "PREMIER EXPLOSIVES LTD": "PREMEXPLN",
    "PREMIER EXPLOSIVES": "PREMEXPLN",
    "JINDAL WORLDWIDE LTD": "JINDWORLD",
    "JINDAL WORLDWIDE": "JINDWORLD",
    "ZYDUS WELLNESS LTD": "ZYDUSWELL",
    "ZYDUS WELLNESS": "ZYDUSWELL",
    "NACL INDUSTRIES LTD": "NACLIND",
    "NACL INDUSTRIES": "NACLIND",
    "KELLTON TECH SOLUTIONS LTD": "KELLTONTEC",
    "KELLTON TECH SOLUTIONS": "KELLTONTEC",
    "SHAKTI PUMPS (INDIA) LTD": "SHAKTIPUMP",
    "SHAKTI PUMPS": "SHAKTIPUMP",
    "GTL INFRASTRUCTURE LTD": "GTLINFRA",
    "GTL INFRASTRUCTURE": "GTLINFRA",
    "OLA ELECTRIC MOBILITY LTD": "OLAELEC",
    "OLA ELECTRIC MOBILITY": "OLAELEC",
    "OLA ELECTRIC": "OLAELEC",
    "OLA ELECTRIC MOBILITY LTD PARTLY PAIDUP": "OLAPP",
    "OLA ELECTRIC MOBILITY PARTLY PAIDUP": "OLAPP",
    "TATA MOTORS LTD": "TATAMOTORS",
    "TATA MOTORS": "TATAMOTORS",
    "STATE BANK OF INDIA": "SBIN",
    "LIFE INSURANCE CORPORATION": "LICI",
    "LIFE INSURANCE CORPORATION OF INDIA": "LICI",
    "PASHUPATI COTSPIN LTD": "PASHUPATI",
    "PASHUPATI COTSPIN": "PASHUPATI",
    "IDEAFORGE TECHNOLOGY LTD": "IDEAFORGE",
    "IDEAFORGE TECHNOLOGY": "IDEAFORGE",
    "PARAS DEFENCE AND SPACE TECHNOLOGIES LTD": "PARAS",
    "PARAS DEFENCE AND SPACE TECHNOLOGIES": "PARAS",
    "PARAS DEFENCE & SPACE TECHNOLOGIES LTD": "PARAS",
    "PARAS DEFENCE & SPACE TECHNOLOGIES": "PARAS",
    "PARAS DEFENCE": "PARAS",
    "BHARAT HEAVY ELECTRICALS LTD": "BHEL",
    "BHARAT HEAVY ELECTRICALS": "BHEL",
    "MAWANA SUGARS LTD": "MAWANASUG",
    "MAWANA SUGARS": "MAWANASUG",
    "DIAMOND POWER INFRASTRUCTURE LTD": "DIACABS",
    "DIAMOND POWER INFRASTRUCTURE": "DIACABS",
    "LLOYDS ENGINEERING WORKS LTD": "LLOYDSENGG",
    "LLOYDS ENGINEERING WORKS": "LLOYDSENGG",
    "ADANI TOTAL GAS LTD": "ATGL",
    "ADANI TOTAL GAS": "ATGL",
    "ANLON HEALTHCARE LTD": "ANLON",
    "ANLON HEALTHCARE": "ANLON",
    "TRANSFORMERS & RECTIFIERS INDIA LTD": "TARIL",
    "TRANSFORMERS & RECTIFIERS INDIA": "TARIL",
    "TRANSFORMERS & RECTIFIERS (INDIA) LTD": "TARIL",
    "TRANSFORMERS AND RECTIFIERS INDIA LTD": "TARIL",
    "TRANSFORMERS AND RECTIFIERS INDIA": "TARIL",
    "TATA TECHNOLOGIES LTD": "TATATECH",
    "TATA TECHNOLOGIES": "TATATECH",
    "AZAD ENGINEERING LTD": "AZAD",
    "AZAD ENGINEERING": "AZAD",
    "UGAR SUGAR WORKS LTD": "UGARSUGAR",
    "UGAR SUGAR WORKS": "UGARSUGAR",
    "MAGADH SUGAR & ENERGY LTD": "MAGADSUGAR",
    "MAGADH SUGAR & ENERGY": "MAGADSUGAR",
    "MAGADH SUGAR AND ENERGY LTD": "MAGADSUGAR",
    "MAGADH SUGAR AND ENERGY": "MAGADSUGAR",
    "DHAMPUR SUGAR MILLS LTD": "DHAMPURSUG",
    "DHAMPUR SUGAR MILLS": "DHAMPURSUG",
    "MOTISONS JEWELLERS LTD": "MOTISONS",
    "MOTISONS JEWELLERS": "MOTISONS",
    "DEE DEVELOPMENT ENGINEERS LTD": "DEEDEV",
    "DEE DEVELOPMENT ENGINEERS": "DEEDEV",
    "SONA BLW PRECISION FORGINGS LTD": "SONACOMS",
    "SONA BLW PRECISION FORGINGS": "SONACOMS",
    "IND-SWIFT LABORATORIES LTD": "INDSWFTLAB",
    "IND-SWIFT LABORATORIES": "INDSWFTLAB",
    "IND SWIFT LABORATORIES LTD": "INDSWFTLAB",
    "IND SWIFT LABORATORIES": "INDSWFTLAB",
    "BHARAT BIJLEE LTD": "BBL",
    "BHARAT BIJLEE": "BBL",
    "NETWEB TECHNOLOGIES INDIA LTD": "NETWEB",
    "NETWEB TECHNOLOGIES INDIA": "NETWEB",
    "NETWEB TECHNOLOGIES": "NETWEB",
    "VA TECH WABAG LTD": "WABAG",
    "VA TECH WABAG": "WABAG",
    "WOCKHARDT LTD": "WOCKPHARMA",
    "WOCKHARDT": "WOCKPHARMA",
    "ONE MOBIKWIK SYSTEMS LTD": "MOBIKWIK",
    "ONE MOBIKWIK SYSTEMS": "MOBIKWIK",
    "MOBIKWIK": "MOBIKWIK",
    "KROSS LTD": "KROSS",
    "KROSS": "KROSS",
    "CUPID LTD": "CUPID",
    "CUPID": "CUPID",
    "ADANI POWER LTD": "ADANIPOWER",
    "ADANI POWER": "ADANIPOWER",
    "PC JEWELLER LTD": "PCJEWELLER",
    "PC JEWELLER": "PCJEWELLER",
    "GTL LTD": "GTL",
    "GTL": "GTL",
    "GACM TECHNOLOGIES LTD": "GATECH",
    "GACM TECHNOLOGIES": "GATECH",
}


def clean_symbol(symbol: str) -> str:
    """Normalize exchange symbols to pure ticker codes.
    
    Examples:
        'NSE:OLAELEC' -> 'OLAELEC'
        'BSE:TATAMOTORS' -> 'TATAMOTORS'
        'MOREPENLAB-BE' -> 'MOREPENLAB'
        'INDS02425 (Shipping Corporation of India Ltd)' -> 'SCI'
    """
    s = (symbol or "").strip()
    match = re.search(r"\(([^)]+)\)", s)
    if match:
        name = match.group(1).strip()
        name_upper = name.upper()
        if name_upper in _IND_TICKER_MAP:
            return _IND_TICKER_MAP[name_upper]
        name_clean = re.sub(r"\b(ltd|limited|pvt|private)\b", "", name, flags=re.IGNORECASE).strip().upper()
        name_clean = re.sub(r"\s+", " ", name_clean)
        if name_clean in _IND_TICKER_MAP:
            return _IND_TICKER_MAP[name_clean]
        name_and = name_clean.replace("&", "AND")
        if name_and in _IND_TICKER_MAP:
            return _IND_TICKER_MAP[name_and]
        name_amp = name_clean.replace("AND", "&")
        if name_amp in _IND_TICKER_MAP:
            return _IND_TICKER_MAP[name_amp]

        # If prefix before parentheses is NOT an INDS broker code (e.g. 'MSFT (Microsoft)'),
        # use the clean prefix itself
        prefix = s[:match.start()].strip()
        if prefix and not prefix.upper().startswith("INDS"):
            if ":" in prefix:
                prefix = prefix.split(":")[-1].strip()
            return re.sub(r"-(BE|EQ|BZ|SM|ST)$", "", prefix, flags=re.IGNORECASE).strip().upper()

        # Return alphanumeric token if not in static map
        return re.sub(r"[^A-Z0-9]", "", name_clean)[:10]

    if ":" in s:
        s = s.split(":")[-1].strip()
    # Remove -BE, -EQ, -BZ suffixes
    s = re.sub(r"-(BE|EQ|BZ|SM|ST)$", "", s, flags=re.IGNORECASE).strip()
    return s.upper()


def clean_display_name(symbol: str) -> str:
    """Extract a human-friendly company name or clean ticker from raw broker codes.
    
    Examples:
        'INDS02938 (GTL Infrastructure Ltd)' -> 'GTL Infrastructure Ltd'
        'INDS02425 (Shipping Corporation of India Ltd)' -> 'Shipping Corporation of India Ltd'
        'NSE:OLAELEC' -> 'OLAELEC'
        'BSE:TATAMOTORS' -> 'TATAMOTORS'
        'MOREPENLAB-BE' -> 'MOREPENLAB'
    """
    s = (symbol or "").strip()
    match = re.search(r"\(([^)]+)\)", s)
    if match:
        return match.group(1).strip()
    if ":" in s:
        s = s.split(":")[-1].strip()
    s = re.sub(r"-(BE|EQ|BZ|SM|ST)$", "", s, flags=re.IGNORECASE).strip()
    return s


def _parse_float(val: Optional[str]) -> Optional[float]:
    """Safely convert scraped number strings into floats."""
    if not val:
        return None
    cleaned = re.sub(r"[^\d.-]", "", val)
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


async def fetch_news_catalysts(
    symbol: str,
    company_name: Optional[str] = None,
    max_items: int = 4
) -> List[NewsCatalyst]:
    """Fetch recent targeted company headlines from Google News RSS (100% free, no key needed)."""
    disp_name = (company_name or clean_display_name(symbol)).strip()
    clean_sym = clean_symbol(symbol)
    cache_key = f"{clean_sym}_{disp_name}"
    now = time.monotonic()
    
    if cache_key in _NEWS_CACHE:
        cached_time, cached_items = _NEWS_CACHE[cache_key]
        if now - cached_time < NEWS_CACHE_TTL:
            return cached_items

    async with _CRAWLER_SEMAPHORE:
        def _fetch():
            import email.utils
            from datetime import datetime, timezone

            # Strip legal corporate suffixes for cleaner exact search
            search_name = re.sub(r"\b(ltd|limited|pvt|private)\b", "", disp_name, flags=re.IGNORECASE).strip()
            
            catalysts: List[NewsCatalyst] = []
            now_dt = datetime.now(timezone.utc)

            # 1. First attempt: Bing News RSS for rich journalistic summaries & direct publisher URLs
            try:
                bing_q = f'"{search_name}"'
                bing_url = f"https://www.bing.com/news/search?q={urllib.parse.quote(bing_q)}&format=rss"
                req_bing = urllib.request.Request(bing_url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req_bing, timeout=5) as resp_bing:
                    bing_root = ET.fromstring(resp_bing.read())
                
                for it in bing_root.findall(".//item"):
                    if len(catalysts) >= max_items:
                        break
                    title = it.find("title").text if it.find("title") is not None else ""
                    desc = it.find("description").text if it.find("description") is not None else ""
                    link_raw = it.find("link").text if it.find("link") is not None else ""
                    m = re.search(r"url=([^&]+)", link_raw)
                    clean_link = urllib.parse.unquote(m.group(1)) if m else link_raw
                    pubdate = it.find("pubDate").text if it.find("pubDate") is not None else ""

                    if not title:
                        continue

                    # Sentiment check
                    combined_text = f"{title} {desc}".lower()
                    if any(w in combined_text for w in ["soar", "jump", "beat", "profit up", "growth", "high", "order win", "dividend", "rally", "doubles"]):
                        sent = "POSITIVE"
                    elif any(w in combined_text for w in ["drop", "plunge", "slump", "loss", "probe", "raid", "cut", "downgrade", "fall", "sink", "scandal", "penalty"]):
                        sent = "NEGATIVE"
                    else:
                        sent = "NEUTRAL"

                    # Category tag
                    if any(w in combined_text for w in ["q1", "q2", "q3", "q4", "quarter", "results", "profit", "revenue", "ebitda", "pat"]):
                        cat = "EARNINGS"
                    elif any(w in combined_text for w in ["sebi", "rbi", "probe", "notice", "fraud", "court", "jpc", "penalty"]):
                        cat = "REGULATORY"
                    elif any(w in combined_text for w in ["contract", "order", "deal", "expansion"]):
                        cat = "CONTRACT"
                    else:
                        cat = "GENERAL"

                    catalysts.append(NewsCatalyst(
                        headline=title.strip(),
                        source="Financial Wire",
                        published_at=pubdate,
                        sentiment=sent,
                        category=cat,
                        link=clean_link,
                        summary_content=desc.strip() if desc else None,
                    ))
            except Exception as exc:
                logger.debug("Bing News crawl note for %s: %s", search_name, exc)

            # 2. Second attempt: Google News RSS fallback / complement
            if len(catalysts) < max_items:
                # Query recent news with when:30d for freshness
                if len(search_name.split()) >= 2:
                    query = f'"{search_name}" when:30d'
                else:
                    query = f'"{search_name}" share OR stock when:30d'

                url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                try:
                    with urllib.request.urlopen(req, timeout=6) as resp:
                        xml_bytes = resp.read()
                    root = ET.fromstring(xml_bytes)
                    items = root.findall(".//item")
                    
                    # If no items in past 30 days, fallback to standard query
                    if not items:
                        fallback_q = f'"{search_name}"' if len(search_name.split()) >= 2 else f'"{search_name}" share OR stock NSE'
                        fb_url = f"https://news.google.com/rss/search?q={urllib.parse.quote(fallback_q)}&hl=en-IN&gl=IN&ceid=IN:en"
                        req_fb = urllib.request.Request(fb_url, headers={"User-Agent": USER_AGENT})
                        with urllib.request.urlopen(req_fb, timeout=6) as resp_fb:
                            root = ET.fromstring(resp_fb.read())
                        items = root.findall(".//item")

                    # Meaningful tokens from company name for relevance filtering (avoid matching generic words like 'India')
                    stop_words = {"ltd", "limited", "the", "co", "company", "corp", "corporation", "inc", "pvt", "private", "and", "of", "india", "global"}
                    name_tokens = [t.lower() for t in search_name.split() if len(t) > 2 and t.lower() not in stop_words]

                    for it in items:
                        if len(catalysts) >= max_items:
                            break

                        title_elem = it.find("title")
                        source_elem = it.find("source")
                        pubdate_elem = it.find("pubDate")
                        link_elem = it.find("link")
                        desc_elem = it.find("description")

                        title = title_elem.text if title_elem is not None else ""
                        source = source_elem.text if source_elem is not None else "Financial News"
                        pubdate = pubdate_elem.text if pubdate_elem is not None else ""
                        link = link_elem.text if link_elem is not None else None
                        desc_raw = desc_elem.text if desc_elem is not None else ""
                        clean_desc = re.sub(r"<[^>]+>", " ", desc_raw).strip() if desc_raw else None

                        # Avoid duplicate headlines
                        if any(c.headline.lower() == title.lower() for c in catalysts):
                            continue

                        # Date freshness filter: avoid articles older than 45 days
                        if pubdate:
                            try:
                                parsed_dt = email.utils.parsedate_to_datetime(pubdate)
                                if (now_dt - parsed_dt).days > 45 and catalysts:
                                    continue
                            except Exception:
                                pass

                        title_lower = title.lower()

                        # Exact relevance check: Title must match company name, ticker, or core distinguishing tokens
                        is_relevant = (
                            search_name.lower() in title_lower or
                            clean_sym.lower() in title_lower or
                            (name_tokens and all(tok in title_lower for tok in name_tokens))
                        )

                        # Reject if title is clearly about a distinct rival or unrelated entity
                        if "shreeji shipping" in title_lower and "shipping corporation of india" not in title_lower:
                            is_relevant = False

                        if not is_relevant and items:
                            if len(catalysts) >= 2:
                                continue

                        # Basic rule-based sentiment
                        if any(w in title_lower for w in ["soar", "jump", "beat", "profit up", "growth", "high", "order win", "dividend", "rally"]):
                            sentiment = "POSITIVE"
                        elif any(w in title_lower for w in ["drop", "plunge", "slump", "loss", "probe", "raid", "cut", "downgrade", "fall", "sink"]):
                            sentiment = "NEGATIVE"
                        else:
                            sentiment = "NEUTRAL"

                        # Category tag
                        if any(w in title_lower for w in ["q1", "q2", "q3", "q4", "quarter", "results", "profit", "revenue", "ebitda"]):
                            category = "EARNINGS"
                        elif any(w in title_lower for w in ["sebi", "rbi", "probe", "notice", "fraud", "court"]):
                            category = "REGULATORY"
                        elif any(w in title_lower for w in ["contract", "order", "deal"]):
                            category = "CONTRACT"
                        else:
                            category = "GENERAL"

                        catalysts.append(NewsCatalyst(
                            headline=title,
                            source=source,
                            published_at=pubdate,
                            sentiment=sentiment,
                            category=category,
                            link=link,
                            summary_content=clean_desc,
                        ))
                except Exception as exc:
                    logger.warning("Google News crawl note for %s: %s", search_name, exc)

            return catalysts

        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, _fetch)
        _NEWS_CACHE[cache_key] = (now, results)
        return results


async def fetch_fundamental_vitals(
    symbol: str,
    company_name: Optional[str] = None
) -> FundamentalVitals:
    """Fetch balance sheet & quarterly financial vitals from Screener.in (100% free public data)."""
    disp_name = (company_name or clean_display_name(symbol)).strip()
    clean_sym = clean_symbol(symbol)
    cache_key = f"{clean_sym}_{disp_name}"
    now = time.monotonic()

    if cache_key in _FUNDAMENTALS_CACHE:
        cached_time, cached_vitals = _FUNDAMENTALS_CACHE[cache_key]
        if now - cached_time < FUNDAMENTALS_CACHE_TTL:
            return cached_vitals

    async with _CRAWLER_SEMAPHORE:
        def _fetch() -> FundamentalVitals:
            vitals = FundamentalVitals()
            search_q = re.sub(r"\b(ltd|limited|pvt|private)\b", "", disp_name, flags=re.IGNORECASE).strip()
            try:
                # 1. Resolve Screener URL path (clean company name first, fallback to clean ticker)
                matches = []
                for q_candidate in [search_q, clean_sym]:
                    if not q_candidate:
                        continue
                    search_url = f"https://www.screener.in/api/company/search/?q={urllib.parse.quote(q_candidate)}"
                    req = urllib.request.Request(search_url, headers={"User-Agent": USER_AGENT})
                    import json
                    try:
                        with urllib.request.urlopen(req, timeout=5) as resp:
                            candidates = json.loads(resp.read().decode("utf-8", errors="ignore"))
                        if candidates and isinstance(candidates, list):
                            matches = candidates
                            break
                    except Exception:
                        continue

                if not matches or not isinstance(matches, list):
                    return vitals

                company_path = matches[0].get("url")
                if not company_path:
                    return vitals

                # 2. Fetch full company page
                page_url = f"https://www.screener.in{company_path}"
                req_page = urllib.request.Request(page_url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req_page, timeout=6) as resp_page:
                    html = resp_page.read().decode("utf-8", errors="ignore")

                soup = BeautifulSoup(html, "html.parser")

                # Top Ratios (Market Cap, P/E, ROCE, ROE, Book Value, High/Low)
                top_ratios = soup.find("ul", id="top-ratios")
                if top_ratios:
                    for li in top_ratios.find_all("li"):
                        name_elem = li.find("span", class_="name")
                        val_elem = li.find("span", class_="number")
                        if not name_elem or not val_elem:
                            continue
                        name = name_elem.text.strip().lower()
                        val = val_elem.text.strip()
                        if "market cap" in name:
                            vitals.market_cap_cr = _parse_float(val)
                        elif "stock p/e" in name or "pe" in name:
                            vitals.pe_ratio = _parse_float(val)
                        elif "book value" in name:
                            vitals.book_value = _parse_float(val)
                        elif "roce" in name:
                            vitals.roce_pct = _parse_float(val)
                        elif "roe" in name:
                            vitals.roe_pct = _parse_float(val)

                # Pros & Cons
                pros_div = soup.find("div", class_="pros")
                if pros_div:
                    vitals.pros = [li.text.strip() for li in pros_div.find_all("li")][:3]
                cons_div = soup.find("div", class_="cons")
                if cons_div:
                    vitals.cons = [li.text.strip() for li in cons_div.find_all("li")][:3]

                # Quarterly Results (Sales growth YoY, Net Profit)
                quarters_sec = soup.find("section", id="quarters")
                if quarters_sec:
                    table = quarters_sec.find("table", class_="data-table")
                    if table:
                        for tr in table.find_all("tr"):
                            tds = [td.text.strip() for td in tr.find_all("td")]
                            if not tds:
                                continue
                            row_name = tds[0].lower()
                            if "sales" in row_name:
                                nums = [_parse_float(td) for td in tds[1:]]
                                valid = [n for n in nums if n is not None]
                                if len(valid) >= 5 and valid[-5] > 0:
                                    vitals.sales_growth_yoy_pct = round(((valid[-1] - valid[-5]) / valid[-5]) * 100.0, 1)
                                elif "yoy sales growth" in row_name:
                                    vitals.sales_growth_yoy_pct = _parse_float(tds[-1])
                            elif "net profit" in row_name:
                                vitals.net_profit_cr = _parse_float(tds[-1])

                # Shareholding (Promoter holding & Institutional trend)
                sh_sec = soup.find("section", id="shareholding")
                if sh_sec:
                    table = sh_sec.find("table", class_="data-table")
                    if table:
                        for tr in table.find_all("tr"):
                            tds = [td.text.strip() for td in tr.find_all("td")]
                            if not tds:
                                continue
                            row_name = tds[0].lower()
                            if "promoters" in row_name:
                                vitals.promoter_holding_pct = _parse_float(tds[-1])
                            elif "fii" in row_name or "dii" in row_name:
                                if len(tds) >= 3:
                                    curr = _parse_float(tds[-1]) or 0.0
                                    prior = _parse_float(tds[-2]) or 0.0
                                    if curr > prior + 0.3:
                                        vitals.fii_dii_trend = "ACCUMULATING"
                                    elif curr < prior - 0.3:
                                        vitals.fii_dii_trend = "DUMPING"

                # Balance Sheet: Calculate Debt to Equity = Borrowings / (Equity Capital + Reserves)
                bs_sec = soup.find("section", id="balance-sheet")
                if bs_sec:
                    eq_cap = 0.0
                    reserves = 0.0
                    borrowings = 0.0
                    has_bs_data = False
                    for tr in bs_sec.find_all("tr"):
                        tds = [td.text.strip() for td in tr.find_all("td")]
                        if not tds:
                            continue
                        row_name = tds[0].lower()
                        val = _parse_float(tds[-1]) or 0.0
                        if "equity capital" in row_name:
                            eq_cap = val
                            has_bs_data = True
                        elif "reserves" in row_name:
                            reserves = val
                            has_bs_data = True
                        elif "borrowings" in row_name:
                            borrowings = val
                            has_bs_data = True

                    if has_bs_data:
                        net_worth = eq_cap + reserves
                        if net_worth > 0:
                            vitals.debt_to_equity = round(borrowings / net_worth, 2)
                        elif borrowings == 0:
                            vitals.debt_to_equity = 0.0

                # Fallback: Parse ROCE from section id="ratios" if missing from top-ratios
                if vitals.roce_pct is None:
                    ratios_sec = soup.find("section", id="ratios")
                    if ratios_sec:
                        for tr in ratios_sec.find_all("tr"):
                            tds = [td.text.strip() for td in tr.find_all("td")]
                            if tds and "roce" in tds[0].lower():
                                val = _parse_float(tds[-1])
                                if val is not None:
                                    vitals.roce_pct = val
                                    break

            except Exception as exc:
                logger.warning("Screener crawl note for %s: %s", search_q, exc)

            # Robust fallback to yfinance if Screener was rate-limited (429) or missing vitals
            if vitals.pe_ratio is None or vitals.debt_to_equity is None or vitals.market_cap_cr is None:
                try:
                    import yfinance as yf
                    for ticker_cand in [f"{clean_sym}.NS", f"{clean_sym}.BO"]:
                        t = yf.Ticker(ticker_cand)
                        inf = t.info
                        if inf and (inf.get("marketCap") or inf.get("regularMarketPrice") or inf.get("currentPrice")):
                            if vitals.market_cap_cr is None and inf.get("marketCap"):
                                vitals.market_cap_cr = round(float(inf["marketCap"]) / 1e7, 1)
                            if vitals.pe_ratio is None:
                                pe = inf.get("trailingPE") or inf.get("forwardPE")
                                if pe:
                                    vitals.pe_ratio = round(float(pe), 1)
                            if vitals.debt_to_equity is None and inf.get("debtToEquity") is not None:
                                de_val = float(inf["debtToEquity"])
                                vitals.debt_to_equity = round(de_val / 100.0, 2) if de_val > 5.0 else round(de_val, 2)
                            if vitals.roe_pct is None and inf.get("returnOnEquity") is not None:
                                vitals.roe_pct = round(float(inf["returnOnEquity"]) * 100.0, 1)
                            break
                except Exception as exc:
                    logger.debug("yfinance fallback note for %s: %s", clean_sym, exc)

            return vitals

        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, _fetch)
        _FUNDAMENTALS_CACHE[cache_key] = (now, results)
        return results


def calculate_market_causality(
    stock_move_pct: float,
    benchmark_move_pct: float,
    sector_move_pct: Optional[float] = None
) -> Tuple[MoveCausality, str]:
    """Decompose price movement into Systemic Market Beta vs. Idiosyncratic Company-Specific.
    
    Returns (MoveCausality, explanation_text).
    """
    # Case 1: Sharp stock fall
    if stock_move_pct <= -5.0:
        if benchmark_move_pct <= -2.0 or (sector_move_pct and sector_move_pct <= -3.0):
            return (
                MoveCausality.SYSTEMIC_MARKET_BETA,
                f"Drop of {stock_move_pct:.1f}% coincided with broad market/sector sell-off (Nifty: {benchmark_move_pct:+.1f}%). Movement is primarily systemic beta."
            )
        else:
            return (
                MoveCausality.COMPANY_SPECIFIC,
                f"Severe drop of {stock_move_pct:.1f}% diverged strongly from stable market (Nifty: {benchmark_move_pct:+.1f}%). Suggests idiosyncratic risk, earnings shock, or negative news."
            )

    # Case 2: Sharp stock surge
    elif stock_move_pct >= 6.0:
        if benchmark_move_pct >= 2.0:
            return (
                MoveCausality.SYSTEMIC_MARKET_BETA,
                f"Surge of {stock_move_pct:+.1f}% aligned with broad market tailwinds (Nifty: {benchmark_move_pct:+.1f}%)."
            )
        else:
            return (
                MoveCausality.COMPANY_SPECIFIC,
                f"Outperformance surge of {stock_move_pct:+.1f}% while Nifty moved {benchmark_move_pct:+.1f}%. Indicates high relative strength, volume accumulation, or positive corporate catalyst."
            )

    # Case 3: Routine consolidation
    return (
        MoveCausality.SYSTEMIC_MARKET_BETA,
        f"Movement of {stock_move_pct:+.1f}% is within normal daily volatility range (Nifty: {benchmark_move_pct:+.1f}%)."
    )


async def fetch_technical_momentum(
    symbol: str,
    owner_id: Optional[str] = None
) -> Tuple[Optional[str], Optional[int], Optional[int]]:
    """Fetch genuine moving-average momentum verdict from SignalCache or live analytics engine.
    
    Returns (trend_verdict, trend_score, trend_max_score).
    Never invents or fabricates moving-average claims from personal portfolio P&L.
    """
    clean = clean_symbol(symbol).strip().upper()
    now = time.monotonic()
    if clean in _MOMENTUM_CACHE:
        ts, verd, score, max_s = _MOMENTUM_CACHE[clean]
        if now - ts < 3600.0 and verd is not None:
            return verd, score, max_s

    # 1. Check SignalCacheRepository
    try:
        from storage.tables.repositories import SignalCacheRepository
        sig_repo = SignalCacheRepository()
        for cand in [f"NSE:{clean}", clean, f"BSE:{clean}"]:
            ent = await sig_repo.get_entity(sig_repo.PARTITION, cand)
            if ent:
                import json
                p = json.loads(ent.get("payload") or "{}")
                m = p.get("momentum")
                if m and m.get("verdict"):
                    v = m.get("verdict")
                    s = m.get("score")
                    mx = m.get("max", 5)
                    verd_str = f"{v} ({s}/{mx})" if s is not None else v
                    _MOMENTUM_CACHE[clean] = (now, verd_str, s, mx)
                    return verd_str, s, mx
    except Exception as exc:
        logger.debug("SignalCache lookup note for %s: %s", clean, exc)

    # 2. Compute on-demand from price candles via Momentum Analyzer engine
    if owner_id:
        try:
            from apps.api.routers.analytics import _load_candles
            from core.analytics import analyze_momentum
            inst, candles, bm = await _load_candles(owner_id, clean, lookback_days=400, with_benchmark=True)
            if candles and len(candles) >= 20:
                a = analyze_momentum(f"NSE:{clean}", candles, benchmark_candles=bm)
                verd_str = f"{a.trend_verdict} ({a.trend_score}/{a.trend_max_score})"
                _MOMENTUM_CACHE[clean] = (now, verd_str, a.trend_score, a.trend_max_score)
                return verd_str, a.trend_score, a.trend_max_score
        except Exception as exc:
            logger.debug("On-demand momentum calculation note for %s: %s", clean, exc)

    return None, None, None


async def build_investigation_dossier(
    symbol: str,
    stock_move_pct: float = 0.0,
    benchmark_move_pct: float = 0.0,
    company_name: Optional[str] = None,
    owner_id: Optional[str] = None
) -> InvestigationDossier:
    """Build a comprehensive forensic due-diligence package combining news, financials, causality, and true technical momentum."""
    disp_name = (company_name or clean_display_name(symbol)).strip()
    clean_sym = clean_symbol(symbol)
    
    # Run news, fundamentals, and true technical momentum fetches concurrently
    news_task = fetch_news_catalysts(clean_sym, company_name=disp_name, max_items=4)
    fundamentals_task = fetch_fundamental_vitals(clean_sym, company_name=disp_name)
    momentum_task = fetch_technical_momentum(clean_sym, owner_id=owner_id)
    news, vitals, (tech_trend, t_score, t_max) = await asyncio.gather(news_task, fundamentals_task, momentum_task)

    causality, explanation = calculate_market_causality(stock_move_pct, benchmark_move_pct)

    # Synthesize plain-English purpose of move
    purpose_notes = []
    if tech_trend:
        purpose_notes.append(f"Moving Average Trend: {tech_trend}")
    if news:
        top_headlines = [n.headline for n in news[:2]]
        purpose_notes.append(f"Recent Coverage: {'; '.join(top_headlines)}")
    if vitals.sales_growth_yoy_pct is not None:
        purpose_notes.append(f"YoY Sales Growth: {vitals.sales_growth_yoy_pct:+.1f}%")
    if vitals.cons:
        purpose_notes.append(f"Key Risk: {vitals.cons[0]}")
    if vitals.pros:
        purpose_notes.append(f"Key Strength: {vitals.pros[0]}")

    purpose_str = " | ".join(purpose_notes) if purpose_notes else explanation

    # Calculate forensic risk score (0-100)
    risk_score = 15  # baseline
    if causality == MoveCausality.COMPANY_SPECIFIC and stock_move_pct < -5.0:
        risk_score += 35
    if vitals.roce_pct is not None and vitals.roce_pct < 0:
        risk_score += 20
    if vitals.fii_dii_trend == "DUMPING":
        risk_score += 15
    if any(n.sentiment == "NEGATIVE" for n in news):
        risk_score += 15
    risk_score = min(max(risk_score, 0), 100)

    return InvestigationDossier(
        symbol=clean_sym,
        causality=causality,
        causality_explanation=explanation,
        market_benchmark_delta={
            "stock_move_pct": stock_move_pct,
            "benchmark_move_pct": benchmark_move_pct,
            "relative_spread_pct": round(stock_move_pct - benchmark_move_pct, 2)
        },
        recent_news=news,
        fundamental_vitals=vitals,
        technical_trend=tech_trend,
        trend_score=t_score,
        trend_max=t_max,
        purpose_of_move=purpose_str,
        forensic_risk_score=risk_score
    )
