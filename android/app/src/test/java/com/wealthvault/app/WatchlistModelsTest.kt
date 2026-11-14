package com.wealthvault.app

import com.wealthvault.app.data.WatchlistItem
import com.wealthvault.app.data.WatchlistResponse
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test

class WatchlistModelsTest {
    private val json = Json { ignoreUnknownKeys = true; coerceInputValues = true; explicitNulls = false }

    @Test
    fun testWatchlistResponseDeserialization() {
        val jsonPayload = """
            {
                "items": [
                    {
                        "symbol": "NSE:HDFCBANK",
                        "name": "HDFC Bank",
                        "exchange": "NSE",
                        "entry_price": 1750.50,
                        "last_price": 1803.05,
                        "return_pct": 3.00,
                        "notes": "50-DMA bounce radar",
                        "trend_verdict": "Strong Uptrend",
                        "trend_score": 5,
                        "trend_max_score": 5,
                        "ath_breakout_state": "SETUP_ACTIVE",
                        "added_at": "2026-11-14T20:00:00Z"
                    },
                    {
                        "symbol": "NSE:ABB",
                        "name": "ABB India",
                        "exchange": "NSE",
                        "entry_price": 6563.00,
                        "last_price": 6563.00,
                        "return_pct": 0.0,
                        "ath_breakout_state": "FLAT"
                    }
                ],
                "count": 2
            }
        """.trimIndent()

        val response = json.decodeFromString<WatchlistResponse>(jsonPayload)
        assertEquals(2, response.count)
        assertEquals(2, response.items.size)

        val first = response.items[0]
        assertEquals("NSE:HDFCBANK", first.symbol)
        assertEquals("HDFC Bank", first.name)
        assertEquals(1750.50, first.entry_price!!, 0.001)
        assertEquals(1803.05, first.last_price!!, 0.001)
        assertEquals(3.00, first.return_pct!!, 0.001)
        assertEquals("Strong Uptrend", first.trend_verdict)
        assertEquals(5, first.trend_score)
        assertEquals("SETUP_ACTIVE", first.ath_breakout_state)

        val second = response.items[1]
        assertEquals("NSE:ABB", second.symbol)
        assertEquals(0.0, second.return_pct!!, 0.001)
        assertEquals("FLAT", second.ath_breakout_state)
    }

    @Test
    fun testWatchlistItemDefaults() {
        val item = WatchlistItem(symbol = "TCS")
        assertEquals("TCS", item.symbol)
        assertEquals(null, item.name)
        assertEquals(null, item.entry_price)
        assertEquals(null, item.last_price)
        assertEquals(5, item.trend_max_score)
    }
}
