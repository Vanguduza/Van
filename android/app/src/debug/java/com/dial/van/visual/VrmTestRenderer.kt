package com.dial.van.visual

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Color
import android.os.Handler
import android.os.Looper
import android.view.View
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import java.io.File
import java.io.FileInputStream

/**
 * DEBUG ONLY — draws an owner-imported VRM model in place of VAN (owner direction,
 * 2026-09-25: "use it as is to test").
 *
 * three.js and @pixiv/three-vrm (both MIT, bundled under `assets/vrm_test/`) render the model
 * in a transparent WebView, and VAN's live [VanVisualState] drives it: breathing and blinking
 * always, the mouth while he speaks, a head tilt while he listens, and his finite actions
 * (wave, nod, point, celebrate, shrug). The model file itself is imported on the device by
 * [VrmTestModelActivity]; it is never bundled, committed or shipped.
 */
object VrmTestModel {
    const val FILE_NAME = "van_test.vrm"

    fun file(context: Context): File = File(context.filesDir, FILE_NAME)
}

class VrmTestRenderer : VanTestModel.Renderer {

    override fun available(context: Context): Boolean = VrmTestModel.file(context).isFile

    @Composable
    override fun Render(
        state: VanVisualState,
        presentation: VanPresentation,
        modifier: Modifier,
        onFailed: () -> Unit,
    ) {
        val framing = if (presentation == VanPresentation.COMPACT) "bust" else "full"
        val failed by rememberUpdatedState(onFailed)
        val json = remember(state) { stateJson(state) }
        AndroidView(
            modifier = modifier,
            factory = { context -> createWebView(context, framing) { failed() } },
            update = { web -> web.evaluateJavascript("window.van && window.van.set($json)", null) },
        )
    }

    private fun stateJson(state: VanVisualState): String =
        "{\"state\":\"${state.durableState.name}\"," +
            "\"speaking\":${state.speaking},\"listening\":${state.listening}," +
            "\"mouth\":${state.mouthOpen},\"action\":${state.actionCode}," +
            "\"ax\":${state.attentionX},\"ay\":${state.attentionY}}"

    @SuppressLint("SetJavaScriptEnabled")
    private fun createWebView(context: Context, framing: String, onFailed: () -> Unit): WebView =
        WebView(context).apply {
            setBackgroundColor(Color.TRANSPARENT)
            setLayerType(View.LAYER_TYPE_HARDWARE, null)
            settings.javaScriptEnabled = true
            settings.allowFileAccess = false
            settings.allowContentAccess = false
            addJavascriptInterface(Bridge(onFailed), "VanBridge")
            webViewClient = AssetServer(context.applicationContext)
            loadUrl("https://$HOST/vrm/index.html?framing=$framing")
        }

    /** What the page reports back; only failure matters, so VAN can fall back to himself. */
    private class Bridge(private val onFailed: () -> Unit) {
        private val main = Handler(Looper.getMainLooper())

        @JavascriptInterface
        fun ready() = Unit

        @JavascriptInterface
        fun failed(message: String) {
            android.util.Log.w("VanVrmTest", "test model failed: $message")
            main.post(onFailed)
        }
    }

    /**
     * Serves the bundled renderer from `assets/vrm_test/` and the imported model from the
     * app's private files, on one https origin so ES modules and the model load same-origin.
     */
    private class AssetServer(private val context: Context) : WebViewClient() {
        override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
            val url = request.url
            if (url.host != HOST) return null
            val path = url.path.orEmpty()
            return runCatching {
                when {
                    path == "/model/${VrmTestModel.FILE_NAME}" ->
                        WebResourceResponse("model/gltf-binary", null, FileInputStream(VrmTestModel.file(context)))
                    path.startsWith("/vrm/") && !path.contains("..") ->
                        WebResourceResponse(mimeFor(path), "utf-8", context.assets.open("vrm_test/" + path.removePrefix("/vrm/")))
                    else -> null
                }
            }.getOrNull()
        }

        private fun mimeFor(path: String) = when {
            path.endsWith(".html") -> "text/html"
            path.endsWith(".js") -> "text/javascript"
            else -> "application/octet-stream"
        }
    }

    private companion object {
        const val HOST = "appassets.androidplatform.net"
    }
}
