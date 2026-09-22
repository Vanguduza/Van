package com.dial.van.command

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Chat
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.MenuBook
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.ShowChart
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationRail
import androidx.compose.material3.NavigationRailItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.dial.van.VanApplication
import com.dial.van.command.attention.AttentionRoute
import com.dial.van.command.connected.ConnectedRoute
import com.dial.van.command.home.HomeRoute
import com.dial.van.command.modules.BrowserEscalationsPage
import com.dial.van.command.modules.BrowserPolicyPage
import com.dial.van.command.modules.BrowserSessionsPage
import com.dial.van.command.modules.BrowserTasksPage
import com.dial.van.command.modules.BrowserAutomationModule
import com.dial.van.command.nav.VanNavModel
import com.dial.van.command.nav.VanRoute
import com.dial.van.command.settings.SettingsNotificationsRoute
import com.dial.van.command.settings.SettingsRoute
import com.dial.van.command.settings.SettingsVoiceRoute
import com.dial.van.command.work.WorkActivityRoute
import com.dial.van.command.work.WorkRoute
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.VanDensity
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.VanPressable
import com.dial.van.visual.VanGlassTokens
import com.dial.van.visual.VanPresence
import com.dial.van.visual.VanTheme
import com.dial.van.visual.rememberVanEffectBudget

/**
 * The Command Centre shell: the Activity, the theme, and the one `NavHost` DNA §4 describes.
 *
 * Replaces the flat 17-module grid (`CommandModule`/`CommandNav`) with the typed route graph
 * in `command/nav/`. Adaptive nav (DNA §4): a bottom bar with the five primaries — Home,
 * Attention, Work, Trading, Memory — at [VanDensity.Regular], a side rail at [VanDensity.Wide],
 * and a "More" sheet for Projects/Connected/Settings. Deep links: `van://<route>`.
 */
class CommandCentreActivity : FragmentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val app = application as VanApplication
        // Legacy callers (the overlay's "module" extra) and this build's own deep links
        // (`intent.data`, e.g. from a notification) both resolve through VanNavModel, never
        // to a raw string handed straight to NavHost.
        val fromData = intent?.data?.toString()?.let(VanNavModel::deepLink)
        val fromExtra = VanNavModel.startDestination(intent.getStringExtra(EXTRA_MODULE))
        val initial = fromData ?: fromExtra

        setContent {
            VanTheme {
                Box(
                    modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background),
                ) {
                    CommandCentreScreen(app, initial)
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        // A deep link arriving while the Activity is already resident (`launchMode
        // singleTop`) has nowhere to hand its route to the composition that already ran
        // `onCreate` — that composition owns its own NavController. Reopening as a fresh
        // task keeps the one restoration path (VanNavModel via the constructor's intent)
        // rather than a second one threaded in after the fact.
        val route = intent.data?.toString()?.let(VanNavModel::deepLink)
        if (route != null) {
            startActivity(
                Intent(this, CommandCentreActivity::class.java)
                    .putExtra(EXTRA_MODULE, route)
                    .setData(intent.data),
            )
        }
    }

    companion object {
        const val EXTRA_MODULE = "module"

        fun deepLinkIntent(context: android.content.Context, route: String): Intent =
            Intent(context, CommandCentreActivity::class.java)
                .setData(Uri.parse(VanRoute.toDeepLink(route)))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    }
}

private data class NavDestination(val route: String, val label: String, val icon: androidx.compose.ui.graphics.vector.ImageVector)

private val PRIMARY_DESTINATIONS = listOf(
    NavDestination(VanRoute.HOME, "Home", Icons.Filled.Home),
    NavDestination(VanRoute.ATTENTION, "Attention", Icons.Filled.Notifications),
    NavDestination(VanRoute.WORK, "Work", Icons.Filled.Chat),
    NavDestination(VanRoute.TRADING, "Trading", Icons.Filled.ShowChart),
    NavDestination(VanRoute.MEMORY, "Memory", Icons.Filled.MenuBook),
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun CommandCentreScreen(app: VanApplication, initial: String) {
    val viewModel: CommandCentreViewModel = viewModel()
    // Synchronous, not a LaunchedEffect: NavHost reads `viewModel.startDestination` once, at
    // its own first composition, so the fresh-vs-restored decision has to be settled before
    // that — a `start` called from a side effect would run one frame too late.
    remember(viewModel) { viewModel.also { it.start(initial) } }
    val nav = rememberNavController()
    val currentRoute by viewModel.currentRoute.collectAsState()
    var moreSheetOpen by remember { mutableStateOf(false) }

    LaunchedEffect(nav) {
        nav.currentBackStackEntryFlow.collect { entry ->
            entry.destination.route?.let { viewModel.onRouteChanged(it) }
        }
    }

    fun navigateTo(route: String) {
        nav.navigate(route) {
            popUpTo(viewModel.startDestination) { saveState = true }
            launchSingleTop = true
            restoreState = true
        }
    }

    val tokens = LocalVanTokens.current
    val wide = tokens.density == VanDensity.Wide

    Scaffold(
        containerColor = Color.Transparent,
        bottomBar = {
            if (!wide) {
                CommandBottomBar(currentRoute, onSelect = ::navigateTo, onMore = { moreSheetOpen = true })
            }
        },
    ) { padding ->
        Row(modifier = Modifier.fillMaxSize().padding(padding)) {
            if (wide) {
                CommandSideRail(currentRoute, onSelect = ::navigateTo, onMore = { moreSheetOpen = true })
            }
            Box(modifier = Modifier.fillMaxSize()) {
                NavHost(navController = nav, startDestination = viewModel.startDestination) {
                    composable(VanRoute.HOME) {
                        HomeRoute(
                            app = app,
                            onOpenAttention = { navigateTo(VanRoute.ATTENTION) },
                            onOpenWork = { navigateTo(VanRoute.WORK) },
                            onOpenTrading = { navigateTo(VanRoute.TRADING) },
                        )
                    }
                    composable(VanRoute.ATTENTION) { AttentionRoute(app) }
                    composable(VanRoute.WORK) {
                        WorkRoute(
                            app = app,
                            onOpenBrowser = { nav.navigate(VanRoute.WORK_BROWSER) },
                            onOpenActivity = { nav.navigate(VanRoute.WORK_ACTIVITY) },
                        )
                    }
                    composable(VanRoute.WORK_ACTIVITY) {
                        WorkActivityRoute(app, onBack = { nav.popBackStack() })
                    }
                    composable(VanRoute.WORK_BROWSER) {
                        val glass = legacyGlass(app)
                        BrowserAutomationModule(
                            app = app,
                            glass = glass,
                            onOpenEscalations = { nav.navigate(VanRoute.WORK_BROWSER_ESCALATIONS) },
                            onOpenTasks = { nav.navigate(VanRoute.WORK_BROWSER_TASKS) },
                            onOpenSessions = { nav.navigate(VanRoute.WORK_BROWSER_SESSIONS) },
                            onOpenPolicy = { nav.navigate(VanRoute.WORK_BROWSER_POLICY) },
                        )
                    }
                    composable(VanRoute.WORK_BROWSER_TASKS) {
                        BrowserTasksPage(app, legacyGlass(app), back = { nav.popBackStack() })
                    }
                    composable(VanRoute.WORK_BROWSER_ESCALATIONS) {
                        BrowserEscalationsPage(app, legacyGlass(app), back = { nav.popBackStack() })
                    }
                    composable(VanRoute.WORK_BROWSER_SESSIONS) {
                        BrowserSessionsPage(app, legacyGlass(app), back = { nav.popBackStack() })
                    }
                    composable(VanRoute.WORK_BROWSER_POLICY) {
                        BrowserPolicyPage(app, legacyGlass(app), back = { nav.popBackStack() })
                    }
                    composable(
                        VanRoute.WORK_MISSION_TEMPLATE,
                        arguments = listOf(navArgument("missionId") { type = NavType.StringType }),
                    ) {
                        // The mission detail surface itself is the expandable row on Work
                        // (`TimelineRail` on expand); this route exists so a deep link or a
                        // notification can land the owner directly on Work with the intent
                        // named, without inventing a second detail screen.
                        WorkRoute(
                            app = app,
                            onOpenBrowser = { nav.navigate(VanRoute.WORK_BROWSER) },
                            onOpenActivity = { nav.navigate(VanRoute.WORK_ACTIVITY) },
                        )
                    }
                    composable(VanRoute.TRADING) {
                        // The trading worker's own destination (owned by `trading/**`, not
                        // this worker). See this worker's report: `TradingRoute` does not
                        // exist yet, so this call site is a forward reference the trading
                        // worker's change makes real.
                        com.dial.van.trading.ui.TradingRoute(app, onBack = { nav.popBackStack() })
                    }
                    composable(VanRoute.MEMORY) {
                        // Owned by the memory/projects worker (`com.dial.van.memory`).
                        com.dial.van.memory.MemoryRoute(app, onBack = { nav.popBackStack() })
                    }
                    composable(VanRoute.PROJECTS) {
                        // Owned by the memory/projects worker (`com.dial.van.projects`).
                        com.dial.van.projects.ProjectsRoute(app) { projectId ->
                            nav.navigate(VanRoute.projectRoute(projectId))
                        }
                    }
                    composable(
                        VanRoute.PROJECT_DETAIL_TEMPLATE,
                        arguments = listOf(navArgument("projectId") { type = NavType.StringType }),
                    ) { entry ->
                        val projectId = entry.arguments?.getString("projectId") ?: ""
                        com.dial.van.projects.ProjectDetailRoute(
                            app = app,
                            projectId = projectId,
                            onBack = { nav.popBackStack() },
                            onAskVan = { text ->
                                app.commandController.selectProject(projectId)
                                app.commandController.submitText(text, com.dial.van.control.VanCommandSource.PROJECT)
                                navigateTo(VanRoute.WORK)
                            },
                        )
                    }
                    composable(VanRoute.CONNECTED) { ConnectedRoute(app) }
                    composable(VanRoute.SETTINGS) {
                        SettingsRoute(
                            app = app,
                            onOpenVoice = { nav.navigate(VanRoute.SETTINGS_VOICE) },
                            onOpenNotifications = { nav.navigate(VanRoute.SETTINGS_NOTIFICATIONS) },
                        )
                    }
                    composable(VanRoute.SETTINGS_VOICE) {
                        SettingsVoiceRoute(app, onBack = { nav.popBackStack() })
                    }
                    composable(VanRoute.SETTINGS_NOTIFICATIONS) {
                        SettingsNotificationsRoute(app, onBack = { nav.popBackStack() })
                    }
                }
            }
        }
    }

    if (moreSheetOpen) {
        MoreSheet(
            onDismiss = { moreSheetOpen = false },
            onSelect = { route ->
                moreSheetOpen = false
                navigateTo(route)
            },
        )
    }
}

@Composable
private fun CommandBottomBar(currentRoute: String, onSelect: (String) -> Unit, onMore: () -> Unit) {
    val tokens = LocalVanTokens.current
    NavigationBar(containerColor = tokens.color.surface1) {
        PRIMARY_DESTINATIONS.forEach { destination ->
            NavigationBarItem(
                selected = currentRoute == destination.route,
                onClick = { onSelect(destination.route) },
                icon = { Icon(destination.icon, contentDescription = destination.label) },
                label = { Text(destination.label, style = tokens.type.label) },
            )
        }
        NavigationBarItem(
            selected = currentRoute in VanRoute.MORE,
            onClick = onMore,
            icon = { Icon(Icons.Filled.MoreVert, contentDescription = "More") },
            label = { Text("More", style = tokens.type.label) },
        )
    }
}

@Composable
private fun CommandSideRail(currentRoute: String, onSelect: (String) -> Unit, onMore: () -> Unit) {
    val tokens = LocalVanTokens.current
    NavigationRail(containerColor = tokens.color.surface1, modifier = Modifier.fillMaxHeight()) {
        PRIMARY_DESTINATIONS.forEach { destination ->
            NavigationRailItem(
                selected = currentRoute == destination.route,
                onClick = { onSelect(destination.route) },
                icon = { Icon(destination.icon, contentDescription = destination.label) },
                label = { Text(destination.label, style = tokens.type.label) },
            )
        }
        NavigationRailItem(
            selected = currentRoute in VanRoute.MORE,
            onClick = onMore,
            icon = { Icon(Icons.Filled.MoreVert, contentDescription = "More") },
            label = { Text("More", style = tokens.type.label) },
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MoreSheet(onDismiss: () -> Unit, onSelect: (String) -> Unit) {
    val tokens = LocalVanTokens.current
    val sheetState = rememberModalBottomSheetState()
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = tokens.color.surfaceAcrylic,
        contentColor = tokens.color.textPrimary,
    ) {
        Column(modifier = Modifier.fillMaxWidth().padding(horizontal = tokens.space.space5, vertical = tokens.space.space3)) {
            SectionHeader("More")
            listOf(
                Triple(VanRoute.PROJECTS, "Projects", "Health, phase, blockers, next actions"),
                Triple(VanRoute.CONNECTED, "Connected", "Google planes, Hermes, knowledge readiness"),
                Triple(VanRoute.SETTINGS, "Settings & Devices", "Pairing, permissions, voice, notifications"),
            ).forEach { (route, title, detail) ->
                VanPressable(
                    onClick = { onSelect(route) },
                    modifier = Modifier.fillMaxWidth().padding(vertical = tokens.space.space2),
                    contentDescription = "$title. $detail.",
                ) {
                    Column(modifier = Modifier.fillMaxWidth()) {
                        Text(title, style = tokens.type.headline, color = tokens.color.textPrimary)
                        Text(detail, style = tokens.type.body, color = tokens.color.textSecondary)
                    }
                }
            }
        }
    }
}

/**
 * The one place `visual/`'s glass style is still built, for the legacy Browser & Automation
 * children this rebuild reuses rather than rewrites (they predate the design system and take
 * a `VanGlassStyle`, not tokens).
 */
@Composable
private fun legacyGlass(app: VanApplication): com.dial.van.visual.VanGlassStyle {
    val degraded by app.degradedModeStore.state.collectAsState()
    val cue = VanPresence.cue(degraded)
    val budget = rememberVanEffectBudget()
    return VanGlassTokens.forState(state = cue.durableState, panel = true, liveBlurAvailable = false, budget = budget)
}
