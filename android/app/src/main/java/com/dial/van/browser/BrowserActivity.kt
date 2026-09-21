package com.dial.van.browser

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.activity.OnBackPressedCallback
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.lifecycleScope
import com.dial.van.VanApplication
import com.dial.van.visual.VanLiveVisualState
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
            // Rev 1.5 §28.1 — the application's reporter, not a new one. Four of the
            // eleven browser metrics can only be measured where the frames arrive, and a
            // second reporter would buffer them into a flush loop nobody started.
            stream = BrowserStreamClient(applicationContext, eglBase, app.telemetry),
            scope = lifecycleScope,
            // §24 — the browser proposes, the arbitration decides, and the embodiment is
            // told only when it wins. A trading warning is never displaced by a page load.
            visual = { state -> VanLiveVisualState.transition(state) },
            visualNow = { VanLiveVisualState.frame.poseState },
        )

        // §17.6 — Back closes the panel, then the address edit, then goes back in the
        // page, and only then leaves. The order is the specification, and the last clause
        // is why this is registered at all: Android's default would close the browser
        // while the owner is three pages into a site.
        onBackPressedDispatcher.addCallback(
            this,
            object : OnBackPressedCallback(true) {
                override fun handleOnBackPressed() {
                    val outcome = controller.onBackPressed(
                        transientPanelOpen = false,
                        addressBarEditing = addressBarEditing,
                    )
                    when (outcome) {
                        BackOutcome.CLOSE_TRANSIENT_PANEL -> Unit
                        BackOutcome.LEAVE_ADDRESS_EDIT -> addressBarEditing = false
                        BackOutcome.BROWSER_BACK -> Unit
                        BackOutcome.ACTIVITY_BACK -> {
                            isEnabled = false
                            onBackPressedDispatcher.onBackPressed()
                        }
                    }
                }
            },
        )

        setContent {
            VanTheme {
                val state by controller.state.collectAsState()
                BrowserSurface(state)
            }
        }

        lifecycleScope.launch {
            // §29.10 — the process may have been killed since the owner last looked. The
            // record supplies a session id to *ask* about; whether it is still there is
            // the Gateway's answer, and nothing from the record is shown before it comes.
            if (sessionId == null) {
                val restored = controller.resumeAfterProcessDeath(
                    persisted = app.restorePersistedBrowserSession(),
                    nowMs = System.currentTimeMillis(),
                )
                if (restored.disposition == RestoreDisposition.CONFIRMED_BY_GATEWAY) {
                    return@launch
                }
                // Gone, or nothing to restore. Clear it so the next start does not ask
                // about a session the Gateway has already said is finished.
                app.clearPersistedBrowserSession()
            }
            val configuration = resources.displayMetrics
            controller.open(
                existingSessionId = sessionId,
                profileAlias = profileAlias,
                widthPx = configuration.widthPixels,
                heightPx = configuration.heightPixels,
                deviceScaleFactor = configuration.density,
            )
            // §17.5 / ADR-RB-023 — an address from outside VAN, opened once the session
            // exists. It travels the same fenced navigation path as anything the owner
            // types, so an external link cannot reach the page by a route a tap cannot.
            intent.getStringExtra(EXTRA_EXTERNAL_URL)?.let(controller::navigateTo)
        }
    }

    /**
     * §12.3 — the window changed shape.
     *
     * `onConfigurationChanged` rather than an Activity recreation, because ADR-RB-021
     * declares the configuration changes this Activity handles itself: a pop-up window
     * being dragged must not tear down the remote session (ADR-RB-022), and an Activity
     * that let Android recreate it would do exactly that.
     */
    override fun onConfigurationChanged(newConfig: android.content.res.Configuration) {
        super.onConfigurationChanged(newConfig)
        controller.onWindowChanged(currentViewport(), System.currentTimeMillis())
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        // Focus returning is the closest signal an Activity gets to "the drag stopped",
        // so the settle message goes here rather than waiting for the debounce.
        if (hasFocus) controller.onWindowTick(System.currentTimeMillis(), settled = true)
    }

    /** §12.1 / §12.4 — the content rectangle and everything the host resizes against. */
    private fun currentViewport(): ViewportCandidate {
        val metrics = resources.displayMetrics
        val insets = Insets.NONE
        val chromeInsets = Insets.NONE
        val (contentWidth, contentHeight) = ContentViewport.compute(
            windowWidthPx = metrics.widthPixels,
            windowHeightPx = metrics.heightPixels,
            systemInsets = insets,
            chromeInsets = chromeInsets,
        )
        return ViewportCandidate(
            // The Gateway issues the revision; this is the phone's proposal number and is
            // replaced by the server's answer before anything is drawn against it.
            revision = 0,
            androidWindowWidthPx = metrics.widthPixels,
            androidWindowHeightPx = metrics.heightPixels,
            contentWidthPx = contentWidth,
            contentHeightPx = contentHeight,
            density = metrics.density,
            fontScale = resources.configuration.fontScale,
            displayRotation = if (android.os.Build.VERSION.SDK_INT >= 30) {
                display?.rotation ?: 0
            } else {
                0
            },
            windowMode = windowMode(),
            systemInsetsPx = insets,
            browserChromeInsetsPx = chromeInsets,
        )
    }

    /**
     * §12.4 — informational, and never a basis for authority.
     *
     * Android tells an Activity whether it is in multi-window mode and, from API 31,
     * whether the task is in a freeform window. It does not distinguish Samsung's pop-up
     * view from a desktop freeform one, so the label stops at what the OS actually says
     * rather than guessing.
     */
    private fun windowMode(): WindowMode = when {
        android.os.Build.VERSION.SDK_INT >= 24 && isInMultiWindowMode -> WindowMode.SPLIT
        else -> WindowMode.FULLSCREEN
    }

    /**
     * §19 — the page asked for a file and the owner picked one.
     *
     * Registered here rather than created on demand because `ActivityResultLauncher` has
     * to exist before the Activity is started; one created when the page asks arrives too
     * late and throws.
     */
    private val documentPicker = registerForActivityResult(
        ActivityResultContracts.OpenDocument(),
    ) { uri: Uri? -> onDocumentChosen(uri) }

    private var pendingChooser: FileChooserRequest? = null

    /** §17.2 — whether the owner is editing the address, which Back consults. */
    private var addressBarEditing: Boolean = false

    /** §19 steps 1-3: the page asked, so VAN asks the owner. */
    fun onFileChooserRequested(request: FileChooserRequest) {
        pendingChooser = request
        documentPicker.launch(
            request.acceptTypes.filter { it.contains('/') }.toTypedArray()
                .ifEmpty { arrayOf("*/*") },
        )
    }

    private fun onDocumentChosen(uri: Uri?) {
        val request = pendingChooser ?: return
        pendingChooser = null
        if (uri == null) return
        val (displayName, byteSize) = describe(uri)
        val refusal = BrowserUploadPolicy.admit(
            request = request,
            displayName = displayName,
            byteSize = byteSize,
            declaredMime = contentResolver.getType(uri) ?: "application/octet-stream",
            liveSessionId = controller.state.value.snapshot?.sessionId.orEmpty(),
        )
        if (refusal != null) {
            // Refused before the bytes move. §19's transfer is the expensive step and the
            // owner pays for it; discovering afterwards that the page will not take the
            // file is the outcome this ordering exists to avoid.
            controller.reportUploadRefused(refusal)
            return
        }
        controller.beginUpload(request, displayName, byteSize)
    }

    private fun describe(uri: Uri): Pair<String, Long> {
        contentResolver.query(uri, null, null, null, null)?.use { cursor ->
            if (cursor.moveToFirst()) {
                val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                val sizeIndex = cursor.getColumnIndex(OpenableColumns.SIZE)
                return Pair(
                    if (nameIndex >= 0) cursor.getString(nameIndex).orEmpty() else "",
                    if (sizeIndex >= 0) cursor.getLong(sizeIndex) else 0L,
                )
            }
        }
        return Pair("", 0L)
    }

    override fun onStop() {
        super.onStop()
        // §29.10 step 1 — written before the process can be killed. A record written only
        // here is already missing whatever happened after the owner last backgrounded the
        // app, which is why the controller can produce one at any moment.
        val app = application as VanApplication
        controller.persistable(System.currentTimeMillis())
            ?.let(app::persistBrowserSession)
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
        val chrome = BrowserWindowClass.forWidthDp(widthDp)
        Column(Modifier.fillMaxSize().background(Color.Black)) {
            Text(
                text = state.ownerReadableState,
                color = MaterialTheme.colorScheme.onSurface,
                fontSize = if (chrome == BrowserWindowClass.COMPACT) 13.sp else 15.sp,
                modifier = Modifier.fillMaxWidth().padding(12.dp),
            )
            AddressBar(chrome)
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

    /**
     * §17.2 — the address bar.
     *
     * What the owner typed is classified on the phone by [BrowserOmnibox] and the
     * *result* travels: the host is told "navigate here" or "search for this" rather than
     * handed raw text to guess about, because a host that guessed would guess differently
     * from the bar the owner is looking at.
     *
     * No suggestions are requested. `SuggestionPolicy.OFF` is the default and this
     * composable has no path to change it — an address bar is where people type things
     * they have not decided to say.
     */
    @Composable
    private fun AddressBar(chrome: BrowserWindowClass) {
        var typed by remember { mutableStateOf("") }
        OutlinedTextField(
            value = typed,
            onValueChange = {
                typed = it
                addressBarEditing = it.isNotEmpty()
            },
            singleLine = true,
            label = {
                Text(
                    if (chrome == BrowserWindowClass.COMPACT) "Address" else "Address or search",
                )
            },
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Go),
            keyboardActions = KeyboardActions(
                onGo = {
                    controller.onOmniboxCommitted(typed)
                    addressBarEditing = false
                },
            ),
            modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp),
        )
    }

    companion object {
        const val EXTRA_SESSION_ID = "van.browser.session_id"
        const val EXTRA_PROFILE_ALIAS = "van.browser.profile_alias"

        /**
         * §17.5 / ADR-RB-023 — an address another app or a shortcut supplied.
         *
         * Separate from a session id because it is not one: it is a place to go once the
         * session exists, and it arrives from outside VAN's trust boundary.
         */
        const val EXTRA_EXTERNAL_URL = "van.browser.external_url"
    }
}
