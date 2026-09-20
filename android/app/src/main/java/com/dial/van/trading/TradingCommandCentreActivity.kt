package com.dial.van.trading

import android.content.Context
import android.content.Intent
import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountBalance
import androidx.compose.material.icons.filled.Chat
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Shield
import androidx.compose.material.icons.filled.ShowChart
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.sp
import androidx.fragment.app.FragmentActivity
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.dial.van.VanApplication
import com.dial.van.command.CommandCentreActivity
import com.dial.van.visual.VanLiveVisualState
import com.dial.van.visual.VanTradeSemantic
import com.dial.van.visual.VanTradeSemantics
import kotlinx.coroutines.delay
import com.dial.van.trading.ui.AccountOnboardingScreen
import com.dial.van.trading.ui.AccountsScreen
import com.dial.van.trading.ui.CognitionScreen
import com.dial.van.trading.ui.InstrumentScreen
import com.dial.van.trading.ui.OverviewScreen
import com.dial.van.trading.ui.RiskScreen
import com.dial.van.trading.ui.StrategiesScreen
import com.dial.van.trading.ui.ScreenEnv
import com.dial.van.trading.ui.TradeDetailScreen
import com.dial.van.trading.ui.TradesScreen
import com.dial.van.trading.ui.TradingNav
import com.dial.van.visual.VanGlassTokens
import com.dial.van.visual.VanTheme
import com.dial.van.visual.VanPresence
import com.dial.van.visual.rememberVanEffectBudget

/**
 * Van Trading Command Center (blueprint Rev 1 → implemented per Rev 5 Part I).
 *
 * One contextual trading system, not a collection of dashboards: every screen reads the same
 * gateway read models of the VATI ledger, keeps the account scope and instrument in the
 * navigation state, and can hand the context to Van (Command Centre chat). Nothing on any
 * screen can place, size, modify or cancel a trade.
 *
 * Routes: overview · trades/{view} · trade/{id} · instrument/{symbol} · risk · accounts
 */
class TradingCommandCentreActivity : FragmentActivity() {

    @OptIn(ExperimentalMaterial3Api::class)
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val app = application as VanApplication
        val startRoute = intent?.getStringExtra(EXTRA_ROUTE) ?: ROUTE_OVERVIEW
        setContent {
            // P3-AND-008 — the third inline `darkColorScheme`. One theme now.
            VanTheme {
                val nav = rememberNavController()
                val degraded = app.degradedModeStore.snapshot()
                val cue = VanPresence.cue(degraded)
                val budget = rememberVanEffectBudget()
                val glass = VanGlassTokens.forState(state = cue.durableState, panel = true, liveBlurAvailable = false, budget = budget)
                val env = remember(cue.durableState) { ScreenEnv(TradingRepository(app.gatewayClient), glass, budget, VanPresence.visualState(cue), cue.headline) { System.currentTimeMillis() } }
                // P1-AURA-003 — the trading system's route into VAN's visual state. It reads
                // the same portfolio read model the screens render, classifies it through the
                // pure classifier, and publishes. The `remember(app)` repository is the one the
                // screens use, so the field and the numbers cannot disagree.
                PublishTradeSemantic(env.repo)
                val tnav = TradingNav(
                    openTrade = { nav.navigate("trade/$it") },
                    openInstrument = { nav.navigate("instrument/$it") },
                    openTrades = { nav.navigate("trades/${it.name}") },
                    openRisk = { nav.navigate(ROUTE_RISK) },
                    openAccounts = { nav.navigate(ROUTE_ACCOUNTS) },
                    openStrategies = { nav.navigate(ROUTE_STRATEGIES) },
                    openCognition = { nav.navigate(ROUTE_COGNITION) },
                    openChat = { startActivity(Intent(this@TradingCommandCentreActivity, CommandCentreActivity::class.java)) },
                )
                Box(modifier = Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Color(0xFF060A14), Color(0xFF0B1424), Color(0xFF04070F))))) {
                    Scaffold(
                        containerColor = Color.Transparent,
                        topBar = { TopAppBar(title = { Text("Van Trading", fontSize = 18.sp) }, colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.Transparent, titleContentColor = Color.White)) },
                        bottomBar = { TradingBottomBar(nav) },
                    ) { padding ->
                        NavHost(navController = nav, startDestination = ROUTE_OVERVIEW) {
                            composable(ROUTE_OVERVIEW) { OverviewScreen(env, tnav, padding) }
                            composable("trades/{view}", arguments = listOf(navArgument("view") { type = NavType.StringType; defaultValue = TradeView.CURRENT.name })) { entry ->
                                TradesScreen(env, tnav, padding, runCatching { TradeView.valueOf(entry.arguments?.getString("view") ?: "CURRENT") }.getOrDefault(TradeView.CURRENT))
                            }
                            composable("trade/{id}", arguments = listOf(navArgument("id") { type = NavType.StringType })) { entry -> TradeDetailScreen(env, tnav, padding, entry.arguments?.getString("id") ?: "") }
                            composable("instrument/{symbol}", arguments = listOf(navArgument("symbol") { type = NavType.StringType })) { entry -> InstrumentScreen(env, tnav, padding, entry.arguments?.getString("symbol") ?: "") }
                            composable(ROUTE_RISK) { RiskScreen(env, tnav, padding) }
                            composable(ROUTE_ACCOUNTS) { AccountsScreen(env, padding, onAdd = { nav.navigate(ROUTE_ACCOUNT_ADD) }) }
                            composable(ROUTE_STRATEGIES) { StrategiesScreen(env, padding, app) }
                            composable(ROUTE_COGNITION) { CognitionScreen(env, padding) }
                            composable(ROUTE_ACCOUNT_ADD) { AccountOnboardingScreen(env, padding, app) { nav.popBackStack() } }
                        }
                        // Deep links from the overlay / Command Centre land on the requested object once the graph exists.
                        if (startRoute != ROUTE_OVERVIEW) {
                            androidx.compose.runtime.LaunchedEffect(startRoute) { nav.navigate(startRoute) }
                        }
                    }
                }
            }
        }
    }

    /**
     * Polls the portfolio read model and publishes VAN's trade semantic.
     *
     * `DisposableEffect` clears it on the way out: VAN should not keep showing a trade field
     * because the owner once opened this screen. Failure to load publishes
     * [VanTradeSemantic.UNKNOWN] rather than nothing — a gateway VAN cannot reach is not a
     * reason to show a calm field, it is the reason to show that VAN cannot see.
     */
    @Composable
    private fun PublishTradeSemantic(repo: TradingRepository) {
        DisposableEffect(repo) {
            onDispose { VanLiveVisualState.tradeSemantic(null) }
        }
        LaunchedEffect(repo) {
            while (true) {
                val semantic = when (val loaded = repo.portfolio()) {
                    is Loaded.Ready -> VanTradeSemantics.classify(loaded.value.toTradeSignals())
                    else -> VanTradeSemantic.UNKNOWN
                }
                VanLiveVisualState.tradeSemantic(semantic)
                delay(TRADE_SEMANTIC_POLL_MS)
            }
        }
    }

    @Composable
    private fun TradingBottomBar(nav: NavHostController) {
        val entry by nav.currentBackStackEntryAsState()
        val route = entry?.destination?.route ?: ROUTE_OVERVIEW
        NavigationBar(containerColor = Color(0xFF0B1424).copy(alpha = 0.92f)) {
            listOf(
                Triple(ROUTE_OVERVIEW, "Overview", Icons.Default.Home),
                Triple("trades/{view}", "Trades", Icons.Default.ShowChart),
                Triple(ROUTE_RISK, "Risk", Icons.Default.Shield),
                Triple(ROUTE_ACCOUNTS, "Accounts", Icons.Default.AccountBalance),
                Triple("chat", "Van", Icons.Default.Chat),
            ).forEach { (r, label, icon) ->
                NavigationBarItem(
                    selected = route == r,
                    onClick = {
                        when (r) {
                            "chat" -> startActivity(Intent(this@TradingCommandCentreActivity, CommandCentreActivity::class.java))
                            "trades/{view}" -> nav.navigate("trades/${TradeView.CURRENT.name}") { launchSingleTop = true }
                            else -> nav.navigate(r) { launchSingleTop = true; popUpTo(ROUTE_OVERVIEW) }
                        }
                    },
                    icon = { Icon(icon, contentDescription = label) },
                    label = { Text(label, fontSize = 10.sp) },
                    colors = NavigationBarItemDefaults.colors(selectedIconColor = Color(VanGlassTokens.ACCENT_CYAN), selectedTextColor = Color(VanGlassTokens.ACCENT_CYAN), unselectedIconColor = Color(0xFF9AA7B6), unselectedTextColor = Color(0xFF9AA7B6), indicatorColor = Color(VanGlassTokens.ACCENT_CYAN).copy(alpha = 0.15f)),
                )
            }
        }
    }

    companion object {
        /**
         * How often VAN re-reads the portfolio for its visual state. Six seconds: fast
         * enough that a stop firing reaches the field while the owner is still looking at
         * the screen, slow enough that it is not a poll loop against the gateway.
         */
        const val TRADE_SEMANTIC_POLL_MS = 6_000L

        const val EXTRA_ROUTE = "route"
        const val ROUTE_OVERVIEW = "overview"
        const val ROUTE_RISK = "risk"
        const val ROUTE_ACCOUNTS = "accounts"
        const val ROUTE_STRATEGIES = "strategies"
        const val ROUTE_COGNITION = "cognition"
        const val ROUTE_ACCOUNT_ADD = "accounts/add"

        fun intent(context: Context, route: String = ROUTE_OVERVIEW): Intent =
            Intent(context, TradingCommandCentreActivity::class.java).putExtra(EXTRA_ROUTE, route).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

        fun tradeRoute(tradeIntentId: String) = "trade/$tradeIntentId"
        fun tradesRoute(view: TradeView) = "trades/${view.name}"
    }
}
