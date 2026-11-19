"""Forensic News Scout: Google News RSS + Local FinBERT NLP Intelligence.

Crawls real-time headlines and applies FinBERT sentiment classification:
- Distinguishes material operational threats (SEBI probes, raids, insolvencies) from ordinary volatility
- Quantifies positive/negative sentiment counts and overall confidence
- Preserves direct source article links for user verification
"""

import logging
from typing import List, Optional

from core.agents.forensic_crawler import clean_symbol, fetch_news_catalysts
from core.agents.ground.contracts import NewsArticleItem, NewsIntelReport
from core.agents.ground.finbert_engine import classify_headline

logger = logging.getLogger("wealthvault.agents.ground.news_scout")

_SEVERE_THREAT_KEYWORDS = {
    "probe", "investigation", "raid", "sebi", "rbi", "penalty", "default",
    "fraud", "fir", "arrest", "cbi", "ed probe", "scandal", "insolvency", "nclt"
}


class NewsScout:
    """Scout for financial news sentiment and regulatory threat detection."""

    async def evaluate(self, symbol: str, company_name: Optional[str] = None) -> NewsIntelReport:
        clean = clean_symbol(symbol)
        try:
            catalysts = await fetch_news_catalysts(clean, company_name=company_name, max_items=5)
            
            articles: List[NewsArticleItem] = []
            pos_count = 0
            neg_count = 0
            neu_count = 0
            threat_reasons: List[str] = []
            
            for cat in catalysts:
                # Run through FinBERT engine
                sentiment, conf = classify_headline(cat.headline)
                
                if sentiment == "POSITIVE":
                    pos_count += 1
                elif sentiment == "NEGATIVE":
                    neg_count += 1
                else:
                    neu_count += 1

                # Check for severe regulatory threat in headline or full article summary (only if fresh <= 45d)
                text_to_check = f"{cat.headline} {cat.summary_content or ''}".lower()
                cat_age = cat.age_days if cat.age_days is not None else 0
                if cat_age <= 45:
                    for kw in _SEVERE_THREAT_KEYWORDS:
                        if kw in text_to_check:
                            threat_reasons.append(f"Regulatory/Legal notice ({cat.age_label or 'recent'}): '{cat.headline[:60]}...'")
                            break

                articles.append(
                    NewsArticleItem(
                        headline=cat.headline,
                        source=cat.source or "News",
                        published_at=cat.published_at or "",
                        age_days=cat.age_days,
                        age_label=cat.age_label,
                        link=cat.link,
                        sentiment=sentiment,
                        confidence=round(conf, 2),
                        category=cat.category or "GENERAL",
                        summary_content=cat.summary_content,
                    )
                )

            total = len(articles)
            if total == 0:
                return NewsIntelReport(
                    symbol=clean,
                    dominant_sentiment="NEUTRAL",
                    articles_scanned=0,
                    is_wire_quiet=True,
                    summary="Financial wire quiet: 0 material headlines in verified press over past 45 days. No active regulatory or operational developments.",
                    status="COMPLETED",
                )

            min_age_days = min((a.age_days for a in articles if a.age_days is not None), default=0)

            if neg_count > pos_count and neg_count >= 2:
                dominant = "NEGATIVE"
                overall_conf = neg_count / total
            elif pos_count > neg_count and pos_count >= 2:
                dominant = "POSITIVE"
                overall_conf = pos_count / total
            else:
                dominant = "NEUTRAL"
                overall_conf = 0.65

            material_threat = len(threat_reasons) > 0
            newest_label = articles[0].age_label or "recent"
            summary = (
                f"{total} verified headlines audited (newest: {newest_label}): {pos_count} Positive, {neg_count} Negative, {neu_count} Neutral. "
                f"Overall bias: {dominant}."
            )
            if material_threat:
                summary += f" [ACTIVE THREAT: {threat_reasons[0]}]"

            return NewsIntelReport(
                symbol=clean,
                articles_scanned=total,
                positive_count=pos_count,
                negative_count=neg_count,
                neutral_count=neu_count,
                dominant_sentiment=dominant,
                sentiment_confidence=round(overall_conf, 2),
                material_threat=material_threat,
                threat_reasons=threat_reasons,
                latest_article_age_days=min_age_days,
                is_wire_quiet=False,
                articles=articles,
                status="COMPLETED",
                summary=summary,
            )
        except Exception as exc:
            logger.warning("NewsScout evaluation error for %s: %s", clean, exc)
            return NewsIntelReport(
                symbol=clean,
                status="FAILED",
                summary=f"Error querying news wire: {str(exc)}",
            )
