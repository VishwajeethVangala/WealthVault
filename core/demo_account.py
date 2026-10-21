"""A demo account for app-store reviewers.

Google Play's reviewers cannot sign in with Google (their devices are not linked to a Google account we could hand
over), so the server offers one username-and-password login for a sample account. It is OFF unless DEMO_USERNAME and
DEMO_PASSWORD are set in the environment, and it only ever opens this one account, filled with made-up holdings.
"""

import hmac
from datetime import datetime, timedelta, timezone
from typing import List

from core.config import get_settings
from core.models import AssetClass, Holding, PortfolioSnapshot, User
from storage.tables.repositories import (
    BrokerConnectionRepository,
    HoldingsRepository,
    SnapshotsRepository,
    UserRepository,
)

DEMO_USER_ID = "demo_reviewer"
DEMO_CONNECTION_ID = "conn_demo_sample"

# symbol, class, quantity, average price, current price, day change %
_SAMPLE = [
    ("RELIANCE", AssetClass.EQUITY, 40, 2450.0, 2890.0, 0.8),
    ("HDFCBANK", AssetClass.EQUITY, 60, 1510.0, 1675.0, -0.4),
    ("INFY", AssetClass.EQUITY, 50, 1380.0, 1520.0, 0.6),
    ("TCS", AssetClass.EQUITY, 15, 3300.0, 3920.0, 0.3),
    ("Parag Parikh Flexi Cap Fund", AssetClass.MUTUAL_FUND, 900, 62.0, 78.5, 0.2),
    ("HDFC Index Fund Nifty 50", AssetClass.MUTUAL_FUND, 400, 170.0, 214.0, 0.5),
    ("Sovereign Gold Bond 2029", AssetClass.GOLD, 20, 5100.0, 7350.0, 0.1),
    ("AAPL", AssetClass.US_STOCKS, 12, 14500.0, 17800.0, 0.9),
]


def demo_enabled() -> bool:
    s = get_settings()
    return bool(s.DEMO_USERNAME and s.DEMO_PASSWORD)


def check_demo_login(username: str, password: str) -> bool:
    """Constant-time check against the configured demo login; always False when the demo is not enabled."""
    s = get_settings()
    if not demo_enabled():
        return False
    ok_user = hmac.compare_digest(username.strip().encode(), s.DEMO_USERNAME.encode())
    ok_pass = hmac.compare_digest(password.encode(), s.DEMO_PASSWORD.encode())
    return ok_user and ok_pass


def _holdings(now_iso: str) -> List[Holding]:
    rows = []
    for sym, cls, qty, avg, cur, day in _SAMPLE:
        value = round(qty * cur, 2)
        rows.append(
            Holding(
                holding_id=f"{DEMO_CONNECTION_ID}_{sym}".replace(" ", "_"),
                owner_id=DEMO_USER_ID,
                connection_id=DEMO_CONNECTION_ID,
                instrument_symbol=sym,
                asset_class=cls,
                quantity=qty,
                average_price=avg,
                current_value=value,
                current_price=cur,
                pnl=round(value - qty * avg, 2),
                day_pnl=round(value * day / 100, 2),
                day_change_percentage=day,
                data_freshness="cached",
                last_price_updated_at=now_iso,
                currency="INR",
            )
        )
    return rows


async def ensure_demo_account() -> User:
    """Create the demo user, one sample connection, sample holdings and a month of snapshots if they are missing."""
    now = datetime.now(timezone.utc)
    users, conns, holdings, snaps = UserRepository(), BrokerConnectionRepository(), HoldingsRepository(), SnapshotsRepository()
    try:
        user = await users.get_user(DEMO_USER_ID)
        if not user:
            user = await users.save_user(User(user_id=DEMO_USER_ID, email="demo@example.invalid", name="Demo Reviewer"))
        if not await conns.is_tenant_initialized(DEMO_USER_ID):
            await conns.create_connection(
                owner_id=DEMO_USER_ID, broker_name="demo", connection_id=DEMO_CONNECTION_ID,
                account_id="DEMO001", account_label="Sample account",
            )
            await conns.mark_tenant_initialized(DEMO_USER_ID)
        if not await holdings.get_holdings(owner_id=DEMO_USER_ID):
            rows = _holdings(now.isoformat())
            await holdings.upsert_holdings(DEMO_USER_ID, rows)
            invested = sum(h.quantity * h.average_price for h in rows)
            value_now = sum(h.current_value for h in rows)
            days = 30
            for i in range(days + 1):
                d = (now - timedelta(days=days - i)).date().isoformat()
                # a gentle, deterministic climb from 92% to 100% of today's value, with a small wobble
                frac = 0.92 + 0.08 * (i / days) + (0.004 if i % 3 == 0 else -0.003 if i % 3 == 1 else 0.0)
                val = value_now if i == days else round(value_now * min(frac, 1.0), 2)
                alloc = {}
                for h in rows:
                    a = alloc.setdefault(h.asset_class.value, {"value": 0.0, "percentage": 0.0})
                    a["value"] += h.current_value
                for a in alloc.values():
                    a["percentage"] = round(a["value"] / value_now * 100, 2)
                await snaps.save_snapshot(
                    PortfolioSnapshot(
                        snapshot_id=f"snapshot_{d}", owner_id=DEMO_USER_ID, as_of_date=d,
                        total_current_value=val, total_invested_value=round(invested, 2),
                        total_unrealized_pnl=round(val - invested, 2),
                        total_pnl_percentage=round((val - invested) / invested * 100, 2),
                        asset_allocation=alloc, holdings_count=len(rows),
                    )
                )
        return user
    finally:
        for r in (users, conns, holdings, snaps):
            await r.close()
