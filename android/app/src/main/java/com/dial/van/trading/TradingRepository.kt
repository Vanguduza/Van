package com.dial.van.trading

import com.dial.van.gateway.VanGatewayClient

/** One place that turns gateway text into models and gateway failure into a named state. Never caches as truth. */
sealed class Loaded<out T> {
    data object Loading : Loaded<Nothing>()
    data class Ready<T>(val value: T) : Loaded<T>()
    data class Unavailable(val reason: String) : Loaded<Nothing>()
}

class TradingRepository(private val client: VanGatewayClient) {
    private suspend fun <T> load(parse: (String) -> T?, call: suspend () -> String): Loaded<T> =
        runCatching { call() }.fold(
            onSuccess = { body -> parse(body)?.let { Loaded.Ready(it) } ?: Loaded.Unavailable("Gateway response unreadable") },
            onFailure = { Loaded.Unavailable("Gateway unreachable: ${it.message?.take(80) ?: "no detail"}") },
        )

    suspend fun portfolio(): Loaded<PortfolioSummary> = load(PortfolioSummary::parse) { client.tradingPortfolio() }
    suspend fun marketStates(symbol: String? = null): Loaded<List<MarketStateCard>> = load({ MarketStateCard.parseAll(it) }) { client.tradingMarketState(symbol) }
    suspend fun risk(): Loaded<RiskView> = load(RiskView::parse) { client.tradingRisk() }
    suspend fun accounts(): Loaded<List<AccountCard>> = load({ b -> parseObject(b)?.arr("accounts")?.map(AccountCard::from) }) { client.tradingAccounts() }
    suspend fun tradeDetail(id: String): Loaded<TradeDetail> = load(TradeDetail::parse) { client.tradingTradeDetail(id) }
    suspend fun bars(symbol: String, timeframe: String, limit: Int = 300): Loaded<BarSeries> = load(BarSeries::parse) { client.tradingBars(symbol, timeframe, limit) }
    suspend fun trades(view: TradeView): Loaded<List<TradeRow>> = load({ b -> (TradeBookParser.parse(view, b) as? TradeBookState.Ready)?.rows }) { client.tradingTrades(view.query, 100) }

    suspend fun promotionCandidates(): Loaded<List<StrategyPromotionCandidate>> =
        load(StrategyPromotionCandidate::parseAll) { client.tradingPromotionCandidates() }
    suspend fun promotionCandidates(): Loaded<List<StrategyPromotionCandidate>> = load(StrategyPromotionCandidate::parseAll) { client.tradingPromotionCandidates() }
}
