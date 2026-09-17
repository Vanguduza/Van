package com.dial.van.overlay

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.PixelFormat
import android.os.Build
import android.os.IBinder
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.WindowManager
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.weight
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.ComposeView
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.app.NotificationCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.LifecycleRegistry
import androidx.lifecycle.setViewTreeLifecycleOwner
import androidx.savedstate.SavedStateRegistry
import androidx.savedstate.SavedStateRegistryController
import androidx.savedstate.SavedStateRegistryOwner
import androidx.savedstate.setViewTreeSavedStateRegistryOwner
import com.dial.van.R
import com.dial.van.VanApplication
import com.dial.van.command.CommandCentreActivity
import com.dial.van.control.VanCommandSource
import com.dial.van.control.VanMessageRole
import com.dial.van.trading.TradingCommandCentreActivity
import com.dial.van.trading.TradeBookParser
import com.dial.van.trading.TradeBookState
import com.dial.van.trading.TradeRow
import com.dial.van.trading.TradeView
import com.dial.van.visual.VanEmbodiment
import com.dial.van.visual.VanGlassSurface
import com.dial.van.visual.VanGlassTokens
import com.dial.van.visual.VanLiveVisualState
import com.dial.van.visual.VanPresence
import com.dial.van.visual.VanPresentation
import com.dial.van.visual.VanVisualState
import com.dial.van.visual.rememberVanEffectBudget
import kotlin.math.abs

private enum class VanWorkboardMode { CONTEXT, CHAT, VOICE, TRADES }

/**
 * Floating VAN owner-control surface.
 *
 * VAN's character, presence and animation are independent from this service's board presentation.
 * Only the VAN hit region moves the overlay; workboard scroll/touch is never hijacked by window drag.
 */
class FloatingOverlayService : Service(), LifecycleOwner, SavedStateRegistryOwner {
    private lateinit var windowManager: WindowManager
    private lateinit var overlayView: ComposeView
    private lateinit var layoutParams: WindowManager.LayoutParams
    private lateinit var stateStore: OverlayStateStore

    private var dismissView: ComposeView? = null
    private var dismissParams: WindowManager.LayoutParams? = null

    private val lifecycleRegistry = LifecycleRegistry(this)
    private val savedStateController = SavedStateRegistryController.create(this)

    private var uiState by mutableStateOf(VanOverlayUiState())
    private var dockEdge by mutableStateOf(DockEdge.NONE)
    private var blurBehindActive by mutableStateOf(false)
    private var workboardMode by mutableStateOf(VanWorkboardMode.CONTEXT)
    private var chatDraft by mutableStateOf("")
    private var tradeView by mutableStateOf(TradeView.CURRENT)
    private var tradeRefreshTick by mutableStateOf(0)

    override fun onCreate() {
        super.onCreate()
        savedStateController.performRestore(null)
        lifecycleRegistry.currentState = Lifecycle.State.CREATED
        stateStore = OverlayStateStore(this)
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager

        val metrics = resources.displayMetrics
        val restored = stateStore.load(metrics.widthPixels / 2, metrics.heightPixels / 3)
        uiState = VanOverlayUiState(
            presentation = restored.presentation,
            xPx = restored.x,
            yPx = restored.y,
        )
        dockEdge = restored.dock

        layoutParams = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            baseFlags(uiState.presentation),
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = uiState.xPx
            y = uiState.yPx
        }
        applyBackdropBlur()

        overlayView = ComposeView(this).apply {
            setViewTreeLifecycleOwner(this@FloatingOverlayService)
            setViewTreeSavedStateRegistryOwner(this@FloatingOverlayService)
            setContent { OverlayContent() }
        }
        windowManager.addView(overlayView, layoutParams)
        lifecycleRegistry.currentState = Lifecycle.State.STARTED
        startForeground(NOTIFICATION_ID, buildNotification())
        stateStore.markRunning(true)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_TOGGLE_MODE -> onVanTap()
            ACTION_OPEN_COMMAND -> openCommandCentre()
        }
        return START_STICKY
    }

    override fun onDestroy() {
        stateStore.markRunning(false)
        persistState(running = false)
        hideDismissTarget()
        if (::overlayView.isInitialized) runCatching { windowManager.removeView(overlayView) }
        lifecycleRegistry.currentState = Lifecycle.State.DESTROYED
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
    override val lifecycle: Lifecycle get() = lifecycleRegistry
    override val savedStateRegistry: SavedStateRegistry get() = savedStateController.savedStateRegistry

    @Composable
    private fun OverlayContent() {
        val app = application as VanApplication
        val degraded by app.degradedModeStore.state.collectAsState()
        val liveFrame = VanLiveVisualState.frame
        val cue = VanPresence.cue(degraded, live = liveFrame)
        val visualState = VanPresence.visualState(cue, liveFrame)
        val chrome = VanOverlayChrome.resolve(
            cue = cue,
            live = liveFrame.copy(health = cue.health),
            healthLine = VanPresence.healthCue(degraded),
        )
        val budget = rememberVanEffectBudget()
        val glass = VanGlassTokens.forState(
            state = chrome.primaryState,
            liveBlurAvailable = blurBehindActive,
            budget = budget,
        )
        val conversation by app.commandController.state.collectAsState()
        val systemLine = chrome.healthLine ?: VanPresence.meshCue(degraded)

        MaterialTheme {
            when (uiState.presentation) {
                VanOverlayPresentation.FULL_FLOATING -> FullFloatingPresence(
                    visualState = visualState,
                    showControls = uiState.quickControls == VanQuickControlsState.VISIBLE,
                )
                VanOverlayPresentation.WORKBOARD_COMPACT -> CompactWorkboard(
                    app = app,
                    visualState = visualState,
                    glass = glass,
                    caption = chrome.caption,
                    healthLine = chrome.healthLine,
                    accent = chrome.accent,
                    latestMessage = conversation.messages.lastOrNull()?.text,
                )
                VanOverlayPresentation.WORKBOARD_EXPANDED -> ExpandedWorkboard(
                    app = app,
                    visualState = visualState,
                    glass = glass,
                    headline = chrome.headline,
                    caption = chrome.caption,
                    systemLine = systemLine,
                    accent = chrome.accent,
                    messages = conversation.messages,
                )
                VanOverlayPresentation.WORKBOARD_MAXIMIZED -> MaximizedWorkboard(
                    app = app,
                    visualState = visualState,
                    glass = glass,
                    headline = chrome.headline,
                    systemLine = systemLine,
                    accent = chrome.accent,
                    messages = conversation.messages,
                )
                VanOverlayPresentation.MINIMIZED -> MinimizedPresence(visualState)
                VanOverlayPresentation.DOCKED -> DockedPresence(visualState)
            }
        }
    }

    @OptIn(ExperimentalFoundationApi::class)
    private fun Modifier.vanGestures(): Modifier = this
        .pointerInput(Unit) {
            detectDragGestures(
                onDragStart = { beginDrag() },
                onDrag = { change, amount ->
                    change.consume()
                    dragBy(amount.x.toInt(), amount.y.toInt())
                },
                onDragEnd = { finishDrag() },
                onDragCancel = { cancelDrag() },
            )
        }
        .combinedClickable(
            onClick = { onVanTap() },
            onDoubleClick = { openCommandCentre() },
            onLongClick = { showQuickControls() },
        )

    @Composable
    private fun FullFloatingPresence(visualState: VanVisualState, showControls: Boolean) {
        val width = if (showControls) 360 else OverlayTheme.RESTING_HIT_DP
        Box(
            modifier = Modifier
                .width(width.dp)
                .height(OverlayTheme.RESTING_HIT_DP.dp),
            contentAlignment = Alignment.TopStart,
        ) {
            val budget = rememberVanEffectBudget()
            VanEmbodiment(
                state = visualState,
                budget = budget,
                presentation = VanPresentation.COMPACT,
                characterFraction = OverlayTheme.RESTING_AVATAR_DP / OverlayTheme.RESTING_HIT_DP.toFloat(),
                modifier = Modifier
                    .size(OverlayTheme.RESTING_HIT_DP.dp)
                    .semantics { contentDescription = "Van floating assistant" }
                    .vanGestures(),
            )
            if (showControls) {
                QuickControls(
                    modifier = Modifier
                        .offset(x = 176.dp, y = 4.dp)
                        .width(176.dp),
                )
            }
        }
    }

    @OptIn(ExperimentalFoundationApi::class)
    @Composable
    private fun CompactWorkboard(
        app: VanApplication,
        visualState: VanVisualState,
        glass: com.dial.van.visual.VanGlassStyle,
        caption: String,
        healthLine: String?,
        accent: Int,
        latestMessage: String?,
    ) {
        val budget = rememberVanEffectBudget()
        Box(
            modifier = Modifier
                .width(OverlayTheme.COMPACT_WIDTH_DP.dp)
                .height(OverlayTheme.COMPACT_HEIGHT_DP.dp),
        ) {
            VanGlassSurface(
                style = glass,
                modifier = Modifier
                    .fillMaxSize()
                    .padding(top = 22.dp),
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(start = 102.dp, end = 10.dp, top = 12.dp, bottom = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(5.dp),
                ) {
                    Text(caption, color = Color(accent), fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                    if (!healthLine.isNullOrBlank()) {
                        Text(healthLine, color = Color(0xFFB8CBD2), fontSize = 10.sp, maxLines = 1)
                    }
                    if (!latestMessage.isNullOrBlank()) {
                        Text(latestMessage, color = Color(0xFFF4FCFF), fontSize = 11.sp, maxLines = 2)
                    }
                    if (workboardMode == VanWorkboardMode.CHAT) {
                        ChatComposer(app, accent, compact = true)
                    } else {
                        Row(horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                            WorkChip("Chat", accent) { openChat(expanded = false) }
                            WorkChip("Voice", accent) { beginVoice(app) }
                            WorkChip("More", accent) { setPresentation(VanOverlayPresentation.WORKBOARD_EXPANDED) }
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                            WorkChip("Projects", accent) { openCommandCentre("projects") }
                            WorkChip("Tasks", accent) { openCommandCentre("tasks") }
                            WorkChip("Decisions", accent) { openCommandCentre("decisions") }
                        }
                    }
                }
            }

            VanEmbodiment(
                state = visualState,
                budget = budget,
                presentation = VanPresentation.COMPACT,
                modifier = Modifier
                    .size(OverlayTheme.RESTING_HIT_DP.dp)
                    .offset(x = (-42).dp, y = (-2).dp)
                    .vanGestures(),
                characterFraction = 0.55f,
            )
            Text(
                "Expand",
                color = Color(0xFFBDEFFF),
                fontSize = 10.sp,
                modifier = Modifier
                    .align(Alignment.BottomEnd)
                    .padding(9.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .combinedClickable(onClick = { setPresentation(VanOverlayPresentation.WORKBOARD_EXPANDED) })
                    .padding(horizontal = 7.dp, vertical = 4.dp),
            )
        }
    }

    @Composable
    private fun ExpandedWorkboard(
        app: VanApplication,
        visualState: VanVisualState,
        glass: com.dial.van.visual.VanGlassStyle,
        headline: String,
        caption: String,
        systemLine: String,
        accent: Int,
        messages: List<com.dial.van.control.VanConversationMessage>,
    ) {
        val budget = rememberVanEffectBudget()
        Box(
            modifier = Modifier
                .width(OverlayTheme.EXPANDED_WIDTH_DP.dp)
                .height(OverlayTheme.EXPANDED_HEIGHT_DP.dp),
        ) {
            VanGlassSurface(
                style = glass,
                modifier = Modifier
                    .fillMaxSize()
                    .padding(top = 20.dp),
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(start = 104.dp, end = 12.dp, top = 12.dp, bottom = 10.dp),
                ) {
                    Text(headline, color = Color(accent), fontSize = 14.sp, fontWeight = FontWeight.Bold)
                    Text(caption, color = Color(0xFFF4FCFF), fontSize = 11.sp, maxLines = 2)
                    Text(systemLine, color = Color(0xFFB8CBD2), fontSize = 10.sp, maxLines = 1)
                    Spacer(Modifier.height(6.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                        WorkChip("Chat", accent) { openChat(expanded = true) }
                        WorkChip("Voice", accent) { beginVoice(app) }
                        WorkChip("Trades", accent) { workboardMode = VanWorkboardMode.TRADES }
                        WorkChip("Max", accent) { setPresentation(VanOverlayPresentation.WORKBOARD_MAXIMIZED) }
                    }
                    Spacer(Modifier.height(6.dp))
                    when (workboardMode) {
                        VanWorkboardMode.CHAT,
                        VanWorkboardMode.VOICE,
                        -> {
                            LazyColumn(
                                modifier = Modifier.weight(1f).fillMaxWidth(),
                                verticalArrangement = Arrangement.spacedBy(5.dp),
                            ) {
                                items(messages.takeLast(20), key = { it.id }) { message ->
                                    ConversationBubble(message.role, message.text, accent)
                                }
                            }
                            ChatComposer(app, accent, compact = false)
                        }
                        VanWorkboardMode.TRADES -> {
                            TradesWorkboardPanel(app = app, accent = accent)
                        }
                        VanWorkboardMode.CONTEXT -> {
                            Column(
                                modifier = Modifier
                                    .weight(1f)
                                    .fillMaxWidth()
                                    .verticalScroll(rememberScrollState()),
                                verticalArrangement = Arrangement.spacedBy(6.dp),
                            ) {
                                ContextAction("Projects", "Open mounted Project Truth contexts") { openCommandCentre("projects") }
                                ContextAction("Tasks", "Inspect queued and active work") { openCommandCentre("tasks") }
                                ContextAction("Decisions", "Review owner decisions and approvals") { openCommandCentre("decisions") }
                                ContextAction("Systems", "Inspect Hermes, gateway and mesh health") { openCommandCentre("systems") }
                                ContextAction("Trading", "Open VATI portfolio, trades, risk and accounts") {
                                    startActivity(TradingCommandCentreActivity.intent(this@FloatingOverlayService))
                                }
                                ContextAction("Command Centre", "Open the full owner admin surface") { openCommandCentre() }
                            }
                        }
                    }
                }
            }

            VanEmbodiment(
                state = visualState,
                budget = budget,
                presentation = VanPresentation.EXPANDED,
                modifier = Modifier
                    .size(OverlayTheme.RESTING_HIT_DP.dp)
                    .offset(x = (-40).dp, y = (-4).dp)
                    .vanGestures(),
                characterFraction = 0.55f,
            )
        }
    }

    @Composable
    private fun MaximizedWorkboard(
        app: VanApplication,
        visualState: VanVisualState,
        glass: com.dial.van.visual.VanGlassStyle,
        headline: String,
        systemLine: String,
        accent: Int,
        messages: List<com.dial.van.control.VanConversationMessage>,
    ) {
        val budget = rememberVanEffectBudget()
        val density = resources.displayMetrics.density
        val widthDp = resources.displayMetrics.widthPixels / density - OverlayTheme.MAXIMIZED_HORIZONTAL_MARGIN_DP * 2
        val heightDp = resources.displayMetrics.heightPixels / density * OverlayTheme.MAXIMIZED_HEIGHT_FRACTION
        Box(
            modifier = Modifier
                .width(widthDp.dp)
                .height(heightDp.dp),
        ) {
            VanGlassSurface(style = glass, modifier = Modifier.fillMaxSize().padding(top = 18.dp)) {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(start = 106.dp, end = 14.dp, top = 14.dp, bottom = 12.dp),
                ) {
                    Text("Van • $headline", color = Color(accent), fontSize = 15.sp, fontWeight = FontWeight.Bold)
                    Text(systemLine, color = Color(0xFFB8CBD2), fontSize = 10.sp)
                    Spacer(Modifier.height(6.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                        WorkChip("Chat", accent) { workboardMode = VanWorkboardMode.CHAT }
                        WorkChip("Voice", accent) { beginVoice(app) }
                        WorkChip("Trades", accent) {
                            startActivity(TradingCommandCentreActivity.intent(this@FloatingOverlayService))
                        }
                        WorkChip("Collapse", accent) { setPresentation(VanOverlayPresentation.WORKBOARD_EXPANDED) }
                        WorkChip("Admin", accent) { openCommandCentre() }
                    }
                    Spacer(Modifier.height(8.dp))
                    LazyColumn(
                        modifier = Modifier.weight(1f).fillMaxWidth(),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        items(messages, key = { it.id }) { message ->
                            ConversationBubble(message.role, message.text, accent)
                        }
                    }
                    ChatComposer(app, accent, compact = false)
                }
            }
            VanEmbodiment(
                state = visualState,
                budget = budget,
                presentation = VanPresentation.EXPANDED,
                modifier = Modifier
                    .size(OverlayTheme.RESTING_HIT_DP.dp)
                    .offset(x = (-38).dp, y = (-5).dp)
                    .vanGestures(),
                characterFraction = 0.55f,
            )
        }
    }

    @Composable
    private fun TradesWorkboardPanel(app: VanApplication, accent: Int) {
        var state: TradeBookState by remember { mutableStateOf(TradeBookState.Loading) }
        val view = tradeView
        val refresh = tradeRefreshTick
        LaunchedEffect(view, refresh) {
            state = runCatching { app.gatewayClient.tradingTrades(view.query) }.fold(
                onSuccess = { TradeBookParser.parse(view, it) },
                onFailure = { TradeBookState.Unavailable(view, "Gateway unreachable: trade ledger not available") },
            )
        }
        Column(modifier = Modifier.fillMaxWidth().weight(1f)) {
            Row(horizontalArrangement = Arrangement.spacedBy(5.dp), verticalAlignment = Alignment.CenterVertically) {
                TradeView.entries.forEach { candidate ->
                    WorkChip(candidate.label, accent) { tradeView = candidate }
                }
                WorkChip("Refresh", accent) { tradeRefreshTick += 1 }
                WorkChip("Open", accent) {
                    startActivity(TradingCommandCentreActivity.intent(this@FloatingOverlayService, TradingCommandCentreActivity.tradesRoute(view)))
                }
            }
            Spacer(Modifier.height(5.dp))
            when (val current = state) {
                TradeBookState.Loading -> Text("Reading the trading ledger…", color = Color(0xFFB6C2D0), fontSize = 10.sp)
                is TradeBookState.Unavailable -> Text(current.reason, color = Color(0xFFFFB300), fontSize = 10.sp, maxLines = 2)
                is TradeBookState.Ready -> {
                    if (!current.ledgerAvailable) {
                        Text("Trading ledger unavailable on the gateway.", color = Color(0xFFFFB300), fontSize = 10.sp)
                    } else if (current.rows.isEmpty()) {
                        Text(view.emptyCopy, color = Color(0xFFB6C2D0), fontSize = 10.sp)
                    } else {
                        LazyColumn(modifier = Modifier.weight(1f).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                            items(current.rows.take(8)) { row -> TradeWorkboardRow(row, accent) }
                        }
                    }
                }
            }
            Text("Read-only preview · confidence is an uncalibrated rule score · Risk Authority owns sizing", color = Color(0xFF7F9099), fontSize = 8.sp, maxLines = 2)
        }
    }

    @Composable
    private fun TradeWorkboardRow(row: TradeRow, accent: Int) {
        ContextAction(row.headline, "${row.confidence.percentLabel} ${row.confidence.band.label}") {
            val route = row.tradeIntentId?.let { TradingCommandCentreActivity.tradeRoute(it) } ?: "instrument/${row.symbol}"
            startActivity(TradingCommandCentreActivity.intent(this@FloatingOverlayService, route))
        }
    }

    @Composable
    private fun ChatComposer(app: VanApplication, accent: Int, compact: Boolean) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(5.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            OutlinedTextField(
                value = chatDraft,
                onValueChange = { chatDraft = it },
                modifier = Modifier.weight(1f),
                singleLine = compact,
                maxLines = if (compact) 1 else 3,
                label = { Text("Command", fontSize = 10.sp) },
            )
            WorkChip("Send", accent) {
                val text = chatDraft.trim()
                if (text.isNotEmpty()) {
                    app.commandController.submitText(text, VanCommandSource.CHAT)
                    chatDraft = ""
                }
            }
        }
    }

    @Composable
    private fun ConversationBubble(role: VanMessageRole, text: String, accent: Int) {
        val background = when (role) {
            VanMessageRole.OWNER -> Color(accent).copy(alpha = 0.18f)
            VanMessageRole.VAN -> Color(0xFFBDEFFF).copy(alpha = 0.11f)
            VanMessageRole.SYSTEM -> Color(0xFFFFB300).copy(alpha = 0.12f)
        }
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(10.dp))
                .background(background)
                .padding(8.dp),
        ) {
            Text(text, color = Color(0xFFF4FCFF), fontSize = 11.sp)
        }
    }

    @OptIn(ExperimentalFoundationApi::class)
    @Composable
    private fun ContextAction(title: String, detail: String, onClick: () -> Unit) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(10.dp))
                .background(Color(VanGlassTokens.BABY_CYAN).copy(alpha = 0.08f))
                .combinedClickable(onClick = onClick)
                .padding(9.dp),
        ) {
            Column {
                Text(title, color = Color.White, fontWeight = FontWeight.SemiBold, fontSize = 12.sp)
                Text(detail, color = Color(0xFFB8CBD2), fontSize = 10.sp)
            }
        }
    }

    @OptIn(ExperimentalFoundationApi::class)
    @Composable
    private fun WorkChip(label: String, accent: Int, onClick: () -> Unit) {
        Box(
            modifier = Modifier
                .height(30.dp)
                .clip(RoundedCornerShape(9.dp))
                .background(Color(accent).copy(alpha = 0.16f))
                .combinedClickable(onClick = onClick)
                .padding(horizontal = 7.dp),
            contentAlignment = Alignment.Center,
        ) {
            Text(label, color = Color(0xFFF4FCFF), fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
        }
    }

    @OptIn(ExperimentalFoundationApi::class)
    @Composable
    private fun QuickControls(modifier: Modifier = Modifier) {
        VanGlassSurface(
            style = VanGlassTokens.forState(
                state = VanLiveVisualState.current.durableState,
                liveBlurAvailable = blurBehindActive,
            ),
            modifier = modifier,
        ) {
            Column(
                modifier = Modifier.padding(8.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                OverlayTheme.QUICK_CONTROLS.forEach { label ->
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(30.dp)
                            .clip(RoundedCornerShape(9.dp))
                            .background(Color(VanGlassTokens.BABY_CYAN).copy(alpha = 0.10f))
                            .combinedClickable(onClick = { handleQuickControl(label) })
                            .padding(horizontal = 8.dp),
                        contentAlignment = Alignment.CenterStart,
                    ) {
                        Text(label, color = Color(0xFFF4FCFF), fontSize = 11.sp)
                    }
                }
            }
        }
    }

    @Composable
    private fun MinimizedPresence(visualState: VanVisualState) {
        Box(
            modifier = Modifier.size(OverlayTheme.MINIMIZED_TOUCH_DP.dp),
            contentAlignment = Alignment.Center,
        ) {
            VanMinimizedAvatar(
                state = visualState,
                modifier = Modifier
                    .size(OverlayTheme.MINIMIZED_VISUAL_DP.dp)
                    .vanGestures(),
            )
        }
    }

    @Composable
    private fun DockedPresence(visualState: VanVisualState) {
        val budget = rememberVanEffectBudget()
        Box(
            modifier = Modifier
                .size(width = OverlayTheme.DOCK_WIDTH_DP.dp, height = OverlayTheme.DOCK_HIT_DP.dp)
                .semantics { contentDescription = "Van docked" },
        ) {
            Canvas(Modifier.fillMaxSize()) {
                val field = Color(VanGlassTokens.ACCENT_CYAN).copy(alpha = 0.25f)
                val path = androidx.compose.ui.graphics.Path().apply {
                    moveTo(size.width * 0.08f, size.height * 0.12f)
                    quadraticBezierTo(size.width * 0.95f, size.height * 0.08f, size.width, size.height * 0.42f)
                    quadraticBezierTo(size.width * 0.92f, size.height * 0.92f, size.width * 0.10f, size.height * 0.88f)
                    quadraticBezierTo(size.width * 0.02f, size.height * 0.50f, size.width * 0.08f, size.height * 0.12f)
                    close()
                }
                drawPath(path, field)
            }
            VanEmbodiment(
                state = visualState,
                budget = budget,
                presentation = VanPresentation.COMPACT,
                modifier = Modifier
                    .size(OverlayTheme.DOCK_CHARACTER_DP.dp)
                    .align(Alignment.TopCenter)
                    .offset(y = (-4).dp)
                    .vanGestures(),
            )
        }
    }

    private fun onVanTap() {
        updateUiState(VanOverlayReducer.onVanTapped(uiState))
    }

    private fun showQuickControls() {
        updateUiState(VanOverlayReducer.showQuickControls(uiState))
    }

    private fun openChat(expanded: Boolean) {
        workboardMode = VanWorkboardMode.CHAT
        setPresentation(
            if (expanded) VanOverlayPresentation.WORKBOARD_EXPANDED
            else VanOverlayPresentation.WORKBOARD_COMPACT,
        )
    }

    private fun beginVoice(app: VanApplication) {
        workboardMode = VanWorkboardMode.VOICE
        setPresentation(VanOverlayPresentation.WORKBOARD_EXPANDED)
        app.voiceSession.beginOwnerTurn()
    }

    private fun handleQuickControl(label: String) {
        val app = application as VanApplication
        when (label) {
            "Chat" -> openChat(expanded = true)
            "Voice" -> beginVoice(app)
            "Minimize" -> updateUiState(VanOverlayReducer.minimize(uiState))
            "Command Centre" -> openCommandCentre()
            "Dock" -> updateUiState(VanOverlayReducer.dock(uiState))
            "Close" -> stopSelf()
        }
    }

    private fun setPresentation(presentation: VanOverlayPresentation) {
        updateUiState(uiState.copy(presentation = presentation, quickControls = VanQuickControlsState.HIDDEN))
    }

    private fun updateUiState(next: VanOverlayUiState) {
        uiState = next
        if (::layoutParams.isInitialized && ::overlayView.isInitialized) {
            updateWindowFlags()
            persistState()
        }
    }

    private fun beginDrag() {
        updateUiState(
            uiState.copy(
                dragging = true,
                dismissTargetVisible = true,
                quickControls = VanQuickControlsState.HIDDEN,
            ),
        )
        showDismissTarget()
    }

    private fun dragBy(dx: Int, dy: Int) {
        val metrics = resources.displayMetrics
        val minTouch = when (uiState.presentation) {
            VanOverlayPresentation.MINIMIZED -> dp(OverlayTheme.MINIMIZED_TOUCH_DP)
            VanOverlayPresentation.DOCKED -> dp(OverlayTheme.DOCK_WIDTH_DP)
            else -> dp(OverlayTheme.RESTING_HIT_DP)
        }
        val nx = (layoutParams.x + dx).coerceIn(0, (metrics.widthPixels - minTouch).coerceAtLeast(0))
        val ny = (layoutParams.y + dy).coerceIn(0, (metrics.heightPixels - minTouch).coerceAtLeast(0))
        layoutParams.x = nx
        layoutParams.y = ny
        windowManager.updateViewLayout(overlayView, layoutParams)

        val armed = isInsideDismissTarget(nx, ny, minTouch)
        if (armed != uiState.dismissTargetArmed) {
            if (armed) overlayView.performHapticFeedback(HapticFeedbackConstants.CLOCK_TICK)
            uiState = uiState.copy(xPx = nx, yPx = ny, dismissTargetArmed = armed)
        } else {
            uiState = uiState.copy(xPx = nx, yPx = ny)
        }
        refreshDismissTarget()
    }

    private fun finishDrag() {
        val shouldClose = uiState.dismissTargetArmed
        hideDismissTarget()
        if (shouldClose) {
            stateStore.markRunning(false)
            stopSelf()
            return
        }

        val metrics = resources.displayMetrics
        val avatar = when (uiState.presentation) {
            VanOverlayPresentation.MINIMIZED -> dp(OverlayTheme.MINIMIZED_TOUCH_DP)
            VanOverlayPresentation.DOCKED -> dp(OverlayTheme.DOCK_WIDTH_DP)
            else -> dp(OverlayTheme.RESTING_HIT_DP)
        }
        val snapped = EdgeDocking.snap(
            layoutParams.x,
            layoutParams.y,
            avatar,
            metrics.widthPixels,
            metrics.heightPixels,
        )
        layoutParams.x = snapped.first
        layoutParams.y = snapped.second
        dockEdge = EdgeDocking.detectEdge(
            snapped.first,
            snapped.second,
            avatar,
            metrics.widthPixels,
            metrics.heightPixels,
        )
        windowManager.updateViewLayout(overlayView, layoutParams)
        updateUiState(
            uiState.copy(
                xPx = snapped.first,
                yPx = snapped.second,
                dragging = false,
                dismissTargetVisible = false,
                dismissTargetArmed = false,
            ),
        )
    }

    private fun cancelDrag() {
        hideDismissTarget()
        updateUiState(uiState.copy(dragging = false, dismissTargetVisible = false, dismissTargetArmed = false))
    }

    private fun isInsideDismissTarget(x: Int, y: Int, avatarSize: Int): Boolean {
        val metrics = resources.displayMetrics
        val hit = dp(OverlayTheme.DISMISS_HIT_DP)
        val bottom = dp(OverlayTheme.DISMISS_BOTTOM_MARGIN_DP)
        val centerX = x + avatarSize / 2
        val centerY = y + avatarSize / 2
        val targetX = metrics.widthPixels / 2
        val targetY = metrics.heightPixels - bottom - hit / 2
        return abs(centerX - targetX) <= hit / 2 && abs(centerY - targetY) <= hit / 2
    }

    private fun showDismissTarget() {
        if (dismissView != null) return
        val view = ComposeView(this).apply {
            setViewTreeLifecycleOwner(this@FloatingOverlayService)
            setViewTreeSavedStateRegistryOwner(this@FloatingOverlayService)
            setContent { DismissTarget(uiState.dismissTargetArmed) }
        }
        val params = WindowManager.LayoutParams(
            dp(OverlayTheme.DISMISS_HIT_DP),
            dp(OverlayTheme.DISMISS_HIT_DP),
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL
            y = dp(OverlayTheme.DISMISS_BOTTOM_MARGIN_DP)
        }
        dismissView = view
        dismissParams = params
        windowManager.addView(view, params)
    }

    private fun refreshDismissTarget() {
        // Compose reads uiState; invalidation keeps armed animation in sync without another window.
        dismissView?.invalidate()
    }

    private fun hideDismissTarget() {
        dismissView?.let { runCatching { windowManager.removeView(it) } }
        dismissView = null
        dismissParams = null
    }

    @Composable
    private fun DismissTarget(armed: Boolean) {
        Box(
            modifier = Modifier.fillMaxSize(),
            contentAlignment = Alignment.Center,
        ) {
            Canvas(
                modifier = Modifier
                    .size((if (armed) OverlayTheme.DISMISS_VISUAL_DP + 8 else OverlayTheme.DISMISS_VISUAL_DP).dp)
                    .clip(CircleShape),
            ) {
                drawCircle(
                    color = if (armed) Color(0xFFEF4444).copy(alpha = 0.92f)
                    else Color(0xFF101820).copy(alpha = 0.84f),
                )
                val inset = size.minDimension * 0.31f
                val width = (size.minDimension * 0.065f).coerceAtLeast(2f)
                drawLine(
                    Color.White,
                    Offset(inset, inset),
                    Offset(size.width - inset, size.height - inset),
                    width,
                    StrokeCap.Round,
                )
                drawLine(
                    Color.White,
                    Offset(size.width - inset, inset),
                    Offset(inset, size.height - inset),
                    width,
                    StrokeCap.Round,
                )
            }
        }
    }

    private fun openCommandCentre(module: String? = null) {
        startActivity(
            Intent(this, CommandCentreActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                if (!module.isNullOrBlank()) putExtra("module", module)
            },
        )
    }

    private fun baseFlags(presentation: VanOverlayPresentation): Int {
        var flags = WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS
        if (presentation !in setOf(
                VanOverlayPresentation.WORKBOARD_COMPACT,
                VanOverlayPresentation.WORKBOARD_EXPANDED,
                VanOverlayPresentation.WORKBOARD_MAXIMIZED,
            )
        ) {
            flags = flags or WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
        }
        return flags
    }

    private fun updateWindowFlags() {
        val blur = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && blurBehindActive) {
            WindowManager.LayoutParams.FLAG_BLUR_BEHIND
        } else {
            0
        }
        layoutParams.flags = baseFlags(uiState.presentation) or blur
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            layoutParams.blurBehindRadius = if (blur != 0) dp(VanGlassTokens.BLUR_DP.toInt()) else 0
        }
        runCatching { windowManager.updateViewLayout(overlayView, layoutParams) }
    }

    private fun applyBackdropBlur() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) {
            blurBehindActive = false
            return
        }
        blurBehindActive = runCatching { windowManager.isCrossWindowBlurEnabled }.getOrDefault(false)
        if (blurBehindActive) {
            layoutParams.flags = layoutParams.flags or WindowManager.LayoutParams.FLAG_BLUR_BEHIND
            layoutParams.blurBehindRadius = dp(VanGlassTokens.BLUR_DP.toInt())
        }
    }

    private fun persistState(running: Boolean = true) {
        stateStore.save(
            OverlayPersistedState(
                x = uiState.xPx,
                y = uiState.yPx,
                presentation = uiState.presentation,
                dock = dockEdge,
                serviceRunning = running,
            ),
        )
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private fun buildNotification(): Notification {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "Van overlay", NotificationManager.IMPORTANCE_LOW),
        )
        val pending = PendingIntent.getActivity(
            this,
            0,
            Intent(this, CommandCentreActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.overlay_notification_title))
            .setContentText(getString(R.string.overlay_notification_body))
            .setSmallIcon(R.drawable.ic_van_notification)
            .setContentIntent(pending)
            .setOngoing(true)
            .build()
    }

    companion object {
        const val ACTION_TOGGLE_MODE = "com.dial.van.overlay.TOGGLE"
        const val ACTION_OPEN_COMMAND = "com.dial.van.overlay.OPEN_COMMAND"
        private const val CHANNEL_ID = "van_overlay"
        private const val NOTIFICATION_ID = 1001

        fun start(context: Context) {
            context.startForegroundService(Intent(context, FloatingOverlayService::class.java))
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, FloatingOverlayService::class.java))
        }
    }
}
