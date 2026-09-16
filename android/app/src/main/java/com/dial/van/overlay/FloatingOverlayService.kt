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
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
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
import com.dial.van.visual.VanLiveVisualState
import com.dial.van.visual.VanPresence
import com.dial.van.visual.VanPresentation
import com.dial.van.visual.VanStatusPalette
import com.dial.van.visual.rememberVanEffectBudget

/**
 * Floating Van overlay.
 *
 * Rev 2.1: rest is frameless VAN + living aura. Interaction condenses that field into glass.
 * VAN overlaps the condensed panel. Dock is an intentional crescent edge slice, not a cyan bar.
 */
class FloatingOverlayService : Service(), LifecycleOwner, SavedStateRegistryOwner {

    private lateinit var windowManager: WindowManager
    private lateinit var overlayView: ComposeView
    private lateinit var layoutParams: WindowManager.LayoutParams
    private lateinit var stateStore: OverlayStateStore

    private val lifecycleRegistry = LifecycleRegistry(this)
    private val savedStateController = SavedStateRegistryController.create(this)

    private var overlayMode by mutableStateOf(OverlayMode.RESTING)
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
            ACTION_TOGGLE_MODE -> overlayMode = when (overlayMode) {
                OverlayMode.RESTING -> OverlayMode.COMPACT
                OverlayMode.COMPACT -> OverlayMode.EXPANDED
                OverlayMode.EXPANDED, OverlayMode.DOCKED -> OverlayMode.RESTING
            }
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
        // Snapshot-backed live state is read in this composition so voice/task changes recompose
        // the complete shell: aura, character, caption, glass style and semantic accent stay in sync.
        val liveState = VanLiveVisualState.current
        val cue = VanPresence.cue(degraded, live = liveState)
        val visualState = VanPresence.visualState(cue, liveState)
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
                    OverlayMode.RESTING -> RestingPresence(
                        budget = budget,
                        visualState = visualState,
                    )

                    OverlayMode.DOCKED -> DockedPresence(
                        budget = budget,
                        visualState = visualState,
                    )

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
     * Resting floating VAN: character and living aura only. Glass has not condensed yet.
     */
    @Composable
    private fun RestingPresence(
        budget: com.dial.van.visual.VanEffectBudget,
        visualState: com.dial.van.visual.VanVisualState,
    ) {
        Box(
            modifier = Modifier
                .size(OverlayTheme.RESTING_HIT_DP.dp)
                .semantics { contentDescription = "Van resting. Tap to form glass." }
                .clickable {
                    overlayMode = OverlayMode.COMPACT
                    persistState()
                },
            contentAlignment = Alignment.Center,
        ) {
            VanEmbodiment(
                state = visualState,
                budget = budget,
                presentation = VanPresentation.COMPACT,
                characterFraction = OverlayTheme.RESTING_AVATAR_DP / OverlayTheme.RESTING_HIT_DP.toFloat(),
                modifier = Modifier.fillMaxSize(),
            )
        }
    }

    /**
     * Compact interaction: glass condenses from the aura. VAN overlaps the panel so the
     * surface reads as generated by him, not attached beside him.
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
            modifier = Modifier
                .width(OverlayTheme.COMPACT_WIDTH_DP.dp)
                .height(COMPACT_HEIGHT_DP.dp),
            contentAlignment = Alignment.TopStart,
        ) {
            VanGlassSurface(
                style = glass,
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .height(OverlayTheme.COMPACT_CAPSULE_HEIGHT_DP.dp),
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(start = 88.dp, end = 10.dp, top = 8.dp, bottom = 8.dp),
                ) {
                    Text(
                        text = caption,
                        color = Color(accent),
                        fontSize = 11.sp,
                        fontWeight = FontWeight.SemiBold,
                        maxLines = 1,
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    OverlayTheme.COMPACT_ACTIONS.chunked(2).forEach { row ->
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            row.forEach { label ->
                                CompactChip(label, accent) {
                                    when (label) {
                                        "Ask" -> app.voiceSession.beginOwnerTurn()
                                        else -> openCommandCentre()
                                    }
                                }
                            }
                        }
                        Spacer(modifier = Modifier.height(4.dp))
                    }
                }
            }

            VanEmbodiment(
                state = visualState,
                budget = budget,
                presentation = VanPresentation.COMPACT,
                modifier = Modifier
                    .size(OverlayTheme.RESTING_AVATAR_DP.dp)
                    .offset(x = (-4).dp)
                    .clickable {
                        overlayMode = OverlayMode.EXPANDED
                        persistState()
                    },
            )
        }
    }

    /** Expanded working surface: glass grown from VAN, actions inside the same field. */
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
        val solid = glass.requiresSolidControls
        Box(
            modifier = Modifier
                .width(OverlayTheme.EXPANDED_WIDTH_DP.dp)
                .height(OverlayTheme.EXPANDED_HEIGHT_DP.dp),
            contentAlignment = Alignment.TopStart,
        ) {
            VanGlassSurface(
                style = glass,
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .height((OverlayTheme.EXPANDED_HEIGHT_DP - 18).dp),
            ) {
                Column(modifier = Modifier.padding(start = 100.dp, end = 12.dp, top = 10.dp, bottom = 8.dp)) {
                    Text("Van", color = Color.White, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                    Text(text = headline, color = Color(accent), fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                    Text(text = caption, color = Color(0xFFB6C2D0), fontSize = 11.sp, maxLines = 2)
                    Text(text = meshCue, color = Color(0xFF8A97A6), fontSize = 10.sp, maxLines = 1)
                    Spacer(modifier = Modifier.height(6.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        OverlayTheme.COMPACT_ACTIONS.forEach { label ->
                            CompactChip(label, accent) {
                                when (label) {
                                    "Ask" -> app.voiceSession.beginOwnerTurn()
                                    else -> openCommandCentre()
                                }
                            }
                        }
                        CompactChip("Dock", accent) {
                            overlayMode = OverlayMode.DOCKED
                            persistState()
                        }
                    }
                    if (solid) {
                        Spacer(modifier = Modifier.height(6.dp))
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(36.dp)
                                .clip(RoundedCornerShape(10.dp))
                                .background(Color(glass.borderColor))
                                .clickable { openCommandCentre() },
                            contentAlignment = Alignment.Center,
                        ) {
                            Text("Approve", color = Color(0xFF10151F), fontWeight = FontWeight.Bold, fontSize = 12.sp)
                        }
                    }
                }
            }

            VanEmbodiment(
                state = visualState,
                budget = budget,
                presentation = VanPresentation.EXPANDED,
                modifier = Modifier
                    .align(Alignment.TopStart)
                    .offset(x = (-6).dp, y = (-2).dp)
                    .size(OverlayTheme.RESTING_AVATAR_DP.dp)
                    .clickable { openCommandCentre() },
            )
        }
    }

    /**
     * Intentional edge dock: 88dp hit, 76dp character. Face/visor stay fully on-screen;
     * body crops at the bottom. Crescent field sits toward the screen interior.
     */
    @Composable
    private fun DockedPresence(
        budget: com.dial.van.visual.VanEffectBudget,
        visualState: com.dial.van.visual.VanVisualState,
    ) {
        Box(
            modifier = Modifier
                .size(width = OverlayTheme.DOCK_WIDTH_DP.dp, height = OverlayTheme.DOCK_HIT_DP.dp)
                .semantics { contentDescription = "Van docked. Tap to restore." }
                .clickable {
                    overlayMode = OverlayMode.RESTING
                    persistState()
                },
        ) {
            androidx.compose.foundation.Canvas(modifier = Modifier.fillMaxWidth().height(OverlayTheme.DOCK_HIT_DP.dp)) {
                val field = Color(VanGlassTokens.ACCENT_CYAN).copy(alpha = 0.28f)
                val path = androidx.compose.ui.graphics.Path()
                path.moveTo(size.width * 0.08f, size.height * 0.12f)
                path.quadraticBezierTo(size.width * 0.95f, size.height * 0.08f, size.width, size.height * 0.42f)
                path.quadraticBezierTo(size.width * 0.92f, size.height * 0.92f, size.width * 0.10f, size.height * 0.88f)
                path.quadraticBezierTo(size.width * 0.02f, size.height * 0.50f, size.width * 0.08f, size.height * 0.12f)
                path.close()
                drawPath(path, field)
            }
            VanEmbodiment(
                state = visualState,
                budget = budget,
                presentation = VanPresentation.COMPACT,
                modifier = Modifier
                    .size(OverlayTheme.DOCK_CHARACTER_DP.dp)
                    .align(Alignment.TopCenter)
                    .offset(y = (-4).dp),
            )
        }
    }

    @Composable
    private fun CompactChip(label: String, accent: Int, onClick: () -> Unit) {
        Box(
            modifier = Modifier
                .height(32.dp)
                .clip(RoundedCornerShape(10.dp))
                .background(Color(accent).copy(alpha = 0.16f))
                .clickable(onClick = onClick)
                .padding(horizontal = 8.dp),
            contentAlignment = Alignment.Center,
        ) {
            Text(label, color = Color(0xFFE7ECF2), fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
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

        private const val SHELL_WIDTH_DP = OverlayTheme.COMPACT_WIDTH_DP
        private const val COMPACT_HEIGHT_DP =
            OverlayTheme.RESTING_AVATAR_DP + OverlayTheme.COMPACT_CAPSULE_HEIGHT_DP - OverlayTheme.VAN_GLASS_OVERLAP_DP

        fun start(context: Context) {
            context.startForegroundService(Intent(context, FloatingOverlayService::class.java))
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, FloatingOverlayService::class.java))
        }
    }
}
