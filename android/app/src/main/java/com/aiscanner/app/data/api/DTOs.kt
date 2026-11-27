package com.aiscanner.app.data.api

import com.google.gson.annotations.SerializedName

data class HealthResponse(
    @SerializedName("ok") val ok: Boolean? = null,
    @SerializedName("time") val time: String? = null
)

data class BotStatus(
    @SerializedName("mode") val mode: String? = null,
    @SerializedName("mirror_enabled") val mirrorEnabled: Boolean? = null,
    @SerializedName("running") val running: Boolean? = null,
    @SerializedName("connected") val connected: Boolean? = null,
    @SerializedName("last_scan") val lastScan: String? = null,
    @SerializedName("bot_start") val botStart: String? = null,
    @SerializedName("health") val health: String? = null,
    @SerializedName("balance") val balance: Double? = null,
    @SerializedName("peak_balance") val peakBalance: Double? = null,
    @SerializedName("drawdown_pct") val drawdownPct: Double? = null,
    @SerializedName("open_positions") val openPositions: Int? = null,
    @SerializedName("total_trades") val totalTrades: Int? = null,
    @SerializedName("paused") val paused: Boolean? = null,
    @SerializedName("halt_reason") val haltReason: String? = null,
    @SerializedName("error") val error: String? = null
)

data class DashboardResponse(
    @SerializedName("bot") val bot: BotStatus? = null,
    @SerializedName("portfolio") val portfolio: Portfolio? = null,
    @SerializedName("performance") val performance: Performance? = null,
    @SerializedName("signals") val signals: SignalSummary? = null,
    @SerializedName("error") val error: String? = null
)

data class Portfolio(
    @SerializedName("balance") val balance: Double? = null,
    @SerializedName("peak_balance") val peakBalance: Double? = null,
    @SerializedName("drawdown_pct") val drawdownPct: Double? = null,
    @SerializedName("daily_pnl") val dailyPnl: Double? = null,
    @SerializedName("daily_pnl_pct") val dailyPnlPct: Double? = null,
    @SerializedName("portfolio_heat") val portfolioHeat: Double? = null,
    @SerializedName("consecutive_loss") val consecutiveLoss: Int? = null,
    @SerializedName("trading_halted") val tradingHalted: Boolean? = null,
    @SerializedName("open_positions") val openPositions: Int? = null,
    @SerializedName("max_positions") val maxPositions: Int? = null,
    @SerializedName("total_trades") val totalTrades: Int? = null
)

data class Performance(
    @SerializedName("total_trades") val totalTrades: Int? = null,
    @SerializedName("wins") val wins: Int? = null,
    @SerializedName("losses") val losses: Int? = null,
    @SerializedName("win_rate") val winRate: Double? = null,
    @SerializedName("total_pnl_usd") val totalPnlUsd: Double? = null,
    @SerializedName("profit_factor") val profitFactor: Double? = null,
    @SerializedName("equity_curve") val equityCurve: List<EquityPoint>? = null,
    @SerializedName("pnl_pct_7d") val pnlPct7d: Double? = null,
    @SerializedName("error") val error: String? = null
)

data class EquityPoint(
    @SerializedName("time") val time: String? = null,
    @SerializedName("balance") val balance: Double? = null
)

data class SignalSummary(
    @SerializedName("total") val total: Int? = null,
    @SerializedName("buy") val buy: Int? = null,
    @SerializedName("sell") val sell: Int? = null,
    @SerializedName("avg_wr") val avgWr: Double? = null,
    @SerializedName("avg_score") val avgScore: Double? = null
)

data class Signal(
    @SerializedName("id") val id: Long? = null,
    @SerializedName("timestamp") val timestamp: String? = null,
    @SerializedName("sent") val sent: Int? = null,
    @SerializedName("momentum") val momentum: Double? = null,
    @SerializedName("symbol") val symbol: String? = null,
    @SerializedName("timeframe") val timeframe: String? = null,
    @SerializedName("signal") val signal: String? = null,
    @SerializedName("price") val price: Double? = null,
    @SerializedName("entry") val entry: Double? = null,
    @SerializedName("sl") val sl: Double? = null,
    @SerializedName("tp1") val tp1: Double? = null,
    @SerializedName("tp2") val tp2: Double? = null,
    @SerializedName("tp3") val tp3: Double? = null,
    @SerializedName("rr_ratio") val rrRatio: Double? = null,
    @SerializedName("confidence") val confidence: Double? = null,
    @SerializedName("score") val score: Double? = null,
    @SerializedName("win_rate") val winRate: Double? = null,
    @SerializedName("reason") val reason: String? = null,
    @SerializedName("status") val status: String? = null,
    @SerializedName("candle_pattern") val candlePattern: String? = null,
    @SerializedName("support") val support: Double? = null,
    @SerializedName("resistance") val resistance: Double? = null,
    @SerializedName("vol_ratio") val volRatio: Double? = null,
    @SerializedName("rsi") val rsi: Double? = null
)

data class Trade(
    @SerializedName("id") val id: Long? = null,
    @SerializedName("pair") val pair: String? = null,
    @SerializedName("timeframe") val timeframe: String? = null,
    @SerializedName("signal") val signal: String? = null,
    @SerializedName("entry") val entry: Double? = null,
    @SerializedName("sl") val sl: Double? = null,
    @SerializedName("exit_price") val exitPrice: Double? = null,
    @SerializedName("pnl_pct") val pnlPct: Double? = null,
    @SerializedName("pnl_usd") val pnlUsd: Double? = null,
    @SerializedName("result") val result: String? = null,
    @SerializedName("opened_at") val openedAt: String? = null,
    @SerializedName("closed_at") val closedAt: String? = null,
    @SerializedName("fees") val fees: Double? = null,
    @SerializedName("duration_min") val durationMin: Long? = null,
    @SerializedName("entry_reason") val entryReason: String? = null,
    @SerializedName("exit_reason") val exitReason: String? = null,
    @SerializedName("strategy") val strategy: String? = null
)

data class TradesResponse(
    @SerializedName("trades") val trades: List<Trade>? = null,
    @SerializedName("total") val total: Int? = null,
    @SerializedName("error") val error: String? = null
)

data class MarketAnalysis(
    @SerializedName("regime") val regime: String? = null,
    @SerializedName("bullish") val bullish: Boolean? = null,
    @SerializedName("bearish") val bearish: Boolean? = null,
    @SerializedName("sideways") val sideways: Boolean? = null,
    @SerializedName("btc_trend") val btcTrend: String? = null,
    @SerializedName("btc_strength") val btcStrength: String? = null,
    @SerializedName("btc_price") val btcPrice: Double? = null,
    @SerializedName("btc_adx") val btcAdx: Double? = null,
    @SerializedName("fear_greed_value") val fearGreedValue: Int? = null,
    @SerializedName("fear_greed_label") val fearGreedLabel: String? = null,
    @SerializedName("allow_buy") val allowBuy: Boolean? = null,
    @SerializedName("allow_sell") val allowSell: Boolean? = null,
    @SerializedName("summary") val summary: String? = null,
    @SerializedName("ai_explanation") val aiExplanation: String? = null,
    @SerializedName("error") val error: String? = null
)

data class RiskStatus(
    @SerializedName("health") val health: String? = null,
    @SerializedName("balance") val balance: Double? = null,
    @SerializedName("peak_balance") val peakBalance: Double? = null,
    @SerializedName("drawdown_pct") val drawdownPct: Double? = null,
    @SerializedName("daily_pnl") val dailyPnl: Double? = null,
    @SerializedName("daily_pnl_pct") val dailyPnlPct: Double? = null,
    @SerializedName("portfolio_heat") val portfolioHeat: Double? = null,
    @SerializedName("consecutive_loss") val consecutiveLoss: Int? = null,
    @SerializedName("trading_halted") val tradingHalted: Boolean? = null,
    @SerializedName("halt_reason") val haltReason: String? = null,
    @SerializedName("open_positions") val openPositions: Int? = null,
    @SerializedName("max_positions") val maxPositions: Int? = null,
    @SerializedName("total_trades") val totalTrades: Int? = null,
    @SerializedName("limits") val limits: RiskLimits? = null,
    @SerializedName("error") val error: String? = null
)

data class RiskLimits(
    @SerializedName("max_drawdown_pct") val maxDrawdownPct: Double? = null,
    @SerializedName("max_daily_loss_pct") val maxDailyLossPct: Double? = null,
    @SerializedName("max_heat_pct") val maxHeatPct: Double? = null,
    @SerializedName("max_consecutive_loss") val maxConsecutiveLoss: Int? = null
)

data class ControlResult(
    @SerializedName("ok") val ok: Boolean? = null,
    @SerializedName("action") val action: String? = null,
    @SerializedName("error") val error: String? = null
)
