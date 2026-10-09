package com.dial.van.trading

/** Current ledger/control observation; a readable file alone never establishes LIVE. */
data class TradingRuntimeReadModel(
    val ledgerAvailable: Boolean,
    val chainOk: Boolean?,
    val stale: Boolean?,
    val lastEventMs: Long?,
    val staleReason: String?,
    val killSwitchActive: Boolean?,
    val killSwitchTriggers: List<String>,
    val head: String?,
) {
    enum class Freshness { LIVE, STALE, OFFLINE, UNKNOWN }
    fun freshness(nowMs: Long): Freshness = when {
        !ledgerAvailable -> Freshness.OFFLINE
        chainOk != true -> Freshness.UNKNOWN
        stale == true -> Freshness.STALE
        stale != false || lastEventMs == null || lastEventMs <= 0L || lastEventMs > nowMs -> Freshness.UNKNOWN
        nowMs - lastEventMs >= TradingReadModels.LEDGER_STALENESS_MS -> Freshness.STALE
        else -> Freshness.LIVE
    }
    val ownerHaltRecorded: Boolean? get() = when {
        killSwitchActive == null -> null
        killSwitchActive == false -> false
        else -> "OWNER_HALT" in killSwitchTriggers
    }
    companion object {
        fun parse(body: String): TradingRuntimeReadModel? {
            val root = parseObject(body) ?: return null
            val available = root.bool("ledger_available") ?: return null
            return TradingRuntimeReadModel(available, root.bool("chain_ok"), root.bool("ledger_stale"),
                root.long("last_event_ms"), root.str("ledger_stale_reason"), root.bool("kill_switch_active"),
                root.strList("kill_switch_triggers"), root.str("head"))
        }
    }
}
