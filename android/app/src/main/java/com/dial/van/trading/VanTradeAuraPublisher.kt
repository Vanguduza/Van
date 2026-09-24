package com.dial.van.trading

import com.dial.van.visual.VanLiveVisualState
import com.dial.van.visual.VanTradeAuraPolicy
import com.dial.van.visual.VanTradeSemantic
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Aura Rev 2 — the trading aura is always on (owner request), not just while the trading
 * screen is open.
 *
 * One app-wide reader polls the portfolio and publishes the classified trade state to
 * [VanLiveVisualState]. Whoever needs it *holds* it: the trading screen while it is composed,
 * the floating overlay while VAN is visible (screen on, attached). With no holder it stops and
 * clears the field, so the gateway is never polled with the screen off.
 *
 * Holders share one loop, so opening the trading screen over the overlay does not double the
 * polling; it only makes the reader strict ([VanTradeAuraPolicy]).
 */
object VanTradeAuraPublisher {

    /** How often VAN re-reads the portfolio: fast enough that a stop firing reaches the field
     * promptly, slow enough that it is not a poll loop against the gateway. */
    const val POLL_MS = 6_000L

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val holders = HashMap<String, Boolean>()   // holder -> strict
    private var repository: TradingRepository? = null
    private var job: Job? = null
    private var published: VanTradeSemantic? = null

    @Synchronized
    fun acquire(holder: String, repo: TradingRepository, strict: Boolean) {
        holders[holder] = strict
        if (repository == null) repository = repo
        if (job?.isActive != true) {
            // A fresh reader republishes from scratch rather than assuming the field is current.
            published = null
            job = scope.launch { loop() }
        }
    }

    @Synchronized
    fun release(holder: String) {
        if (holders.remove(holder) == null) return
        if (holders.isEmpty()) {
            job?.cancel()
            job = null
            repository = null
            published = null
            VanLiveVisualState.tradeSemantic(null)
        }
    }

    @Synchronized
    private fun snapshot(): Pair<TradingRepository?, Boolean> = repository to holders.values.any { it }

    private suspend fun loop() {
        while (true) {
            val (repo, strict) = snapshot()
            if (repo == null) return
            val signals = when (val loaded = repo.portfolio()) {
                is Loaded.Ready -> loaded.value.toTradeSignals()
                else -> null
            }
            synchronized(this) {
                // Under the same lock as release(): once the last holder has gone and the field
                // is cleared, a read that was already in flight cannot put a stale trade back.
                if (holders.isEmpty()) return
                val next = VanTradeAuraPolicy.resolve(signals, published, strict)
                // Publish only on change: every publish restarts VAN's state clock, and an
                // always-on reader must not do that every few seconds all day. (The call only
                // posts to the main thread, so holding the lock across it is cheap.)
                if (next != published) {
                    published = next
                    VanLiveVisualState.tradeSemantic(next)
                }
            }
            delay(POLL_MS)
        }
    }
}
