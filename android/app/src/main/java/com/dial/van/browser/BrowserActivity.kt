package com.dial.van.browser

import android.content.Intent
import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.TextButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
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
import androidx.compose.ui.viewinterop.AndroidView
import androidx.activity.OnBackPressedCallback
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.lifecycleScope
import com.dial.van.VanApplication
import com.dial.van.design.LocalVanTokens
import com.dial.van.visual.VanLiveVisualState
import com.dial.van.visual.VanTheme
import kotlinx.coroutines.launch
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
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
    private lateinit var phoneActions: BrowserPhoneActions
    private var surfaceWidth = 0
    private var surfaceHeight = 0
    private var resizeSettle: Job? = null
    private var browserView: BrowserSurfaceView? = null
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

        phoneActions = BrowserPhoneActions(this, app.gatewayClient, controller)

        // §17.6 — Back closes the panel, then the address edit, then goes back in the
        // page, and only then leaves. The order is the specification, and the last clause
        // is why this is registered at all: Android's default would close the browser
        // while the owner is three pages into a site.
        onBackPressedDispatcher.addCallback(
            this,
            object : OnBackPressedCallback(true) {
                override fun handleOnBackPressed() {
                    val outcome = controller.onBackPressed(
                        transientPanelOpen = downloadsPanelOpen || sessionPanelOpen || actionPlansPanelOpen,
                        addressBarEditing = addressBarEditing,
                    )
                    when (outcome) {
                        BackOutcome.CLOSE_TRANSIENT_PANEL -> { downloadsPanelOpen = false; sessionPanelOpen = false; actionPlansPanelOpen = false }
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
                    proposeMeasuredViewport()
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
            proposeMeasuredViewport()
            intent.getStringExtra(EXTRA_EXTERNAL_URL)?.let(controller::openExternalUrl)
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
        proposeMeasuredViewport()
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        // Focus returning is the closest signal an Activity gets to "the drag stopped",
        // so the settle message goes here rather than waiting for the debounce.
        if (hasFocus && ::phoneActions.isInitialized && !phoneActions.pending)
            controller.onWindowTick(System.currentTimeMillis(), settled = true)
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
            contentWidthPx = surfaceWidth.takeIf { it > 0 } ?: contentWidth,
            contentHeightPx = surfaceHeight.takeIf { it > 0 } ?: contentHeight,
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

    private var addressBarEditing: Boolean = false
    private var downloadsPanelOpen by mutableStateOf(false)
    private var sessionPanelOpen by mutableStateOf(false)
    private var actionPlansPanelOpen by mutableStateOf(false)

    /** Called only for a chooser observed on the current media peer. */
    fun onFileChooserRequested(request: FileChooserRequest) = phoneActions.choose(request)

    private fun proposeMeasuredViewport() {
        if (!::controller.isInitialized || surfaceWidth <= 0 || surfaceHeight <= 0) return
        // SAF and IME transitions must not replace the epoch of an in-flight one-use file action.
        if (::phoneActions.isInitialized && phoneActions.pending) return
        controller.onWindowChanged(currentViewport(), System.currentTimeMillis())
        resizeSettle?.cancel()
        resizeSettle = lifecycleScope.launch {
            delay(ResizeCoalescer.STABILITY_MS)
            if (!phoneActions.pending) controller.onWindowTick(System.currentTimeMillis(), settled = true)
        }
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
        // The system SAF picker is part of this explicit file action. Suspending here
        // would revoke the chooser before its selected URI is returned.
        if (!phoneActions.externalPickerOpen) controller.suspendSession()
    }

    override fun onStart() {
        super.onStart()
        if (::controller.isInitialized && controller.state.value.snapshot?.state == BrowserSessionState.SUSPENDED &&
            !phoneActions.externalPickerOpen) controller.reconnect()
    }

    override fun onDestroy() {
        super.onDestroy()
        phoneActions.close()
        controller.close()
        eglBase.release()
    }

    @Composable
    private fun BrowserSurface(state: BrowserSessionController.State) {
        val tokens = LocalVanTokens.current
        LaunchedEffect(phoneActions.pending) { if (!phoneActions.pending) proposeMeasuredViewport() }
        val widthDp = LocalConfiguration.current.screenWidthDp
        val chrome = BrowserWindowClass.forWidthDp(widthDp)
        Column(Modifier.fillMaxSize().background(Color.Black)) {
            Text(
                text = state.ownerReadableState,
                color = MaterialTheme.colorScheme.onSurface,
                style = if (chrome == BrowserWindowClass.COMPACT) tokens.type.data else tokens.type.body,
                modifier = Modifier.fillMaxWidth().padding(12.dp),
            )
            Text(state.transferNotice.orEmpty(), color = MaterialTheme.colorScheme.onSurface,
                maxLines = 2, style = tokens.type.label, modifier = Modifier.fillMaxWidth().height(36.dp).padding(horizontal = 12.dp))
            AddressBar(chrome)
            Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp).horizontalScroll(rememberScrollState())) {
                OutlinedButton(enabled = controller.mayActuate() && state.tabState.active?.canGoBack == true,
                    onClick = { controller.historyBack() }) { Text("Back") }
                OutlinedButton(enabled = controller.mayActuate() && state.tabState.active?.canGoForward == true,
                    onClick = { controller.goForward() }) { Text("Forward") }
                OutlinedButton(enabled = controller.mayActuate(), onClick = { controller.reload() }) { Text("Reload") }
                OutlinedButton(enabled = controller.mayActuate() && state.tabState.active?.loading == true,
                    onClick = { controller.stopLoading() }) { Text("Stop") }
                OutlinedButton(enabled = controller.mayActuate(), onClick = {
                    browserView?.let { view ->
                        view.requestFocus()
                        (getSystemService(android.content.Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager)
                            .showSoftInput(view, android.view.inputmethod.InputMethodManager.SHOW_IMPLICIT)
                    }
                }) { Text("Keyboard") }
            }
            if (state.snapshot?.controlHolder?.isAgent == true) {
                OutlinedButton(enabled = BrowserControlMutation.mayRequestControl(state.snapshot!!, state.controlUncertain, state.controlMutationPending),
                    onClick = { controller.takeControl() }, modifier = Modifier.padding(horizontal = 12.dp)) {
                    Text(if (state.controlMutationPending) "Confirming control…" else "Take control")
                }
            }
            Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp).horizontalScroll(rememberScrollState())) {
                OutlinedButton(enabled = state.snapshot != null, onClick = { downloadsPanelOpen = true }) {
                    Text("Downloads & phone files")
                }
                OutlinedButton(enabled = state.snapshot != null, onClick = { sessionPanelOpen = true }) {
                    Text("Control & history")
                }
                OutlinedButton(enabled = state.snapshot != null && !state.controlUncertain, onClick = { actionPlansPanelOpen = true }) {
                    Text("Exact effect plans")
                }
                OutlinedButton(enabled = state.snapshot?.state?.isTerminal == false && !state.controlMutationPending,
                    onClick = controller::reconnect) { Text("Reconnect") }
            }
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
                            browserView = this
                            onSurfaceSize = { width, height ->
                                surfaceWidth = width; surfaceHeight = height
                                proposeMeasuredViewport()
                            }
                            this@BrowserActivity.controller.attachRenderer(this)
                            requestFocus()
                        }
                    },
                )
            }
        }
        state.pendingChooser?.let { request ->
            AlertDialog(onDismissRequest = { if (!phoneActions.pending) controller.reportUploadRefused(UploadRefusal.OWNER_CANCELLED) },
                title = { Text("Send a phone file to this page?") },
                text = { Text("Choose one file. VAN sends it only to the requesting page; this does not authorize file analysis. Limit: 64 MiB.") },
                confirmButton = { TextButton(enabled = !phoneActions.pending && controller.mayActuate(),
                    onClick = { onFileChooserRequested(request) }) { Text(if (phoneActions.pending) "Choosing or sending…" else "Choose file…") } },
                dismissButton = { TextButton(enabled = !phoneActions.pending,
                    onClick = { controller.reportUploadRefused(UploadRefusal.OWNER_CANCELLED) }) { Text("Cancel") } })
        }
        state.snapshot?.let { snapshot ->
            if (actionPlansPanelOpen) BrowserActionPlansPanel(application as VanApplication, this, snapshot,
                onDismiss = { actionPlansPanelOpen = false })
            if (sessionPanelOpen) BrowserSessionPanel(
                gateway = (application as VanApplication).gatewayClient, state = state,
                onDelegate = controller::delegateControl, onDismiss = { sessionPanelOpen = false },
            )
            if (downloadsPanelOpen) BrowserDownloadsPanel(
                gateway = (application as VanApplication).gatewayClient,
                sessionId = snapshot.sessionId,
                onDismiss = { downloadsPanelOpen = false },
                onSaveToPhone = phoneActions::saveToPhone,
                transferPending = phoneActions.pending,
                transferAvailable = controller.transferContext() != null,
                onPaste = phoneActions::pastePhoneClipboard,
                onCopy = phoneActions::copyBrowserSelection,
                transferNotice = state.transferNotice,
                onImport = phoneActions::importPhoneFile,
                onAnalyse = phoneActions::analyse,
                onOpen = phoneActions::openInVan,
                onRecover = phoneActions::recoverFileOutcome,
                ownerApp = application as VanApplication,
                ownerActivity = this,
            )
        }
        phoneActions.preview?.let { BrowserInertFileDialog(it, phoneActions::dismissPreview) }
        phoneActions.inspection?.let { BrowserInspectionDialog(it, phoneActions::dismissInspection) }
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
