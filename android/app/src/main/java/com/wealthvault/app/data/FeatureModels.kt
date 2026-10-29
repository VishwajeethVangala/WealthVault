package com.wealthvault.app.data

import kotlinx.serialization.Serializable

/** Shapes for the analysis features (signals, Stage 2, momentum, strategies), brokers and the overview panels. */

/** A stock offered while typing in the Momentum and Strategy boxes; `symbol` is what those calls take. */
@Serializable
data class StockSuggestion(val symbol: String = "", val name: String = "", val exchange: String = "")

// --- equity signals (same per-stock reading the web app shows) --------------------------------------------

@Serializable
data class MomentumSignal(
    val verdict: String = "",
    val score: Int = 0,
    val max: Int = 0,
    val last_price: Double = 0.0,
    val high_52w: Double? = null,
    val low_52w: Double? = null,
    val pct_from_52w_high: Double? = null,
    val range_pos: Double? = null,
)

/** The text of one notification, fetched from the server by the id the push carried. */
@Serializable
data class PushNote(
    val kind: String = "",
    val title: String = "",
    val body: String = "",
    val body_masked: String = "",
    val public_title: String = "",
    val route: String = "",
)

@Serializable
data class AthCall(
    val signal_date: String = "",
    val entry_date: String = "",
    val entry_price: Double? = null,
    val close: Double? = null,
    val prior_ath: Double? = null,
    val above_ath_pct: Double? = null,
    val days_since_below_dma: Int? = null,
    val window_bars: Int? = null,
    val dma: Double? = null,
)

@Serializable
data class ExitCall(
    val signal_date: String = "",
    val exit_date: String = "",
    val exit_price: Double? = null,
    val reason: String = "",
    val entry_date: String = "",
    val entry_price: Double? = null,
    val pnl_pct: Double? = null,
    val bars_held: Int? = null,
)

@Serializable
data class PendingSell(
    val signal_date: String = "",
    val signal_close: Double? = null,
    val reason: String = "",
    val entry_date: String? = null,
    val entry_price: Double? = null,
)

@Serializable
data class AthSignal(
    val state: String = "",
    val headline: String = "",
    val detail: String = "",
    val last_signal: String? = null,
    val entry_date: String? = null,
    val entry_price: Double? = null,
    val bars_held: Int? = null,
    val in_window: Boolean = false,
    val window_days_left: Int? = null,
    val pct_to_ath: Double? = null,
    val pct_above_dma: Double? = null,
    val call: AthCall? = null,
    val exits: List<ExitCall>? = null,
)

@Serializable
data class StockSignals(
    val instrument: String = "",
    val name: String? = null,
    val as_of: String? = null,
    val live_date: String? = null,
    val last_sessions: List<String>? = null,
    val momentum: MomentumSignal? = null,
    val ath: AthSignal? = null,
    val errors: Map<String, String> = emptyMap(),
    val computed_at: String? = null,
    val history_status: String? = null,
    val history_note: String? = null,
)

@Serializable
data class SignalsJob(
    val state: String = "idle",
    val total: Int = 0,
    val done: Int = 0,
    val failed: Int = 0,
    val finished_at: String? = null,
    val message: String? = null,
    val auth_url: String? = null,
    /** where the stocks come from: on the Chartink list, held, and on both (counted once in `total`) */
    val list_count: Int = 0,
    val holdings_count: Int = 0,
    val overlap: Int = 0,
    /** "manual" (the button) or "schedule" (the market-hours auto refresh) */
    val trigger: String = "manual",
)

@Serializable
data class SignalsResponse(
    val job: SignalsJob = SignalsJob(),
    val symbol_map: Map<String, String> = emptyMap(),
    val signals: Map<String, StockSignals> = emptyMap(),
)

@Serializable
data class LiveSignalsResponse(val signals: Map<String, StockSignals> = emptyMap(), val live: Boolean = false, val reason: String? = null)

@Serializable
data class LiveQuote(val price: Double = 0.0, val day_change_pct: Double? = null, val ext_price: Double? = null)

@Serializable
data class UsLiveResponse(val quotes: Map<String, LiveQuote> = emptyMap(), val session_closed: Boolean = true)

// --- Stage 2 screener --------------------------------------------------------------------------------------

@Serializable
data class Stage2Row(
    val nsecode: String = "",
    val name: String = "",
    val close: Double = 0.0,
    val per_chg: Double? = null,
    val volume: Double? = null,
    val market_cap: Double? = null,
    val sector: String? = null,
    val held: Boolean = false,
    val is_new: Boolean? = null,
)

@Serializable
data class Stage2Dropped(val nsecode: String = "", val name: String = "")

@Serializable
data class Stage2List(
    val title: String = "",
    val date: String = "",
    val url: String? = null,
    val previous_date: String? = null,
    val rows: List<Stage2Row> = emptyList(),
    val dropped: List<Stage2Dropped> = emptyList(),
)

@Serializable
data class AutoRun(val slot: String = "", val at: String = "", val outcome: String = "", val message: String = "", val users: Int = 0)

/** The server's market-hours auto refresh of the Signals list. */
@Serializable
data class AutoRefresh(
    val enabled: Boolean = false,
    val every_minutes: Int = 15,
    val window: String = "",
    val next_run: String? = null,
    val last_run: AutoRun? = null,
)

@Serializable
data class Stage2Response(
    val job: SignalsJob = SignalsJob(),
    val list: Stage2List? = null,
    val signals: Map<String, StockSignals> = emptyMap(),
    val auto: AutoRefresh? = null,
)

@Serializable
data class Stage2LiveResponse(val quotes: Map<String, LiveQuote> = emptyMap())

// --- momentum analysis -------------------------------------------------------------------------------------

@Serializable
data class TrendCheck(val key: String = "", val label: String = "", val passed: Boolean = false, val detail: String = "")

@Serializable
data class MomentumPoint(val date: String = "", val close: Double = 0.0, val sma50: Double? = null, val sma200: Double? = null)

@Serializable
data class MomentumAnalysis(
    val instrument: String = "",
    val name: String? = null,
    val as_of: String = "",
    val last_price: Double = 0.0,
    val candles_used: Int = 0,
    val live_bar: Boolean = false,
    val trend_score: Int = 0,
    val trend_max_score: Int = 0,
    val trend_verdict: String = "",
    val trend_checks: List<TrendCheck> = emptyList(),
    val sma_20: Double? = null,
    val sma_50: Double? = null,
    val sma_200: Double? = null,
    val pct_from_sma50: Double? = null,
    val pct_from_sma200: Double? = null,
    val sma200_slope_pct: Double? = null,
    val cross_state: String? = null,
    val days_since_cross: Int? = null,
    val macd: Double? = null,
    val macd_signal: Double? = null,
    val macd_histogram: Double? = null,
    val returns: Map<String, Double?> = emptyMap(),
    val volatility_6m: Double? = null,
    val volatility_12m: Double? = null,
    val risk_adjusted_6m: Double? = null,
    val risk_adjusted_12m: Double? = null,
    val rsi_14: Double? = null,
    val high_52w: Double? = null,
    val low_52w: Double? = null,
    val pct_from_52w_high: Double? = null,
    val pct_from_52w_low: Double? = null,
    val benchmark: String = "",
    val relative_strength: Map<String, Double?> = emptyMap(),
    val series: List<MomentumPoint> = emptyList(),
)

// --- strategy backtests (the 200-DMA ATH breakout) -------------------------

@Serializable
data class StrategyStatus(
    val state: String = "",
    val headline: String = "",
    val detail: String = "",
    val regime_bullish: Boolean? = null,
    val regime_checks: List<TrendCheck> = emptyList(),
    val pending_order: String? = null,
    val last_signal: String? = null,
    val entry_date: String? = null,
    val entry_price: Double? = null,
    val stop_price: Double? = null,
    val unrealized_pct: Double? = null,
    val bars_held: Int? = null,
    val in_window: Boolean? = null,
    val window_days_left: Int? = null,
    val pct_to_ath: Double? = null,
    val pct_above_dma: Double? = null,
    val dma: Double? = null,
    val prior_ath: Double? = null,
    val close: Double? = null,
    val days_since_below_dma: Int? = null,
    val ut_stop: Double? = null,
    val exit_ema: Double? = null,
)

@Serializable
data class StrategyStats(
    val initial_capital: Double = 0.0,
    val final_equity: Double = 0.0,
    val net_profit: Double = 0.0,
    val net_profit_pct: Double = 0.0,
    val cagr_pct: Double = 0.0,
    val max_drawdown_pct: Double = 0.0,
    val buy_hold_return_pct: Double = 0.0,
    val total_trades: Int = 0,
    val open_trade: Boolean = false,
    val win_rate_pct: Double? = null,
    val avg_win_pct: Double? = null,
    val avg_loss_pct: Double? = null,
    val profit_factor: Double? = null,
    val avg_bars_held: Double? = null,
    val exposure_pct: Double = 0.0,
    val signal_exits: Int = 0,
    val stop_exits: Int = 0,
)

@Serializable
data class StrategyTrade(
    val entry_date: String = "",
    val entry_price: Double = 0.0,
    val exit_date: String? = null,
    val exit_price: Double? = null,
    val exit_reason: String = "",
    val pnl: Double = 0.0,
    val pnl_pct: Double = 0.0,
    val bars_held: Int = 0,
    val is_open: Boolean = false,
)

/** One day of a backtest: the price, the strategy's lines and signals, and both equity curves.  */
@Serializable
data class StrategyBar(
    val date: String = "",
    val high: Double = 0.0,
    val low: Double = 0.0,
    val close: Double = 0.0,
    val equity: Double = 0.0,
    val buy_hold: Double = 0.0,
    val buy: Boolean = false,
    val sell: Boolean = false,
    val stop_exit: Boolean = false,
    val stop_level: Double? = null,
    val regime: Boolean = false,
    val sma_fast: Double? = null,
    val sma_slow: Double? = null,
    val exit_ema: Double? = null,
    val ut_stop: Double? = null,
    val dma: Double? = null,
    val ath: Double? = null,
    val in_window: Boolean = false,
)

/** The settings a backtest ran with (the ATH breakout run). */
@Serializable
data class StrategyParams(
    val use_stop: Boolean? = null,
    val initial_capital: Double = 0.0,
    val commission_pct: Double? = null,
    val capital_per_trade: Double? = null,
    val dma_length: Int? = null,
    val window_bars: Int? = null,
)

@Serializable
data class StrategyResult(
    val instrument: String = "",
    val name: String? = null,
    val as_of: String = "",
    val test_start: String = "",
    val test_end: String = "",
    val bars_tested: Int = 0,
    val live_bar: Boolean = false,
    val live_price: Double? = null,
    val partial_bar_excluded: Boolean = false,
    val history_start: String? = null,
    val params: StrategyParams = StrategyParams(),
    val status: StrategyStatus = StrategyStatus(),
    val stats: StrategyStats = StrategyStats(),
    val trades: List<StrategyTrade> = emptyList(),
    val series: List<StrategyBar> = emptyList(),
)

// --- brokers -----------------------------------------------------------------------------------------------

@Serializable
data class CredentialField(val key: String = "", val label: String = "", val secret: Boolean = true, val required: Boolean = false, val help: String? = null)

@Serializable
data class BrokerCatalogItem(
    val broker_name: String = "",
    val display_name: String = "",
    val tag: String = "",
    val color: String = "",
    val auth_type: String = "",
    val description: String = "",
    val supported: Boolean = false,
    val coming_soon: Boolean = false,
    val is_connected: Boolean = false,
    val connected_count: Int = 0,
    val credential_fields: List<CredentialField> = emptyList(),
    val setup_url: String? = null,
    val setup_steps: List<String> = emptyList(),
)

@Serializable
data class CredentialSaveResponse(val saved_fields: List<String> = emptyList(), val login_ok: Boolean = false, val message: String = "", val auth_url: String? = null)

// --- overview panels ---------------------------------------------------------------------------------------

/** One day's portfolio value and money invested; `classes` is that day's value of each asset class. */
@Serializable
data class HistoryPoint(val date: String = "", val value: Double = 0.0, val invested: Double = 0.0, val classes: Map<String, Double> = emptyMap())

@Serializable
data class Ohlc(val open: Double = 0.0, val high: Double = 0.0, val low: Double = 0.0, val close: Double = 0.0)

@Serializable
data class MarketQuote(val last_price: Double = 0.0, val ohlc: Ohlc? = null)

@Serializable
data class MarketQuotesResponse(val quotes: Map<String, MarketQuote> = emptyMap())

@Serializable
data class Targets(val targets: Map<String, Double> = emptyMap())

@Serializable
data class HighBeta(val name: String = "", val weight: Double = 0.0, val beta: Double = 0.0)

@Serializable
data class PortfolioRisk(
    val days: Int = 0,
    val beta: Double? = null,
    val correlation: Double? = null,
    val volatility_pct: Double = 0.0,
    val benchmark_volatility_pct: Double = 0.0,
    val var95_1d_pct: Double = 0.0,
    val max_drawdown_pct: Double = 0.0,
    val best_day_pct: Double = 0.0,
    val worst_day_pct: Double = 0.0,
    val positive_days_pct: Double = 0.0,
    val coverage_pct: Double = 0.0,
    val high_beta: List<HighBeta> = emptyList(),
)

@Serializable
data class RiskResponse(val risk: PortfolioRisk? = null, val equity_value: Double = 0.0, val measured_stocks: Int = 0, val total_stocks: Int = 0)

/** Inputs for a 200-DMA ATH breakout run (the web's defaults). */
data class AthOptions(val startDate: String = "2015-01-01", val dmaLength: Int = 200, val windowBars: Int = 200, val capital: Double = 50000.0)
