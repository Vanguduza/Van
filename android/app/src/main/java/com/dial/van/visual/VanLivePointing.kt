package com.dial.van.visual

import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

/** Native main-thread ownership shell for measured VAN-owned UI targets. */
object VanLivePointing {
    private data class Probe(val lease: Long, val measure: () -> VanOwnedLayout?)
    private data class Active(val id: String, val lease: Long, val actionGeneration: Long, val deadlineMs: Long)
    private val main by lazy { Handler(Looper.getMainLooper()) }
    private val registry = VanUiTargetRegistry()
    private val probes = LinkedHashMap<String, Probe>()
    private var avatar: Probe? = null
    private var active: Active? = null
    var highlightedTarget by mutableStateOf<Pair<String, Long>?>(null); private set
    private var eventSequence = 0L

    fun registerTarget(id: String, lease: Long, provider: () -> VanOwnedLayout?) = onMain {
        val previous = probes[id]
        if (previous != null && previous.lease > lease) return@onMain
        probes[id] = Probe(lease, provider)
        while (probes.size > 64) {
            val first = probes.keys.first(); val old = probes.remove(first) ?: continue
            registry.removeTarget(first, old.lease)
            if (active?.id == first) stop()
        }
        changed(id)
    }

    fun unregisterTarget(id: String, lease: Long) = onMain {
        if (probes[id]?.lease == lease) probes.remove(id)
        registry.removeTarget(id, lease)
        if (active?.let { it.id == id && it.lease == lease } == true) stop()
    }

    fun registerAvatar(lease: Long, provider: () -> VanOwnedLayout?) = onMain {
        if (avatar?.let { it.lease > lease } == true) return@onMain
        avatar = Probe(lease, provider); changed(null)
    }

    fun unregisterAvatar(lease: Long) = onMain {
        if (avatar?.lease == lease) { avatar = null; registry.removeAvatar(lease); stop() }
    }

    /** Called only on real layout/visibility changes; no additional rendering loop. */
    fun changed(id: String?) = onMain {
        val current = active ?: return@onMain
        if (id != null && id != current.id) return@onMain
        val now = SystemClock.uptimeMillis()
        val resolved = refresh(current.id, now)
        if (now > current.deadlineMs || resolved == null || resolved.lease != current.lease) {
            stop(); return@onMain
        }
        VanLiveVisualState.retargetPointing(current.actionGeneration, resolved.directionX, resolved.directionY)
    }

    /** A guidance request has no approval, navigation, tap or command side effect. */
    fun pointAt(id: String) = onMain {
        val now = SystemClock.uptimeMillis()
        val target = refresh(id, now) ?: return@onMain
        val gesture = VanOwnedScreenContext.pointing(VanNativeScreenContext.current)
        VanLiveVisualState.action(
            action = VanFiniteAction.POINT_TARGET,
            evidence = VanCueEvidence.LOCAL_UI,
            target = target.cueTarget,
            source = "owned-ui-target:$id",
            eventId = "layout-point-${++eventSequence}",
            sourceRevision = target.revision,
            context = gesture,
            attentionOverride = target.directionX to target.directionY,
            onApplied = { token ->
                val duration = gesture.durationMs
                active = Active(id, target.lease, token, now + duration)
                highlightedTarget = id to target.lease
                main.postDelayed({ if (active?.actionGeneration == token) stop() }, duration + 1)
            },
        )
    }

    private fun refresh(id: String, now: Long): VanResolvedUiTarget? {
        val target = probes[id] ?: return null
        val body = avatar ?: return null
        val t = runCatching { target.measure() }.getOrNull() ?: return null
        val a = runCatching { body.measure() }.getOrNull() ?: return null
        registry.observeTarget(id, target.lease, t, now)
        registry.observeAvatar(body.lease, a, now)
        return registry.resolve(id, now)
    }

    /** A higher-priority gesture immediately withdraws an old visual highlight. */
    fun actionChanged(token: Long) {
        if (active?.let { it.actionGeneration != token } == true) stop()
    }

    private fun stop() {
        val previous = active; active = null
        highlightedTarget = null
        if (previous != null) VanLiveVisualState.clearPointing(previous.actionGeneration)
    }
    private fun onMain(block: () -> Unit) {
        if (Looper.myLooper() == Looper.getMainLooper()) block() else main.post(block)
    }
}
