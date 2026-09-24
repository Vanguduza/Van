package com.dial.van.trading.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountBalance
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.PowerSettingsNew
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.ShowChart
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.fragment.app.FragmentActivity
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.dial.van.VanApplication
import com.dial.van.control.VanCommandSource
import com.dial.van.control.VanMessageRole
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.ApprovalSheet
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel
import com.dial.van.security.BiometricGate
import com.dial.van.trading.TradingHaltAuthority
import com.dial.van.trading.TradingRepository
import com.dial.van.trading.VanTradeAuraPublisher

/** Navigation callbacks the inner destinations need; [TradingRoute] wires them to the NavController. */
class TradingNav(
    val openPositions: () -> Unit,
    val openPosition: (String) -> Unit,
    val openPotential: () -> Unit,
    val openHistory: () -> Unit,
    val openAccounts: () -> Unit,
    val openAccountAdd: () -> Unit,
    val openStrategies: () -> Unit,
    val openCognition: () -> Unit,
    val back: () -> Unit,
)

private const val ROUTE_OVERVIEW = "overview"
private const val ROUTE_POSITIONS = "positions"
private const val ROUTE_POSITION_DETAIL = "positions/{id}"
private const val ROUTE_POTENTIAL = "potential"
private const val ROUTE_HISTORY = "history"
private const val ROUTE_ACCOUNTS = "accounts"
private const val ROUTE_ACCOUNTS_ADD = "accounts/add"
private const val ROUTE_STRATEGIES = "strategies"
private const val ROUTE_COGNITION = "cognition"

/**
 * DNA §4 destination 4, "Trading": `overview → positions → position detail → potential →
 * history → accounts → strategies`, plus `cognition` (Rev 5.1's owner cognition surface,
 * reachable from Overview's VAN assessment panel — not one of DNA's named seven, kept
 * because it is real functionality this worker migrates rather than discards).
 *
 * One [TradingRepository] for the whole destination — every screen reads the same gateway
 * connection. `TradingCommandCentreActivity` (the legacy activity entry point) hosts this
 * composable directly rather than owning its own `NavHost`.
 */
@Composable
fun TradingRoute(app: VanApplication, onBack: () -> Unit) {
    val tokens = LocalVanTokens.current
    val repo = remember(app) { TradingRepository(app.gatewayClient) }
    PublishTradeSemantic(repo)
    val nav = rememberNavController()
    val tnav = remember(nav) {
        TradingNav(
            openPositions = { nav.navigate(ROUTE_POSITIONS) { launchSingleTop = true } },
            openPosition = { id -> nav.navigate("positions/$id") },
            openPotential = { nav.navigate(ROUTE_POTENTIAL) { launchSingleTop = true } },
            openHistory = { nav.navigate(ROUTE_HISTORY) { launchSingleTop = true } },
            openAccounts = { nav.navigate(ROUTE_ACCOUNTS) { launchSingleTop = true } },
            openAccountAdd = { nav.navigate(ROUTE_ACCOUNTS_ADD) },
            openStrategies = { nav.navigate(ROUTE_STRATEGIES) },
            openCognition = { nav.navigate(ROUTE_COGNITION) },
            back = onBack,
        )
    }

    Scaffold(
        containerColor = tokens.color.bgCanvas,
        topBar = { TradingTopBar(nav, onBack, app) },
        bottomBar = { TradingBottomBar(nav) },
    ) { padding ->
        Column(modifier = Modifier.padding(padding)) {
            TradingHaltStatusBar(app)
            NavHost(navController = nav, startDestination = ROUTE_OVERVIEW, modifier = Modifier.weight(1f)) {
                composable(ROUTE_OVERVIEW) { OverviewScreen(repo, tnav) { System.currentTimeMillis() } }
                composable(ROUTE_POSITIONS) { PositionsScreen(repo, tnav) }
                composable(
                    ROUTE_POSITION_DETAIL,
                    arguments = listOf(navArgument("id") { type = NavType.StringType }),
                ) { entry -> PositionDetailScreen(repo, tnav, entry.arguments?.getString("id") ?: "") }
                composable(ROUTE_POTENTIAL) { PotentialScreen(repo, tnav) }
                composable(ROUTE_HISTORY) { HistoryScreen(repo, tnav) }
                composable(ROUTE_ACCOUNTS) { AccountsScreen(repo, tnav) { System.currentTimeMillis() } }
                composable(ROUTE_ACCOUNTS_ADD) { AccountOnboardingScreen(app) { nav.popBackStack() } }
                composable(ROUTE_STRATEGIES) { StrategiesScreen(app, repo) }
                composable(ROUTE_COGNITION) { CognitionScreen(repo) }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun TradingTopBar(nav: NavHostController, onBack: () -> Unit, app: VanApplication) {
    val tokens = LocalVanTokens.current
    val entry by nav.currentBackStackEntryAsState()
    val atRoot = entry?.destination?.route == ROUTE_OVERVIEW || entry == null
    TopAppBar(
        title = { Text("Trading", style = tokens.type.title, color = tokens.color.textPrimary) },
        navigationIcon = {
            IconButton(onClick = { if (atRoot) onBack() else nav.popBackStack() }) {
                Icon(Icons.Default.ArrowBack, contentDescription = "Back", tint = tokens.color.textPrimary)
            }
        },
        actions = { TradingHaltButton(app) },
        colors = TopAppBarDefaults.topAppBarColors(
            containerColor = tokens.color.bgCanvas,
            titleContentColor = tokens.color.textPrimary,
        ),
    )
}

@Composable
private fun TradingBottomBar(nav: NavHostController) {
    val tokens = LocalVanTokens.current
    val entry by nav.currentBackStackEntryAsState()
    val route = entry?.destination?.route ?: ROUTE_OVERVIEW
    NavigationBar(containerColor = tokens.color.surfaceAcrylic) {
        val items = listOf(
            Triple(ROUTE_OVERVIEW, "Overview", Icons.Default.Home),
            Triple(ROUTE_POSITIONS, "Positions", Icons.Default.ShowChart),
            Triple(ROUTE_POTENTIAL, "Potential", Icons.Default.Search),
            Triple(ROUTE_HISTORY, "History", Icons.Default.History),
            Triple(ROUTE_ACCOUNTS, "Accounts", Icons.Default.AccountBalance),
        )
        items.forEach { (target, label, icon) ->
            NavigationBarItem(
                selected = route == target,
                onClick = { nav.navigate(target) { launchSingleTop = true; popUpTo(ROUTE_OVERVIEW) } },
                icon = { Icon(icon, contentDescription = label) },
                label = { Text(label, style = tokens.type.label) },
                colors = NavigationBarItemDefaults.colors(
                    selectedIconColor = tokens.color.accentCyan,
                    selectedTextColor = tokens.color.accentCyan,
                    unselectedIconColor = tokens.color.textTertiary,
                    unselectedTextColor = tokens.color.textTertiary,
                    indicatorColor = tokens.color.accentCyan.copy(alpha = 0.15f),
                ),
            )
        }
    }
}

/**
 * GAP-F-005 owner halt — the app-bar icon + confirmation sheet. Two independent biometric
 * signatures: the `owner-halt` authority grant here (carried as `client_context`), then the
 * gateway's own A4 challenge in [TradingHaltStatusBar]. The gateway's `TradingHaltExecutor`
 * requires both; this screen never claims a halt the gateway did not verify.
 */
/**
 * What the halt button knows that the status bar must show: the outcome of confirmation 1
 * (the authority grant) once the sheet has gone. Process-scoped on purpose — a halt attempt
 * is one owner, one screen, one moment; it is cleared when a halt command is actually sent.
 */
internal object TradingHaltUi {
    var authorityStatus: String? by mutableStateOf(null)
}

@Composable
private fun TradingHaltButton(app: VanApplication) {
    val tokens = LocalVanTokens.current
    val context = LocalContext.current
    val gate = remember(context) { (context as? FragmentActivity)?.let(::BiometricGate) }
    var showSheet by remember { mutableStateOf(false) }

    IconButton(onClick = { showSheet = true }) {
        Icon(
            Icons.Default.PowerSettingsNew,
            contentDescription = "Halt trading",
            tint = tokens.color.forStatusRole(StatusSemantics.ROLE_CRITICAL),
        )
    }

    if (showSheet) {
        ApprovalSheet(
            title = "Halt trading",
            actionDigest = "Stops VAN placing, sizing, modifying or exiting trades across every " +
                "connected account until you resume trading. Existing positions are not closed. " +
                "This sends the request; owner biometric approval is required next and is " +
                "enforced by the trading authority itself, not by this screen.",
            onApprove = {
                // Confirmation 1 of 2: sign the `owner-halt` / `van-trading-core` authority
                // grant under biometrics; the ref travels as `client_context`. The gateway
                // then issues its own A4 challenge (confirmation 2, in TradingHaltStatusBar).
                // Without a gate there is no grant, so nothing is sent and the screen says so.
                if (gate == null) {
                    return@ApprovalSheet Result.failure(
                        IllegalStateException("Owner biometric approval is unavailable on this screen; nothing was sent."),
                    )
                }
                val prepared = runCatching { TradingHaltAuthority.prepare() }.getOrElse {
                    return@ApprovalSheet Result.failure(IllegalStateException("Owner authority key unavailable; nothing was sent."))
                }
                val signature = runCatching { app.gatewayClient.newA4ApprovalSignature() }.getOrElse {
                    return@ApprovalSheet Result.failure(IllegalStateException("Owner authority key unavailable; nothing was sent."))
                }
                TradingHaltUi.authorityStatus = "Confirmation 1 of 2: sign the halt authority grant."
                gate.requestA4CommandApproval(
                    signature = signature,
                    challenge = prepared.canonical,
                    title = "Authorize trading halt",
                    subtitle = "owner-halt → van-trading-core",
                    onApproved = { signatureBase64 ->
                        val ref = runCatching { prepared.assembleFromSignatureBase64(signatureBase64) }.getOrElse {
                            TradingHaltUi.authorityStatus = "Owner authority token could not be assembled; nothing was sent."
                            return@requestA4CommandApproval
                        }
                        TradingHaltUi.authorityStatus = null
                        app.commandController.submitText(
                            text = TradingHaltAuthority.HALT_COMMAND_TEXT,
                            source = VanCommandSource.QUICK_ACTION,
                            actionClass = TradingHaltAuthority.ACTION_CLASS,
                            clientContext = mapOf(TradingHaltAuthority.CLIENT_CONTEXT_KEY to ref),
                        )
                    },
                    onDenied = { reason -> TradingHaltUi.authorityStatus = "Halt authority not granted: $reason. Nothing was sent." },
                )
                Result.success(Unit)
            },
            onDismiss = { showSheet = false },
        )
    }
}

/**
 * The real biometric gate (server-enforced either way) and the honest outcome, shown for as
 * long as a `"halt trading"` command is pending or was the most recent thing said in this
 * conversation — DNA §5's DEGRADED/denied reading, not a claimed success this client cannot
 * back up. A refusal (`owner_halt_authority_missing`, an expired grant, a failed A4 proof) is
 * shown with the gateway's own words.
 */
@Composable
private fun TradingHaltStatusBar(app: VanApplication) {
    val tokens = LocalVanTokens.current
    val activity = LocalContext.current as? FragmentActivity
    val conversation by app.commandController.state.collectAsState()

    val authorityStatus = TradingHaltUi.authorityStatus
    val haltOwnerIndex = conversation.messages.indexOfLast {
        it.role == VanMessageRole.OWNER && it.text == TradingHaltAuthority.HALT_COMMAND_TEXT
    }
    val reply = if (haltOwnerIndex < 0) null else conversation.messages.drop(haltOwnerIndex + 1).firstOrNull()
    val pending = conversation.pendingA4Approval?.takeIf { it.command.text == TradingHaltAuthority.HALT_COMMAND_TEXT }
    if (authorityStatus == null && haltOwnerIndex < 0) return
    if (authorityStatus == null && pending == null && reply == null && !conversation.submitting) return

    VanPanel(dense = true) {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            when {
                authorityStatus != null -> {
                    StatusChip(label = "HALT AUTHORITY", role = StatusSemantics.ROLE_EVENT_RISK)
                    Text(authorityStatus, style = tokens.type.body, color = tokens.color.textSecondary)
                }
                pending != null -> {
                    StatusChip(label = "OWNER APPROVAL PENDING", role = StatusSemantics.ROLE_EVENT_RISK)
                    Text(pending.resolvedActionId, style = tokens.type.body, color = tokens.color.textSecondary)
                    TextButton(enabled = activity != null, onClick = { activity?.let { app.commandController.approvePendingA4(it) } }) {
                        Text("Approve with biometric", style = tokens.type.label, color = tokens.color.forStatusRole(StatusSemantics.ROLE_CRITICAL))
                    }
                }
                conversation.submitting -> {
                    StatusChip(label = "SENDING", role = StatusSemantics.ROLE_MONITOR)
                }
                reply != null -> {
                    val role = if (reply.status?.name?.contains("VERIFIED") == true) StatusSemantics.ROLE_FAVOURABLE else StatusSemantics.ROLE_EVENT_RISK
                    StatusChip(label = reply.status?.name ?: "OUTCOME", role = role)
                    Text(reply.text, style = tokens.type.body, color = tokens.color.textSecondary)
                }
            }
        }
    }
}

/**
 * P1-AURA-003 — the trading system's route into VAN's visual state.
 *
 * Aura Rev 2: the reading itself now lives in [VanTradeAuraPublisher], which the floating
 * overlay also holds so the trading aura is always on. This screen holds it *strict* while
 * composed: while the owner is looking at trades, an unreadable ledger shows as UNKNOWN,
 * never as calm. Leaving the screen releases the hold; the overlay's lenient hold (if VAN is
 * visible) keeps the field live.
 */
@Composable
private fun PublishTradeSemantic(repo: TradingRepository) {
    DisposableEffect(repo) {
        VanTradeAuraPublisher.acquire(TRADING_SCREEN_HOLDER, repo, strict = true)
        onDispose { VanTradeAuraPublisher.release(TRADING_SCREEN_HOLDER) }
    }
}

private const val TRADING_SCREEN_HOLDER = "trading-screen"
