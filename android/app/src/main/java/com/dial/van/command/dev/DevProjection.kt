package com.dial.van.command.dev

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import com.dial.van.VanApplication
import com.dial.van.design.ScreenState
import com.dial.van.dialdev.DialDevEnvelope
import com.dial.van.dialdev.DialDevFetch
import com.dial.van.dialdev.DialDevFreshness
import com.dial.van.dialdev.DialDevScreenReducer
import com.dial.van.dialdev.DialDevSse
import com.dial.van.gateway.GatewayHttpException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.retryWhen
import kotlinx.coroutines.launch
import java.io.IOException

/**
 * One DIAL projection read as a screen holds it: the reducer's inputs (`DialDevFetch`, the
 * last good projection) and the [ScreenState] they reduce to. [envelope] is what an owner
 * action is decided against — its `projection_revision` becomes the action's
 * `expected_projection_revision`, and there is no action without one.
 */
class DevProjection<T>(
    val state: ScreenState<T>,
    val envelope: DialDevEnvelope?,
    val online: Boolean,
    val reload: () -> Unit,
    val setAwaitingOutcome: (Boolean) -> Unit,
) {
    val revision: String? get() = envelope?.projectionRevision
}

/**
 * The one fetch loop every development screen uses.
 *
 * - First read on entry; then a refetch whenever `GET /v1/dial-dev/events` reports a change to
 *   one of [sections] (SSE), with a poll at the route's stale threshold as the fallback for a
 *   dropped or unavailable stream — and every 3 s while an owner action awaits its outcome.
 * - Offline: the only thing queued is this read refresh, which re-runs on the next tick; owner
 *   actions are never queued (see `DevActions`).
 * - Everything the owner sees comes from [DialDevScreenReducer], which is pure and executed in
 *   `android/verification`.
 */
@Composable
fun <T> rememberDevProjection(
    app: VanApplication,
    key: Any?,
    sections: Set<String>,
    emptySentence: String,
    staleThresholdMs: Long = DialDevFreshness.DEFAULT_STALE_MS,
    isEmpty: (T) -> Boolean = { false },
    parse: (DialDevEnvelope) -> T?,
    fetch: suspend () -> String,
): DevProjection<T> {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var fetchState by remember(key) { mutableStateOf<DialDevFetch>(DialDevFetch.Loading) }
    var lastGood by remember(key) { mutableStateOf<DialDevFetch.Loaded?>(null) }
    var now by remember(key) { mutableStateOf(System.currentTimeMillis()) }
    var awaitingOutcome by remember(key) { mutableStateOf(false) }
    var online by remember(key) { mutableStateOf(true) }

    val reload: () -> Unit = {
        scope.launch {
            online = DevNetwork.isOnline(context)
            if (!online) {
                fetchState = DialDevFetch.Offline
                now = System.currentTimeMillis()
                return@launch
            }
            fetchState = try {
                val body = fetch()
                val envelope = DialDevEnvelope.parse(body)
                if (envelope == null) {
                    DialDevFetch.Failed(null, body, "The gateway answered, but not with a DIAL projection.")
                } else {
                    DialDevFetch.Loaded(envelope, System.currentTimeMillis()).also { lastGood = it }
                }
            } catch (cancel: CancellationException) {
                throw cancel
            } catch (http: GatewayHttpException) {
                DialDevFetch.Failed(http.code, http.body, null)
            } catch (io: IOException) {
                online = DevNetwork.isOnline(context)
                if (online) DialDevFetch.Failed(null, "", "VAN could not reach its gateway.") else DialDevFetch.Offline
            } catch (other: Exception) {
                DialDevFetch.Failed(null, "", other.message ?: "VAN could not read DIAL development state.")
            }
            now = System.currentTimeMillis()
        }
        Unit
    }

    LaunchedEffect(key) { reload() }
    LaunchedEffect(key, awaitingOutcome) {
        while (true) {
            delay(if (awaitingOutcome) AWAITING_POLL_MS else staleThresholdMs)
            reload()
        }
    }
    LaunchedEffect(key) {
        app.gatewayClient.dialDev.events()
            .retryWhen { cause, attempt ->
                // A gateway without the stream (404) is answered by the poll above, not retried.
                val missing = cause is GatewayHttpException && cause.code == 404
                if (!missing) delay((2_000L shl attempt.toInt().coerceAtMost(4)).coerceAtMost(30_000L))
                !missing
            }
            .catch { }
            .collect { change -> if (DialDevSse.affects(change, sections)) reload() }
    }

    val state = DialDevScreenReducer.reduce(fetchState, lastGood, now, staleThresholdMs, parse, isEmpty, emptySentence)
    return DevProjection(
        state = state,
        envelope = lastGood?.envelope,
        online = online,
        reload = reload,
        setAwaitingOutcome = { awaitingOutcome = it },
    )
}

private const val AWAITING_POLL_MS = 3_000L

object DevNetwork {
    /** Whether the phone has a validated internet-capable network right now. */
    fun isOnline(context: Context): Boolean {
        val manager = context.getSystemService(ConnectivityManager::class.java) ?: return true
        val network = manager.activeNetwork ?: return false
        val caps = manager.getNetworkCapabilities(network) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }
}
