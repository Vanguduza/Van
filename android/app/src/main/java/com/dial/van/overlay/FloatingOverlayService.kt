package com.dial.van.overlay

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.PixelFormat
import android.os.IBinder
import android.view.Gravity
import android.view.WindowManager
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Chat
import androidx.compose.material.icons.filled.Dashboard
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.ComposeView
import androidx.compose.ui.unit.dp
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
import com.dial.van.visual.VanAvatar
import com.dial.van.visual.VanVisualState
import kotlinx.coroutines.flow.MutableStateFlow

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
    private val visualState = MutableStateFlow(VanVisualState())

    private var avatarSizePx = 0
    private var dragStartX = 0
    private var dragStartY = 0

    override fun onCreate() {
        super.onCreate()
        savedStateController.performRestore(null)
        lifecycleRegistry.currentState = Lifecycle.State.CREATED
        stateStore = OverlayStateStore(this)
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
        avatarSizePx = (AVATAR_DP * resources.displayMetrics.density).toInt()

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
            ACTION_TOGGLE_MODE -> overlayMode = if (overlayMode == OverlayMode.COMPACT) OverlayMode.EXPANDED else OverlayMode.COMPACT
            ACTION_OPEN_COMMAND -> startActivity(
                Intent(this, CommandCentreActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            )
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
        MaterialTheme {
            Surface(
                shape = RoundedCornerShape(16.dp),
                color = Color(0xCC111820),
                modifier = Modifier.pointerInput(Unit) {
                    detectDragGestures(
                        onDragStart = {
                            dragStartX = layoutParams.x
                            dragStartY = layoutParams.y
                        },
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
                                layoutParams.x, layoutParams.y, avatarSizePx,
                                metrics.widthPixels, metrics.heightPixels,
                            )
                            layoutParams.x = snapped.first
                            layoutParams.y = snapped.second
                            dockEdge = EdgeDocking.detectEdge(
                                layoutParams.x, layoutParams.y, avatarSizePx,
                                metrics.widthPixels, metrics.heightPixels,
                            )
                            windowManager.updateViewLayout(overlayView, layoutParams)
                            posX = layoutParams.x
                            posY = layoutParams.y
                            persistState()
                        },
                    )
                },
            ) {
                val avatarState by visualState.collectAsState()
                if (overlayMode == OverlayMode.COMPACT) {
                    Box(
                        modifier = Modifier
                            .size(AVATAR_DP.dp)
                            .clickable { overlayMode = OverlayMode.EXPANDED },
                        contentAlignment = Alignment.Center,
                    ) {
                        VanAvatar(state = avatarState, modifier = Modifier.size(AVATAR_DP.dp))
                    }
                } else {
                    Column(modifier = Modifier.padding(8.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            VanAvatar(state = avatarState, modifier = Modifier.size(AVATAR_DP.dp))
                            Column(modifier = Modifier.padding(start = 8.dp)) {
                                Text("Van", color = Color.White)
                                Text(app.degradedModeStore.snapshot().let {
                                    if (it.active) "Degraded" else "Ready"
                                }, color = Color(0xFF00E5FF))
                            }
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            IconButton(onClick = {
                                app.voiceSession.beginOwnerTurn()
                                visualState.value = visualState.value.copy(listening = true)
                            }) {
                                Icon(Icons.Default.Mic, contentDescription = "Voice", tint = Color.White)
                            }
                            IconButton(onClick = {
                                startActivity(Intent(this@FloatingOverlayService, CommandCentreActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                            }) {
                                Icon(Icons.Default.Dashboard, contentDescription = "Command Centre", tint = Color.White)
                            }
                            IconButton(onClick = { overlayMode = OverlayMode.COMPACT }) {
                                Icon(Icons.Default.Chat, contentDescription = "Compact", tint = Color.White)
                            }
                        }
                    }
                }
            }
        }
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
        private const val AVATAR_DP = 72

        fun start(context: Context) {
            context.startForegroundService(Intent(context, FloatingOverlayService::class.java))
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, FloatingOverlayService::class.java))
        }
    }
}
