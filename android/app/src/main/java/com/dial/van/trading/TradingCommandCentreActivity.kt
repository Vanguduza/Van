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
 * `EXTRA_ROUTE` preserves the overlay's selected view or trade. Unknown links resolve to
 * Overview; trade links use the existing detail screen, which also reads closed trades.
 */
class TradingCommandCentreActivity : FragmentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val app = application as VanApplication
        setContent {
            VanTheme {
                TradingRoute(app, onBack = { finish() }, initialRoute = intent.getStringExtra(EXTRA_ROUTE))
            }
        }
    }

    companion object {
        const val EXTRA_ROUTE = "route"

        /** Default for `overlay/`'s workboard entry points. */
        const val ROUTE_OVERVIEW = "overview"

        fun intent(context: Context, route: String = ROUTE_OVERVIEW): Intent =
            Intent(context, TradingCommandCentreActivity::class.java)
                .putExtra(EXTRA_ROUTE, route)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

        fun tradeRoute(tradeIntentId: String) = "trade/$tradeIntentId"
        fun tradesRoute(view: TradeView) = "trades/${view.name}"
    }
}
