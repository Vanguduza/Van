package com.dial.van.trading

import android.content.Context
import android.content.Intent
import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.fragment.app.FragmentActivity
import com.dial.van.VanApplication
import com.dial.van.trading.ui.TradingRoute
import com.dial.van.visual.VanTheme

/**
 * Legacy activity entry point for the Trading destination (DNA §4). All of its screens now
 * live in one `NavHost` hosted by [TradingRoute]; this activity's whole job is to host that
 * composable inside [VanTheme] and forward old deep-link intents.
 *
 * `EXTRA_ROUTE` is accepted for compatibility with existing deep links/shortcuts but is not
 * threaded further yet — [TradingRoute] always starts at its overview destination. A caller
 * that needs a specific inner route (e.g. a position) should prefer
 * `TradingCommandCentreActivity` staying on Overview and using in-app navigation, since the
 * inner `NavHost`'s graph is private to [TradingRoute].
 */
class TradingCommandCentreActivity : FragmentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val app = application as VanApplication
        setContent {
            VanTheme {
                TradingRoute(app, onBack = { finish() })
            }
        }
    }

    companion object {
        const val EXTRA_ROUTE = "route"

        /** Kept for `overlay/`'s existing call sites (`VanOverlayWorkboards.kt`); this activity
         * always opens on the overview destination regardless of the value passed. */
        const val ROUTE_OVERVIEW = "overview"

        fun intent(context: Context, route: String = ROUTE_OVERVIEW): Intent =
            Intent(context, TradingCommandCentreActivity::class.java)
                .putExtra(EXTRA_ROUTE, route)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

        fun tradeRoute(tradeIntentId: String) = "trade/$tradeIntentId"
        fun tradesRoute(view: TradeView) = "trades/${view.name}"
    }
}
