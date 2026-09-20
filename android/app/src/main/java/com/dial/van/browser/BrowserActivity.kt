package com.dial.van.browser

import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.lifecycleScope
import com.dial.van.VanApplication
import com.dial.van.visual.VanTheme
import kotlinx.coroutines.launch
import org.webrtc.EglBase
import org.webrtc.RendererCommon

/**
 * Rev 1.5 §§7, 8 — the owner holding a browser that is running somewhere else.
 *
 * The Activity's job is small and specific: draw the remote frames, turn touches into
 * protocol packets, and — the part that matters — stop accepting touches the moment VAN is
 * no longer entitled to actuate. §7 names the failure directly: a frozen last frame with
 * live touch handling, where the owner keeps tapping a picture and the taps either vanish
 * or arrive somewhere unrecognisable a few seconds later.
 *
 * So there is exactly one gate, [BrowserSessionSnapshot.mayActuate], and it is consulted on
 * every motion event rather than cached in a boolean that something forgot to clear.
 *
 * The three things this deliberately does not do:
 *
 *  * it never asks to navigate. There is no URL bar and no gateway route for one;
 *    navigation is an actuation and is fenced by the control lease on the stream host;
 *  * it never renders while the control lease is held by an agent. Watching Hermes work is
 *    a view, and a view does not take input (ADR-RB-007);
 *  * it never reports the session as success or failure. §5.2 — a session is not an
 *    outcome, and `is_work_outcome` comes from the Gateway as false for exactly that
 *    reason.
 */
class BrowserActivity : FragmentActivity() {

    private lateinit var controller: BrowserSessionController
    private val eglBase: EglBase by lazy { EglBase.create() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val app = application as VanApplication
        val sessionId = intent.getStringExtra(EXTRA_SESSION_ID)
        val profileAlias = intent.getStringExtra(EXTRA_PROFILE_ALIAS) ?: "authenticated_owner"

        controller = BrowserSessionController(
            gateway = app.gatewayClient,
            stream = BrowserStreamClient(applicationContext, eglBase),
            scope = lifecycleScope,
        )

        setContent {
            VanTheme {
                val state by controller.state.collectAsState()
                BrowserSurface(state)
            }
        }

        lifecycleScope.launch {
            val configuration = resources.displayMetrics
            controller.open(
                existingSessionId = sessionId,
                profileAlias = profileAlias,
                widthPx = configuration.widthPixels,
                heightPx = configuration.heightPixels,
                deviceScaleFactor = configuration.density,
            )
        }
    }

    override fun onStop() {
        super.onStop()
        // §5.3 — a backgrounded phone stops heartbeating, and the Gateway's lease expires
        // on its own. Suspending explicitly means the owner's tabs are still there when
        // they come back, rather than a session that timed out into nothing.
        controller.suspendSession()
    }

    override fun onDestroy() {
        super.onDestroy()
        controller.close()
        eglBase.release()
    }

    @Composable
    private fun BrowserSurface(state: BrowserSessionController.State) {
        val widthDp = LocalConfiguration.current.screenWidthDp
        Column(Modifier.fillMaxSize().background(Color.Black)) {
            Text(
                text = state.ownerReadableState,
                color = MaterialTheme.colorScheme.onSurface,
                fontSize = if (BrowserWindowClass.forWidthDp(widthDp) == BrowserWindowClass.COMPACT) {
                    13.sp
                } else {
                    15.sp
                },
                modifier = Modifier.fillMaxWidth().padding(12.dp),
            )
            Box(Modifier.fillMaxSize()) {
                AndroidView(
                    modifier = Modifier.fillMaxSize(),
                    factory = { context ->
                        BrowserSurfaceView(context).apply {
                            init(eglBase.eglBaseContext, null)
                            setScalingType(RendererCommon.ScalingType.SCALE_ASPECT_FIT)
                            setEnableHardwareScaler(true)
                            // Focusable so the IME will open for the remote page's text
                            // fields; without this the owner taps an input, the caret
                            // appears on the far side, and no keyboard comes up here.
                            isFocusableInTouchMode = true
                            this.controller = this@BrowserActivity.controller
                            this@BrowserActivity.controller.attachRenderer(this)
                            requestFocus()
                        }
                    },
                )
            }
        }
    }

    companion object {
        const val EXTRA_SESSION_ID = "van.browser.session_id"
        const val EXTRA_PROFILE_ALIAS = "van.browser.profile_alias"
    }
}
