package com.dial.van.overlay

import android.app.Application
import com.dial.van.VanApplication
import com.dial.van.trading.TradingRepository
import com.dial.van.trading.VanTradeAuraPublisher

/**
 * Aura Rev 2 (CF-D-08-REV1) — the trading aura is always on while VAN is on screen.
 *
 * The floating overlay holds the shared trading reader while it animates and lets go when
 * paused or destroyed, so the gateway is never polled with the screen off. It holds it
 * leniently: in the background an unreadable ledger only alarms if money was at stake
 * ([com.dial.van.visual.VanTradeAuraPolicy]). Unpaired devices have no ledger to read, so they
 * do not hold it.
 */
internal object OverlayTradeAura {
    private const val HOLDER = "floating-overlay"

    fun hold(application: Application, visible: Boolean) {
        val app = application as? VanApplication
        if (visible && app != null && runCatching { app.deviceIsBound() }.getOrDefault(false)) {
            VanTradeAuraPublisher.acquire(HOLDER, TradingRepository(app.gatewayClient), strict = false)
        } else {
            VanTradeAuraPublisher.release(HOLDER)
        }
    }
}
