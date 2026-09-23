package com.dial.van.command.artemis

import android.graphics.Bitmap
import android.net.Uri
import android.webkit.CookieManager
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import com.dial.van.BuildConfig
import com.dial.van.VanApplication
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.components.SectionHeader

/**
 * The ARTEMIS web surface inside VAN.
 *
 * ARTEMIS remains a Hermes subordinate. This WebView never carries the Netcup console
 * bearer token. State-changing requests are accepted only by the narrow Hermes-governed
 * Netcup owner allowlist; privileged ARTEMIS admin mutations remain blocked.
 */
@Composable
fun ArtemisConsoleRoute(app: VanApplication, onBack: () -> Unit) {
    val tokens = LocalVanTokens.current
    var launchUrl by remember { mutableStateOf<String?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var loading by remember { mutableStateOf(true) }
    var webView by remember { mutableStateOf<WebView?>(null) }

    LaunchedEffect(Unit) {
        runCatching { app.gatewayClient.artemisConsoleSession().getString("launch_url") }
            .onSuccess {
                launchUrl = it
                error = null
            }
            .onFailure {
                loading = false
                error = it.message ?: "ARTEMIS console is unavailable."
            }
    }

    DisposableEffect(Unit) {
        onDispose {
            webView?.stopLoading()
            webView?.destroy()
            webView = null
        }
    }

    Column(
        modifier = Modifier.fillMaxSize().padding(horizontal = tokens.space.pageGutter),
        verticalArrangement = Arrangement.spacedBy(tokens.space.space2),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(top = tokens.space.space2),
            horizontalArrangement = Arrangement.spacedBy(tokens.space.space2),
        ) {
            Button(onClick = onBack) { Text("← Work") }
        }
        SectionHeader("ARTEMIS Android Lab", detail = "Hermes-governed • owner control console")
        Text(
            "Live device state, tasks, traces and diagnostics are shown here. Task start/stop, admitted device selection, admitted emulator launch and safe ADB recovery stay behind Hermes governance; credential, destructive-history and ARTEMIS lifecycle admin remain blocked.",
            style = tokens.type.label,
            color = tokens.color.textSecondary,
        )

        error?.let {
            Text(it, style = tokens.type.body, color = tokens.color.textSecondary)
        }

        if (launchUrl == null && error == null) {
            CircularProgressIndicator()
        } else {
            launchUrl?.let { url ->
                val allowed = remember(url) { Uri.parse(url) }
                AndroidView(
                    modifier = Modifier.fillMaxSize(),
                    factory = { context ->
                        CookieManager.getInstance().setAcceptCookie(true)
                        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
                        WebView(context).also { view ->
                            webView = view
                            CookieManager.getInstance().setAcceptThirdPartyCookies(view, false)
                            view.settings.javaScriptEnabled = true
                            view.settings.domStorageEnabled = true
                            view.settings.allowFileAccess = false
                            view.settings.allowContentAccess = false
                            view.settings.javaScriptCanOpenWindowsAutomatically = false
                            view.settings.setSupportMultipleWindows(false)
                            view.settings.mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
                            if (android.os.Build.VERSION.SDK_INT >= 26) {
                                view.settings.safeBrowsingEnabled = true
                            }
                            view.webViewClient = object : WebViewClient() {
                                override fun onPageStarted(v: WebView?, u: String?, favicon: Bitmap?) {
                                    loading = true
                                }
                                override fun onPageFinished(v: WebView?, u: String?) {
                                    loading = false
                                }
                                override fun shouldOverrideUrlLoading(v: WebView?, request: WebResourceRequest?): Boolean {
                                    val target = request?.url ?: return true
                                    return target.scheme != allowed.scheme ||
                                        target.host != allowed.host ||
                                        target.port != allowed.port
                                }
                            }
                            view.loadUrl(url)
                        }
                    },
                    update = { view ->
                        if (view.url == null) view.loadUrl(url)
                    },
                )
            }
        }
    }
}
