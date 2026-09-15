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
import android.view.WindowManager
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Apps
import androidx.compose.material.icons.filled.Chat
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
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
import com.dial.van.visual.VanCaptions
import com.dial.van.visual.VanEmbodiment
import com.dial.van.visual.VanGlassSurface
import com.dial.van.visual.VanGlassTokens
import com.dial.van.visual.VanPresence
import com.dial.van.visual.VanPresentation
import com.dial.van.visual.VanStatusPalette
import com.dial.van.visual.rememberVanEffectBudget

/**
 * Floating Van overlay.
 *
 * Composition follows `docs/VAN_GLASSMORPHIC_FLOATING_ASSISTANT_DESIGN.md`:
 * §4 Van breaks the glass edge and is never trapped in a rectangular card; §5 compact mode
 * carries the character, aura, status copy and 1–3 quick actions; §10 requests real backdrop
 * blur at the window level and degrades to a pre-tinted surface; §13 governs tap, drag and
 * dock behaviour.
 */
class FloatingOverlayService : Service(), LifecycleOwner, SavedStateRegistryOwner {

    private lateinit var windowManager: WindowManager
    private lateinit var overlayView: ComposeView
    private lateinit var layoutParams: WindowManager.LayoutParams
    private lateinit var stateStore: OverlayStateStore

    private val lifecycleRegistry = LifecycleRegistry(this)
    private val savedStateController = SavedStateRegistryController.create(this)

    private var overlayMode by mutableStateOf(OverlayMode.COMPACT)
    private var posX by mutableIntStateOf(0)
    private var posY by mutableIntStateOf(0)
    private var dockEdge by mutableStateOf(DockEdge.NONE)
    private var blurBehindActive by mutableStateOf(false)

    private var shellWidthPx = 0

    override fun onCreate() {
        super.onCreate()
        savedStateController.performRestore(null)
        lifecycleRegistry.currentState = Lifecycle.State.CREATED
        stateStore = OverlayStateStore(this)
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
        shellWidthPx = (SHELL_WIDTH_DP * resources.displayMetrics.density).toInt()

        val metrics = resources.displayMetrics
        val restored = stateStore.load(metrics.widthPixels / 2, metrics.heightPixels / 3)
        posX = restored.x
        posY = restored.y
        overlayMode = restored.mode
        dockEdge = restored.dock

        layoutParams = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = posX
            y = posY
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

    /**
     * §10 step 2 — real backdrop blur sampling. Cross-window blur is an Android 12+ capability
     * and can be switched off system-wide at any time, so the result is recorded and the glass
     * tokens compensate when it is unavailable.
     */
    private fun applyBackdropBlur() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) {
            blurBehindActive = false
            return
        }
        val enabled = runCatching { windowManager.isCrossWindowBlurEnabled }.getOrDefault(false)
        blurBehindActive = enabled
        if (enabled) {
            layoutParams.flags = layoutParams.flags or WindowManager.LayoutParams.FLAG_BLUR_BEHIND
            layoutParams.blurBehindRadius =
                (VanGlassTokens.BLUR_DP * resources.displayMetrics.density).toInt()
        } else {
            layoutParams.flags = layoutParams.flags and WindowManager.LayoutParams.FLAG_BLUR_BEHIND.inv()
            layoutParams.blurBehindRadius = 0
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_TOGGLE_MODE -> overlayMode =
                if (overlayMode == OverlayMode.COMPACT) OverlayMode.EXPANDED else OverlayMode.COMPACT
            ACTION_OPEN_COMMAND -> openCommandCentre()
        }
        persistState()
        return START_STICKY
    }

    override fun onDestroy() {
        stateStore.markRunning(false)
        persistState()
        if (::overlayView.isInitialized) windowManager.removeView(overlayView)
        lifecycleRegistry.currentState = Lifecycle.State.DESTROYED
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override val lifecycle: Lifecycle get() = lifecycleRegistry
    override val savedStateRegistry: SavedStateRegistry get() = savedStateController.savedStateRegistry

    @Composable
    private fun OverlayContent() {
        val app = application as VanApplication
        val degraded = app.degradedModeStore.snapshot()
        val cue = VanPresence.cue(degraded)
        val visualState = VanPresence.visualState(cue)
        val palette = VanStatusPalette.forState(cue.durableState)
        val budget = rememberVanEffectBudget()
        val glass = VanGlassTokens.forState(
            state = cue.durableState,
            liveBlurAvailable = blurBehindActive,
            budget = budget,
        )

        MaterialTheme {
            Box(modifier = Modifier.pointerInput(Unit) { dragHandler() }) {
                when (overlayMode) {
                    OverlayMode.DOCKED -> DockedPresence(palette.accent)

                    OverlayMode.COMPACT -> CompactShell(
                        app = app,
                        glass = glass,
                        budget = budget,
                        visualState = visualState,
                        caption = VanCaptions.forState(cue.durableState),
                        accent = palette.accent,
                    )

                    OverlayMode.EXPANDED -> ExpandedShell(
                        app = app,
                        glass = glass,
                        budget = budget,
                        visualState = visualState,
                        headline = cue.headline,
                        caption = VanCaptions.forState(cue.durableState),
                        meshCue = VanPresence.meshCue(degraded),
                        accent = palette.accent,
                    )
                }
            }
        }
    }

    /**
     * §4/§5 compact composition: a glass capsule carrying status and quick actions, with Van
     * and his aura overlapping — and breaking — the capsule's top edge.
     */
    @Composable
    private fun CompactShell(
        app: VanApplication,
        glass: com.dial.van.visual.VanGlassStyle,
        budget: com.dial.van.visual.VanEffectBudget,
        visualState: com.dial.van.visual.VanVisualState,
        caption: String,
        accent: Int,
    ) {
        Box(
            modifier = Modifier.width(SHELL_WIDTH_DP.dp).height(COMPACT_HEIGHT_DP.dp),
            contentAlignment = Alignment.TopCenter,
        ) {
            VanGlassSurface(
                style = glass,
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .height(CAPSULE_HEIGHT_DP.dp),
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 10.dp, vertical = 6.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text(
                        text = caption,
                        color = Color(accent),
                        fontSize = 11.sp,
                        fontWeight = FontWeight.SemiBold,
                        maxLines = 1,
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    // §5: 1–3 immediate quick actions, never dominating Van.
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        GlassAction(Icons.Default.Mic, "Talk to Van", accent) {
                            app.voiceSession.beginOwnerTurn()
                        }
                        GlassAction(Icons.Default.Chat, "Open Command Centre", accent) {
                            openCommandCentre()
                        }
                        GlassAction(Icons.Default.Apps, "Expand", accent) {
                            overlayMode = OverlayMode.EXPANDED
                            persistState()
                        }
                    }
                }
            }

            // §4: character partly outside the glass, and the primary focal point.
            VanEmbodiment(
                state = visualState,
                budget = budget,
                presentation = VanPresentation.COMPACT,
                modifier = Modifier
                    .size(CHARACTER_DP.dp)
                    .clickable {
                        // §13: tap Van → expand Command Centre surface.
                        overlayMode = OverlayMode.EXPANDED
                        persistState()
                    },
            )
        }
    }

    /** Expanded glass card plus the right-edge action rail from the owner design sheet. */
    @Composable
    private fun ExpandedShell(
        app: VanApplication,
        glass: com.dial.van.visual.VanGlassStyle,
        budget: com.dial.van.visual.VanEffectBudget,
        visualState: com.dial.van.visual.VanVisualState,
        headline: String,
        caption: String,
        meshCue: String,
        accent: Int,
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                modifier = Modifier.width(EXPANDED_WIDTH_DP.dp).height(EXPANDED_HEIGHT_DP.dp),
                contentAlignment = Alignment.TopStart,
            ) {
                VanGlassSurface(
                    style = glass,
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .fillMaxWidth()
                        .height((EXPANDED_HEIGHT_DP - 26).dp),
                ) {
                    Column(modifier = Modifier.padding(start = 96.dp, end = 12.dp, top = 12.dp)) {
                        Text("Van", color = Color.White, fontSize = 17.sp, fontWeight = FontWeight.Bold)
                        Text(
                            text = headline,
                            color = Color(accent),
                            fontSize = 13.sp,
                            fontWeight = FontWeight.SemiBold,
                        )
                        Text(text = caption, color = Color(0xFFB6C2D0), fontSize = 11.sp, maxLines = 2)
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(text = meshCue, color = Color(0xFF8A97A6), fontSize = 10.sp, maxLines = 1)
                    }
                }

                VanEmbodiment(
                    state = visualState,
                    budget = budget,
                    presentation = VanPresentation.EXPANDED,
                    modifier = Modifier
                        .align(Alignment.TopStart)
                        .offset(x = 2.dp)
                        .size(CHARACTER_DP.dp)
                        .clickable { openCommandCentre() },
                )
            }

            Spacer(modifier = Modifier.width(8.dp))
            ActionRail(app = app, glass = glass, accent = accent)
        }
    }

    /** Glass rail: Chat, Apps/Agents, Mic, Close — the owner sheet's right-edge control stack. */
    @Composable
    private fun ActionRail(
        app: VanApplication,
        glass: com.dial.van.visual.VanGlassStyle,
        accent: Int,
    ) {
        VanGlassSurface(style = glass, modifier = Modifier.width(48.dp)) {
            Column(
                modifier = Modifier.padding(vertical = 8.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                GlassAction(Icons.Default.Chat, "Chat", accent, active = true) { openCommandCentre() }
                GlassAction(Icons.Default.Apps, "Agents", accent) { openCommandCentre() }
                GlassAction(Icons.Default.Mic, "Voice", accent) { app.voiceSession.beginOwnerTurn() }
                GlassAction(Icons.Default.Close, "Dock Van", accent) {
                    overlayMode = OverlayMode.DOCKED
                    persistState()
                }
            }
        }
    }

    /**
     * §13 Dock: glass controls collapse and a small cyan presence line remains, so Van is
     * never silently gone. Tapping restores the compact shell.
     */
    @Composable
    private fun DockedPresence(accent: Int) {
        Box(
            modifier = Modifier
                .size(width = 12.dp, height = 72.dp)
                .semantics { contentDescription = "Van docked. Tap to restore." }
                .clickable {
                    overlayMode = OverlayMode.COMPACT
                    persistState()
                },
            contentAlignment = Alignment.Center,
        ) {
            Box(
                modifier = Modifier
                    .size(width = 5.dp, height = 56.dp)
                    .clip(RoundedCornerShape(3.dp))
                    .background(Color(accent)),
            )
        }
    }

    @Composable
    private fun GlassAction(
        icon: androidx.compose.ui.graphics.vector.ImageVector,
        label: String,
        accent: Int,
        active: Boolean = false,
        onClick: () -> Unit,
    ) {
        Box(
            modifier = Modifier
                // §5 minimum 48dp touch target.
                .size(TOUCH_TARGET_DP.dp)
                .clip(RoundedCornerShape(12.dp))
                .background(Color(accent).copy(alpha = if (active) 0.26f else 0.12f))
                .clickable(onClick = onClick),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                imageVector = icon,
                contentDescription = label,
                tint = if (active) Color(accent) else Color(0xFFE7ECF2),
                modifier = Modifier.size(20.dp),
            )
        }
    }

    /** §13 Drag: Van and the glass shell move together; docking is short and deterministic. */
    private suspend fun androidx.compose.ui.input.pointer.PointerInputScope.dragHandler() {
        detectDragGestures(
            onDrag = { change, dragAmount ->
                change.consume()
                layoutParams.x = (layoutParams.x + dragAmount.x.toInt()).coerceAtLeast(0)
                layoutParams.y = (layoutParams.y + dragAmount.y.toInt()).coerceAtLeast(0)
                windowManager.updateViewLayout(overlayView, layoutParams)
                posX = layoutParams.x
                posY = layoutParams.y
            },
            onDragEnd = {
                val metrics = resources.displayMetrics
                val snapped = EdgeDocking.snap(
                    layoutParams.x, layoutParams.y, shellWidthPx,
                    metrics.widthPixels, metrics.heightPixels,
                )
                layoutParams.x = snapped.first
                layoutParams.y = snapped.second
                dockEdge = EdgeDocking.detectEdge(
                    layoutParams.x, layoutParams.y, shellWidthPx,
                    metrics.widthPixels, metrics.heightPixels,
                )
                windowManager.updateViewLayout(overlayView, layoutParams)
                posX = layoutParams.x
                posY = layoutParams.y
                persistState()
            },
        )
    }

    private fun openCommandCentre() {
        startActivity(
            Intent(this, CommandCentreActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
        )
    }

    private fun persistState() {
        stateStore.save(
            OverlayPersistedState(
                x = posX,
                y = posY,
                mode = overlayMode,
                dock = dockEdge,
                serviceRunning = true,
            ),
        )
    }

    private fun buildNotification(): Notification {
        val channelId = CHANNEL_ID
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.createNotificationChannel(
            NotificationChannel(channelId, "Van overlay", NotificationManager.IMPORTANCE_LOW),
        )
        val pending = PendingIntent.getActivity(
            this, 0,
            Intent(this, CommandCentreActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, channelId)
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

        /** §5 recommended geometry: character 72–112dp visual height. */
        private const val CHARACTER_DP = 104
        private const val SHELL_WIDTH_DP = 150
        private const val CAPSULE_HEIGHT_DP = 60
        private const val COMPACT_HEIGHT_DP = 150
        private const val EXPANDED_WIDTH_DP = 250
        private const val EXPANDED_HEIGHT_DP = 128
        private const val TOUCH_TARGET_DP = 34

        fun start(context: Context) {
            context.startForegroundService(Intent(context, FloatingOverlayService::class.java))
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, FloatingOverlayService::class.java))
        }
    }
}
