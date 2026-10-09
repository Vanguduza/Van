package com.dial.van.trading

import com.dial.van.gateway.VanGatewayClient

/** The owner screens share one gateway; a failed section never fabricates an empty ledger. */
class TradingRepository(private val client: VanGatewayClient) {
    private suspend fun <T> load(parse: (String) -> T?, call: suspend () -> String): Loaded<T> =
        loadTradingData(parse, call)

    suspend fun status(): Loaded<TradingRuntimeReadModel> = load(TradingRuntimeReadModel::parse) { client.tradingStatus() }

    suspend fun tickets(): Loaded<TradingTicketList> = load(TradingTicketList::parse) { client.tradingTickets() }

    suspend fun portfolio(): Loaded<PortfolioSummary> = load(PortfolioSummary::parse) { client.tradingPortfolio() }
    suspend fun marketStates(symbol: String? = null): Loaded<List<MarketStateCard>> = load({ MarketStateCard.parseAll(it) }) { client.tradingMarketState(symbol) }
    suspend fun risk(): Loaded<RiskView> = load(RiskView::parse) { client.tradingRisk() }
    suspend fun cognition(): Loaded<CognitionSnapshot> = load(CognitionSnapshot::parse) { client.tradingCognition() }
    suspend fun accounts(): Loaded<List<AccountCard>> = load({ b -> parseObject(b)?.arr("accounts")?.map(AccountCard::from) }) { client.tradingAccounts() }
    suspend fun tradeDetail(id: String): Loaded<TradeDetail> = load(TradeDetail::parse) { client.tradingTradeDetail(id) }
    suspend fun bars(symbol: String, timeframe: String, limit: Int = 300): Loaded<BarSeries> = load(BarSeries::parse) { client.tradingBars(symbol, timeframe, limit) }
    suspend fun trades(view: TradeView): Loaded<List<TradeRow>> = load({ b -> (TradeBookParser.parse(view, b) as? TradeBookState.Ready)?.rows }) { client.tradingTrades(view.query, 100) }

    suspend fun promotionCandidates(): Loaded<List<StrategyPromotionCandidate>> =
        load(StrategyPromotionCandidate::parseAll) { client.tradingPromotionCandidates() }

    // ---------------------------------------------------------- GAP-F-003 intelligence read models
    suspend fun positions(): Loaded<PositionsReadModel> = load(PositionsReadModel::parse) { client.tradingPositions() }
    suspend fun events(limit: Int = 50): Loaded<EventsReadModel> = load(EventsReadModel::parse) { client.tradingEvents(limit) }
    suspend fun potentialTrades(): Loaded<PotentialReadModel> = load(PotentialReadModel::parse) { client.tradingPotential() }
    suspend fun history(limit: Int = 50): Loaded<HistoryReadModel> = load(HistoryReadModel::parse) { client.tradingHistory(limit) }
    suspend fun assessment(): Loaded<AssessmentReadModel> = load(AssessmentReadModel::parse) { client.tradingAssessment() }
}
