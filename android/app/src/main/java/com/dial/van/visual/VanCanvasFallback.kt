package com.dial.van.visual

import android.content.Context
import android.database.ContentObserver
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.ColorMatrix
import androidx.compose.ui.graphics.FilterQuality
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.imageResource
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import java.io.IOException
import kotlin.math.PI
import kotlin.math.min
import kotlin.math.sin

@Composable
fun VanAvatar(
    state: VanVisualState,
    modifier: Modifier = Modifier,
    presentation: VanPresentation = VanPresentation.COMPACT,
    onDecision: (VanRenderDecision) -> Unit = VanRendererStatusPublisher::publish,
    /** Aura Rev 2 — reports where VAN is on screen so the aura can wrap him. */
    onSilhouette: (VanSilhouette?) -> Unit = {},
    animate: Boolean = true,
    budget: VanEffectBudget = VanEffectBudget.FULL,
    reducedMotion: Boolean = rememberReducedMotion(),
    phase: Float? = null,
) {
    val motionEnabled = vanMotionEnabled(budget, animate = animate, reducedMotion = reducedMotion)
    val effectivePhase = phase ?: vanIdlePhase(state.durableState, reducedMotion, motionEnabled)
    val context = LocalContext.current
    var decision by remember(context) { mutableStateOf(resolveRenderer(context)) }

    LaunchedEffect(decision) { onDecision(decision) }

    when (decision.renderer) {
        VanRenderer.RIVE -> VanRiveAvatar(
            state = state,
            modifier = modifier,
            onSilhouette = onSilhouette,
            animate = motionEnabled,
            budget = budget,
            reducedMotion = reducedMotion,
            onLoadFailed = {
                decision = VanVisualRuntime.decide(
                    assetBytes = null,
                    riveRuntimeAvailable = false,
                    loadFailed = true,
                    candidateBAvailable = true,
                )
            },
        )

        VanRenderer.CANDIDATE_B -> VanCandidateBAvatar(
            state = state,
            modifier = modifier,
            presentation = presentation,
            onSilhouette = onSilhouette,
            motionEnabled = motionEnabled,
            reducedMotion = reducedMotion,
            phase = effectivePhase,
        )

        VanRenderer.CANVAS -> {
            // The procedural character is drawn from the measured layout; so is its aura.
            LaunchedEffect(Unit) { onSilhouette(null) }
            VanCanvasAvatar(
                state = state,
                modifier = modifier,
                presentation = presentation,
                motionEnabled = motionEnabled,
                reducedMotion = reducedMotion,
                phase = effectivePhase,
            )
        }
    }
}

/**
 * The owner's chosen interim VAN: real Candidate B art, framed per presentation exactly like
 * the Canvas character and the flame aura, with the same state-aware micro-motion the
 * character sampler gives a still. Offline and degraded desaturate him; he never fades.
 */
@Composable
fun VanCandidateBAvatar(
    state: VanVisualState,
    modifier: Modifier = Modifier,
    presentation: VanPresentation = VanPresentation.COMPACT,
    onSilhouette: (VanSilhouette?) -> Unit = {},
    motionEnabled: Boolean = true,
    reducedMotion: Boolean = rememberReducedMotion(),
    phase: Float? = null,
) {
    val image = ImageBitmap.imageResource(com.dial.van.R.drawable.van_candidate_b_front)
    // Aura Rev 2 — the art's own alpha is the silhouette, built once per framing.
    val unitAlpha = remember(image) { unitAlphaOf(image) }
    LaunchedEffect(unitAlpha, presentation) {
        onSilhouette(
            unitAlpha?.let {
                VanSilhouette.framedFromUnitAlpha(
                    VanSilhouette.SQUARE, VanSilhouette.SQUARE, it, VanFraming.forPresentation(presentation),
                )
            },
        )
    }
    val palette = VanStatusPalette.forState(state.durableState)
    val description = vanContentDescription(state)
    val enabled = vanMotionEnabled(VanEffectBudget.FULL, animate = motionEnabled, reducedMotion = reducedMotion)
    val effectivePhase = phase ?: vanIdlePhase(state.durableState, reducedMotion, enabled)
    val still = !enabled
    val motion = VanCharacterMotion.sample(state, effectivePhase, still)
    val framing = VanFraming.forPresentation(presentation)
    val marks = VanScene.stateMarks(
        state,
        VanSceneFrame(presentation = presentation, phase = effectivePhase, reducedMotion = still),
    )
    val filter = if (palette.desaturation > 0.01f) {
        ColorFilter.colorMatrix(ColorMatrix().apply { setToSaturation(1f - palette.desaturation) })
    } else {
        null
    }
    Canvas(
        modifier = modifier
            .semantics { contentDescription = description }
            .offset(x = motion.offsetXDp.dp, y = motion.offsetYDp.dp)
            .graphicsLayer {
                rotationZ = motion.rotationDeg
                scaleX = motion.scale
                scaleY = motion.scale
            },
    ) {
        val blit = VanInterimArt.blit(framing, image.width, size.width, size.height) ?: return@Canvas
        drawImage(
            image = image,
            srcOffset = IntOffset(blit.srcLeft, blit.srcTop),
            srcSize = IntSize(blit.srcWidth, blit.srcHeight),
            dstOffset = IntOffset(blit.dstLeft.toInt(), blit.dstTop.toInt()),
            dstSize = IntSize(blit.dstWidth.toInt(), blit.dstHeight.toInt()),
            alpha = palette.dim,
            colorFilter = filter,
            filterQuality = FilterQuality.High,
        )
        drawVanScene(marks)
    }
}

/**
 * The cut-out's alpha, downsampled once to the silhouette grid. Null if the pixels cannot be
 * read (a hardware-backed bitmap, say): the aura then falls back to the measured layout.
 */
private fun unitAlphaOf(image: ImageBitmap): ByteArray? = try {
    val n = VanSilhouette.SQUARE
    val source = image.asAndroidBitmap().let {
        if (it.config == android.graphics.Bitmap.Config.HARDWARE) it.copy(android.graphics.Bitmap.Config.ARGB_8888, false) else it
    }
    val small = android.graphics.Bitmap.createScaledBitmap(source, n, n, true)
    val pixels = IntArray(n * n)
    small.getPixels(pixels, 0, n, 0, 0, n, n)
    ByteArray(n * n) { (pixels[it] ushr 24).toByte() }
} catch (_: Throwable) {
    null
}

/**
 * Complete VAN embodiment. Character pose follows local activity; Zone B follows that same local
 * activity; Zone C independently follows [VanVisualState.resolvedSemanticState].
 */
@Composable
fun VanEmbodiment(
    state: VanVisualState,
    modifier: Modifier = Modifier,
    presentation: VanPresentation = VanPresentation.COMPACT,
    budget: VanEffectBudget = rememberVanEffectBudget(),
    onDecision: (VanRenderDecision) -> Unit = VanRendererStatusPublisher::publish,
    characterFraction: Float = 1f,
    /**
     * P1-PERF-002 — false stops the frame loop entirely. The overlay passes
     * `OverlayVisibilityPolicy.shouldAnimate(...)`, so VAN does not animate a field nobody
     * can see. Defaulted true so every in-app caller keeps the behaviour it had.
     */
    animate: Boolean = true,
) {
    // P1-AURA-002 — both fields blend over 120-420 ms rather than switching. Zone B follows
    // local activity and Zone C follows semantic truth, and they change independently, so
    // each carries its own transition; sharing one would make a health change drag the
    // activity field with it.
    // DNA §2 — reactive to voice RMS: a pure post-transform over the already-blended spec,
    // so a louder syllable brightens the field without retriggering P1-AURA-002's blend
    // machinery (`mouthOpen` is not one of that effect's keys, deliberately: it changes many
    // times a second during speech, and restarting a 120-420ms blend that often would be the
    // exact snap-on-change P1-AURA-002 exists to remove). Zero outside LISTENING/SPEAKING —
    // see `reactToVoiceAmplitude`'s doc — so this is a no-op for every other state.
    val reducedMotion = rememberReducedMotion()
    var cadenceMissed by remember { mutableStateOf(false) }
    val effectiveBudget = VanEffectPolicy.withCadencePressure(budget, cadenceMissed)
    val motionEnabled = vanMotionEnabled(effectiveBudget, animate = animate, reducedMotion = reducedMotion)
    // The same clock drives movement and cadence feedback. No extra measurement frame loop.
    val sharedMotion = rememberVanMotionFrame(
        state.durableState, motionEnabled, onCadenceChanged = { cadenceMissed = it },
    )
    val activitySpec = rememberBlendedAura(
        state.durableState,
        effectiveBudget,
        enabled = motionEnabled,
    ).reactToVoiceAmplitude(state.mouthOpen)
    // Aura Rev 2 — a live trade drives the outer field unless authority, health or offline
    // truth outranks it (VanPresenceFrame decides; this only reads the result).
    val semanticSpec = rememberBlendedAura(
        state.resolvedSemanticState,
        effectiveBudget,
        VanAuraSpecs.semanticSpecFor(state, effectiveBudget),
        enabled = motionEnabled,
    )
    val phase = sharedMotion.phase
    val body = characterFraction.coerceIn(0.40f, 1f)

    // Both aura phases use the body's active-time clock; hidden time advances neither.
    var silhouette by remember { mutableStateOf<VanSilhouette?>(null) }
    val slowPhase = sharedMotion.slowPhase
    val pulse = rememberAuraPulse(state.auraPulseGeneration, motionEnabled)
    val framing = VanFraming.forPresentation(presentation)

    Box(modifier = modifier, contentAlignment = Alignment.Center) {
        VanAuraLayer(
            spec = activitySpec,
            semanticSpec = semanticSpec,
            phase = phase,
            budget = effectiveBudget,
            characterScale = body,
            framing = framing,
            silhouette = silhouette,
            slowPhase = slowPhase,
            pulse = pulse,
            depth = VanAuraDepth.BACK,
            modifier = Modifier.matchParentSize(),
        )
        VanAvatar(
            state = state,
            modifier = Modifier.fillMaxSize(body),
            presentation = presentation,
            onDecision = onDecision,
            onSilhouette = { silhouette = it },
            animate = motionEnabled,
            budget = effectiveBudget,
            reducedMotion = reducedMotion,
            phase = phase,
        )
        // Faint wisps over the legs and forearms, and the rim light on VAN's edge.
        VanAuraLayer(
            spec = activitySpec,
            semanticSpec = semanticSpec,
            phase = phase,
            budget = effectiveBudget,
            characterScale = body,
            framing = framing,
            silhouette = silhouette,
            slowPhase = slowPhase,
            pulse = pulse,
            depth = VanAuraDepth.FRONT,
            modifier = Modifier.matchParentSize(),
        )
    }
}

/** One brief white expansion each time [generation] advances (a live position closed). */
@Composable
private fun rememberAuraPulse(generation: Int, enabled: Boolean = true): Float {
    val pulse = remember { Animatable(0f) }
    var seen by remember { mutableStateOf(generation) }
    var wasEnabled by remember { mutableStateOf(enabled) }
    LaunchedEffect(generation, enabled) {
        val shouldPulse = enabled && wasEnabled && generation != seen
        seen = generation
        wasEnabled = enabled
        pulse.snapTo(0f)
        if (!shouldPulse) return@LaunchedEffect
        pulse.snapTo(1f)
        pulse.animateTo(0f, tween(durationMillis = 900, easing = LinearEasing))
    }
    return if (enabled) pulse.value else 0f
}

/**
 * The aura for a state, blended in from whatever was on screen (P1-AURA-002).
 *
 * The transition is held in `remember`, keyed on nothing, so retargeting mid-blend continues
 * from where the blend had actually got to rather than from the previous target — which is
 * the case that matters, since LISTENING to THINKING to WORKING inside half a second is
 * ordinary, and restarting from the old target would put the snap back on the second change.
 */
@Composable
private fun rememberBlendedAura(
    state: VanDurableState,
    budget: VanEffectBudget,
    target: VanAuraSpec = VanAuraSpecs.forState(state, budget),
    enabled: Boolean = budget.allowMotion,
): VanAuraSpec {
    var transition by remember { mutableStateOf<VanAuraTransition?>(null) }
    var previousState by remember { mutableStateOf(state) }
    var spec by remember { mutableStateOf(target) }

    // Keyed on the target itself: a trading change retargets as smoothly as a state change.
    LaunchedEffect(target, enabled) {
        if (!enabled) {
            transition = null
            previousState = state
            spec = target
            return@LaunchedEffect
        }
        if (!spec.differsFrom(target)) {
            transition = null
            previousState = state
            spec = target
            return@LaunchedEffect
        }
        val started = withFrameNanos { it }
        transition = VanAuraTransition.retarget(
            existing = transition,
            current = spec,
            to = target,
            fromState = previousState,
            toState = state,
            nowNanos = started,
        )
        previousState = state
        while (true) {
            val now = withFrameNanos { it }
            val active = transition ?: break
            spec = active.specAt(now)
            if (active.isComplete(now)) {
                spec = target
                transition = null
                break
            }
        }
    }
    return if (enabled) spec else target
}

/** Retained public source/binary entry point; native subscription is shared in its own adapter. */
@Composable
fun rememberVanEffectBudget(): VanEffectBudget = rememberObservedVanEffectBudget()

private fun resolveRenderer(context: Context): VanRenderDecision {
    val bytes = try {
        context.assets.open(RiveBindingContract.ASSET_FILE).use { stream ->
            var total = 0L
            val buffer = ByteArray(8192)
            while (true) {
                val read = stream.read(buffer)
                if (read <= 0) break
                total += read
            }
            total
        }
    } catch (_: IOException) {
        null
    }
    return VanVisualRuntime.decide(
        assetBytes = bytes,
        riveRuntimeAvailable = riveRuntimeAvailable(),
        // Bundled with the app (res/drawable-nodpi/van_candidate_b_front.png).
        candidateBAvailable = true,
    )
}

private fun riveRuntimeAvailable(): Boolean = try {
    Class.forName("app.rive.runtime.kotlin.RiveAnimationView")
    true
} catch (_: Throwable) {
    false
}

private fun readReducedMotion(context: Context): Boolean = runCatching {
    Settings.Global.getFloat(
        context.contentResolver,
        Settings.Global.ANIMATOR_DURATION_SCALE,
        1f,
    ) == 0f
}.getOrDefault(true)

@Composable
fun rememberReducedMotion(): Boolean {
    val context = LocalContext.current
    var reducedMotion by remember(context) { mutableStateOf(readReducedMotion(context)) }
    DisposableEffect(context) {
        val resolver = context.contentResolver
        var disposed = false
        var registered = false
        val observer = object : ContentObserver(Handler(Looper.getMainLooper())) {
            override fun onChange(selfChange: Boolean) {
                if (!disposed) reducedMotion = readReducedMotion(context)
            }
        }
        try {
            resolver.registerContentObserver(
                Settings.Global.getUriFor(Settings.Global.ANIMATOR_DURATION_SCALE),
                false,
                observer,
            )
            registered = true
            reducedMotion = readReducedMotion(context)
        } catch (_: SecurityException) {
            reducedMotion = true
        }
        onDispose {
            // Queued main-thread notifications must not update a disposed composition.
            disposed = true
            if (registered) runCatching { resolver.unregisterContentObserver(observer) }
        }
    }
    return reducedMotion
}

@Composable
fun VanCanvasAvatar(
    state: VanVisualState,
    modifier: Modifier = Modifier,
    presentation: VanPresentation = VanPresentation.COMPACT,
    motionEnabled: Boolean = true,
    reducedMotion: Boolean = rememberReducedMotion(),
    phase: Float? = null,
) {
    val enabled = vanMotionEnabled(VanEffectBudget.FULL, animate = motionEnabled, reducedMotion = reducedMotion)
    val effectivePhase = phase ?: vanIdlePhase(state.durableState, reducedMotion, enabled)
    val frame = VanSceneFrame(
        presentation = presentation,
        phase = effectivePhase,
        blink = if (enabled) blinkFor(effectivePhase) else 0f,
        reducedMotion = !enabled,
    )
    val ops = VanScene.build(state, frame)
    val description = vanContentDescription(state)

    Canvas(modifier = modifier.semantics { contentDescription = description }) {
        drawVanScene(ops)
    }
}

/**
 * One monotonic clock, driven by `withFrameNanos`, never restarted (P1-AURA-002).
 *
 * This used to be a `rememberInfiniteTransition` whose `durationMillis` was chosen from the
 * state. Changing state changed the duration, which **restarts the tween from zero** — so
 * every aura change produced a one-frame snap at exactly the moment VAN was supposed to be
 * showing the owner a change. [VanAnimationClock] integrates `dt / period` instead, so a
 * period change alters how fast the phase advances and leaves where it *is* alone.
 *
 * The frame loop also feeds [VanFrameBudgetSampler], which is the producer
 * `VanEffectConditions.frameBudgetMissed` never had (P2-PERF-001), and it stops entirely
 * when [animate] is false rather than running with the screen off (P1-PERF-002).
 */
@Composable
private fun vanIdlePhase(
    state: VanDurableState,
    reducedMotion: Boolean,
    animate: Boolean = true,
    sampler: VanFrameBudgetSampler? = null,
): Float {
    return rememberVanMotionFrame(state, animate && !reducedMotion, sampler).phase
}

private data class VanMotionFrame(val phase: Float, val slowPhase: Float)

@Composable
private fun rememberVanMotionFrame(
    state: VanDurableState,
    enabled: Boolean,
    sampler: VanFrameBudgetSampler? = null,
    onCadenceChanged: ((Boolean) -> Unit)? = null,
): VanMotionFrame {
    val clock = remember { VanAnimationClock(initialPhase = NEUTRAL_PHASE) }
    var frame by remember { mutableStateOf(VanMotionFrame(clock.phase, 0f)) }
    val period by rememberUpdatedState(VanMotionPeriods.periodMillisFor(state))
    val currentSampler by rememberUpdatedState(sampler)
    val currentCadenceCallback by rememberUpdatedState(onCadenceChanged)
    val refreshRate = rememberVanDisplayRefreshRate()
    val cadence = remember { VanFrameCadenceFeedback() }

    // State/period changes retain phase; a display-rate change starts a new cadence window.
    LaunchedEffect(enabled, refreshRate) {
        clock.suspendTiming()
        cadence.configure(refreshRate, enabled)
        var reported = cadence.missed
        currentCadenceCallback?.invoke(reported)
        if (!enabled) return@LaunchedEffect
        var previous: Long? = null
        try {
            while (true) {
                withFrameNanos { frameNanos ->
                    previous?.let { currentSampler?.recordNanos(it, frameNanos) }
                    previous = frameNanos
                    val missed = cadence.record(frameNanos)
                    if (missed != reported) {
                        reported = missed
                        currentCadenceCallback?.invoke(missed)
                    }
                    val phase = clock.advance(frameNanos, period)
                    val slow = (clock.elapsedNanos % 23_700_000_000L).toFloat() / 23_700_000_000f
                    frame = VanMotionFrame(phase, slow)
                }
            }
        } finally {
            clock.suspendTiming()
            cadence.pause()
        }
    }
    return frame
}

private fun blinkFor(phase: Float): Float {
    val start = 0.93f
    if (phase < start) return 0f
    val t = ((phase - start) / (1f - start)).coerceIn(0f, 1f)
    return sin(t * PI.toFloat())
}

internal fun vanContentDescription(state: VanVisualState): String {
    val label = VanScene.statusLabel(state.durableState)
    return "Van assistant, $label"
}

fun DrawScope.drawVanScene(ops: List<VanDrawOp>) {
    val s = min(size.width, size.height)
    if (s <= 0f) return
    val dx = (size.width - s) / 2f
    val dy = (size.height - s) / 2f

    fun px(v: Float) = v * s
    fun x(v: Float) = dx + v * s
    fun y(v: Float) = dy + v * s

    ops.forEach { op ->
        val color = Color(op.color)
        val stroke = op.strokeWidth?.let { Stroke(width = px(it).coerceAtLeast(1f)) }
        when (op) {
            is VanDrawOp.Circle -> if (stroke == null) {
                drawCircle(color, radius = px(op.r), center = Offset(x(op.cx), y(op.cy)))
            } else {
                drawCircle(color, radius = px(op.r), center = Offset(x(op.cx), y(op.cy)), style = stroke)
            }

            is VanDrawOp.Oval -> {
                val topLeft = Offset(x(op.cx - op.rx), y(op.cy - op.ry))
                val boxSize = Size(px(op.rx * 2f), px(op.ry * 2f))
                if (stroke == null) drawOval(color, topLeft, boxSize) else drawOval(color, topLeft, boxSize, style = stroke)
            }

            is VanDrawOp.RoundRect -> {
                val topLeft = Offset(x(op.cx - op.halfW), y(op.cy - op.halfH))
                val boxSize = Size(px(op.halfW * 2f), px(op.halfH * 2f))
                val radius = CornerRadius(px(op.radius), px(op.radius))
                if (stroke == null) {
                    drawRoundRect(color, topLeft, boxSize, radius)
                } else {
                    drawRoundRect(color, topLeft, boxSize, radius, style = stroke)
                }
            }

            is VanDrawOp.Arc -> drawArc(
                color = color,
                startAngle = op.startDegrees,
                sweepAngle = op.sweepDegrees,
                useCenter = false,
                topLeft = Offset(x(op.cx - op.r), y(op.cy - op.r)),
                size = Size(px(op.r * 2f), px(op.r * 2f)),
                style = stroke ?: Stroke(width = 1f),
            )

            is VanDrawOp.PathOp -> {
                val path = Path()
                op.segments.forEach { seg ->
                    when (seg) {
                        is VanPathSeg.MoveTo -> path.moveTo(x(seg.x), y(seg.y))
                        is VanPathSeg.LineTo -> path.lineTo(x(seg.x), y(seg.y))
                        is VanPathSeg.QuadTo -> path.quadraticBezierTo(x(seg.cx), y(seg.cy), x(seg.x), y(seg.y))
                        VanPathSeg.Close -> path.close()
                    }
                }
                if (stroke == null) drawPath(path, color) else drawPath(path, color, style = stroke)
            }
        }
    }
}

private const val NEUTRAL_PHASE = 0.25f

@Preview(name = "Van compact — ready", widthDp = 96, heightDp = 96)
@Composable
private fun PreviewVanCompactReady() {
    VanCanvasAvatar(
        state = VanVisualState(durableState = VanDurableState.IDLE),
        modifier = Modifier.size(96.dp).background(Color(0xFF0B0F14)),
    )
}

@Preview(name = "Van compact — degraded", widthDp = 96, heightDp = 96)
@Composable
private fun PreviewVanCompactDegraded() {
    VanCanvasAvatar(
        state = VanVisualState(durableState = VanDurableState.DEGRADED, urgency = 0.3f),
        modifier = Modifier.size(96.dp).background(Color(0xFF0B0F14)),
    )
}

@Preview(name = "Van compact — offline", widthDp = 96, heightDp = 96)
@Composable
private fun PreviewVanCompactOffline() {
    VanCanvasAvatar(
        state = VanVisualState(durableState = VanDurableState.OFFLINE),
        modifier = Modifier.size(96.dp).background(Color(0xFF0B0F14)),
    )
}

@Preview(name = "Van command centre — speaking", widthDp = 220, heightDp = 220)
@Composable
private fun PreviewVanCommandCentre() {
    VanCanvasAvatar(
        state = VanVisualState(durableState = VanDurableState.SPEAKING, speaking = true, mouthOpen = 0.6f),
        presentation = VanPresentation.COMMAND_CENTRE,
        modifier = Modifier.size(220.dp).background(Color(0xFF0B0F14)),
    )
}
