package com.wealthvault.app.data

import kotlinx.serialization.Serializable

/** Shapes returned by the WealthVault API (the same server the web app uses). Unknown fields are ignored. */

@Serializable
data class AuthConfig(val google_client_id: String = "", val environment: String = "", val demo_login: Boolean = false, val support_email: String = "")

@Serializable
data class User(val user_id: String, val email: String = "", val name: String = "", val picture: String? = null)

@Serializable
data class TokenResponse(val access_token: String, val user: User)

@Serializable
data class AllocationSlice(val percentage_weight: Double = 0.0, val absolute_value: Double = 0.0)

@Serializable
data class Snapshot(
    val as_of_date: String = "",
    val total_current_value: Double = 0.0,
    val total_invested_value: Double = 0.0,
    val total_unrealized_pnl: Double = 0.0,
    val total_pnl_percentage: Double = 0.0,
    val asset_allocation: Map<String, AllocationSlice> = emptyMap(),
    val holdings_count: Int = 0,
)

@Serializable
data class Summary(val snapshot: Snapshot)

@Serializable
data class Holding(
    val holding_id: String,
    val connection_id: String = "",
    val instrument_symbol: String,
    val asset_class: String = "",
    val quantity: Double = 0.0,
    val average_price: Double = 0.0,
    val current_value: Double = 0.0,
    val current_price: Double? = null,
    val pnl: Double? = null,
    val day_pnl: Double? = null,
    val day_change_percentage: Double? = null,
    /** per-share day change, when the broker sends that instead of day_pnl */
    val day_change: Double? = null,
    val currency: String = "INR",
    /** "live" when refreshed from a broker quote, "cached" when it is the stored price */
    val data_freshness: String = "live",
) {
    val invested: Double get() = quantity * average_price
    val pnlPct: Double? get() = if (invested > 0) ((current_value / invested) - 1) * 100 else null
}

@Serializable
data class BrokerSession(
    val connection_id: String,
    val broker_name: String = "",
    val display_name: String = "",
    val status: String = "",
    val last_sync_time: String? = null,
    val account_id: String = "",
    val account_label: String? = null,
    val auth_type: String = "",
    val is_expired: Boolean = false,
    val holdings_count: Int = 0,
    val total_valuation: Double = 0.0,
    val error_message: String? = null,
    val auth_url: String? = null,
    val session_expires_at: String? = null,
    val mcp_server_url: String = "",
    val credentials_saved: Boolean = false,
)

/** Readable names for the server's asset classes. */
val ASSET_CLASS_LABEL = mapOf(
    "EQUITY" to "Stocks",
    "MUTUAL_FUND" to "Mutual funds",
    "US_STOCKS" to "US stocks",
    "GOLD" to "Gold",
    "NPS" to "Retirement",
    "DEBT" to "Debt",
    "OTHER" to "Other",
)
