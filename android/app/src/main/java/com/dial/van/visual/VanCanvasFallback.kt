package com.dial.van.visual

import android.content.Context
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import android.view.WindowManager
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
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
import com.dial.van.runtime.DeviceRuntimeReadings
import com.dial.van.runtime.VanResourceEnvelope
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
) {
    val context = LocalContext.current
    // Debug builds only: an imported test model stands in for VAN (see VanTestModel).
    val testModel = VanTestModel.renderer
    var testModelFailed by remember { mutableStateOf(false) }
    if (testModel != null && !testModelFailed && testModel.available(context)) {
        LaunchedEffect(Unit) { onSilhouette(null) }
        testModel.Render(state, presentation, modifier) { testModelFailed = true }
        return
    }
    var decision by remember(context) { mutableStateOf(resolveRenderer(context)) }

    LaunchedEffect(decision) { onDecision(decision) }

    when (decision.renderer) {
        VanRenderer.RIVE -> VanRiveAvatar(
            state = state,
            modifier = modifier,
            onSilhouette = onSilhouette,
            onLoadFailed = {
                decision = VanVisualRuntime.decide(
                    assetBytes = null,
                    riveRuntimeAvailable = false,
                    ownerArtAvailable = VanStateArt.artAvailable(context),
                    loadFailed = true,
                    candidateBAvailable = true,
                )
            },
        )

        VanRenderer.OWNER_ART -> VanOwnerArtAvatar(state = state, modifier = modifier)

        VanRenderer.CANDIDATE_B -> VanCandidateBAvatar(
            state = state,
            modifier = modifier,
            presentation = presentation,
            onSilhouette = onSilhouette,
        )

        VanRenderer.CANVAS -> {
            // The procedural character is drawn from the measured layout; so is its aura.
            LaunchedEffect(Unit) { onSilhouette(null) }
            VanCanvasAvatar(
                state = state,
                modifier = modifier,
                presentation = presentation,
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
    val reducedMotion = rememberReducedMotion()
    val phase = vanIdlePhase(state.durableState, reducedMotion)
    val motion = VanCharacterMotion.sample(state, phase, reducedMotion)
    val framing = VanFraming.forPresentation(presentation)
    val marks = VanScene.stateMarks(
        state,
        VanSceneFrame(presentation = presentation, phase = phase, reducedMotion = reducedMotion),
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

/** Owner-art fallback stays opaque but receives tiny state-aware micro-motion. */
@Composable
fun VanOwnerArtAvatar(state: VanVisualState, modifier: Modifier = Modifier) {
    val palette = VanStatusPalette.forState(state.durableState)
    val resId = VanStateArt.drawableFor(state.durableState) ?: return
    val description = vanContentDescription(state)
    val reducedMotion = rememberReducedMotion()
    val phase = vanIdlePhase(state.durableState, reducedMotion)
    val motion = VanCharacterMotion.sample(state, phase, reducedMotion)

    val filter = if (palette.desaturation > 0.01f) {
        ColorFilter.colorMatrix(ColorMatrix().apply { setToSaturation(1f - palette.desaturation) })
    } else {
        null
    }

    Image(
        painter = painterResource(id = resId),
        contentDescription = description,
        modifier = modifier
            .offset(x = motion.offsetXDp.dp, y = motion.offsetYDp.dp)
            .graphicsLayer {
                rotationZ = motion.rotationDeg
                scaleX = motion.scale
                scaleY = motion.scale
            },
        contentScale = ContentScale.Fit,
        alpha = palette.dim,
        colorFilter = filter,
    )
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
    budget: VanEffectBudget = VanEffectBudget.FULL,
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
    val activitySpec = rememberBlendedAura(state.durableState, budget).reactToVoiceAmplitude(state.mouthOpen)
    // Aura Rev 2 — a live trade drives the outer field unless authority, health or offline
    // truth outranks it (VanPresenceFrame decides; this only reads the result).
    val semanticSpec = rememberBlendedAura(
        state.resolvedSemanticState,
        budget,
        VanAuraSpecs.semanticSpecFor(state, budget),
    )
    val phase = vanIdlePhase(state.durableState, !budget.allowMotion, animate = animate)
    val body = characterFraction.coerceIn(0.40f, 1f)

    // Aura Rev 2 (CF-D-08) — where VAN is on screen (Rive alpha, B art alpha or layout), a
    // long second clock so the fire never visibly repeats, and a brief pulse on a closed trade.
    var silhouette by remember { mutableStateOf<VanSilhouette?>(null) }
    val slowPhase = rememberSlowAuraPhase(enabled = budget.allowMotion && animate)
    val pulse = rememberAuraPulse(state.auraPulseGeneration)
    val framing = VanFraming.forPresentation(presentation)

    Box(modifier = modifier, contentAlignment = Alignment.Center) {
        VanAuraLayer(
            spec = activitySpec,
            semanticSpec = semanticSpec,
            phase = phase,
            budget = budget,
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
        )
        // Faint wisps over the legs and forearms, and the rim light on VAN's edge.
        VanAuraLayer(
            spec = activitySpec,
            semanticSpec = semanticSpec,
            phase = phase,
            budget = budget,
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

/**
 * Aura Rev 2 — a second, long clock (23.7 s, unrelated to any state period) so the combined
 * motion never visibly loops. A constant duration, so it never restarts on a state change.
 */
@Composable
private fun rememberSlowAuraPhase(enabled: Boolean): Float {
    if (!enabled) return 0f
    val transition = rememberInfiniteTransition(label = "van-aura-slow")
    val value by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(durationMillis = 23_700, easing = LinearEasing)),
        label = "van-aura-slow-phase",
    )
    return value
}

/** One brief white expansion each time [generation] advances (a live position closed). */
@Composable
private fun rememberAuraPulse(generation: Int): Float {
    val pulse = remember { Animatable(0f) }
    var seen by remember { mutableStateOf(generation) }
    LaunchedEffect(generation) {
        if (generation == seen) return@LaunchedEffect
        seen = generation
        pulse.snapTo(1f)
        pulse.animateTo(0f, tween(durationMillis = 900, easing = LinearEasing))
    }
    return pulse.value
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
): VanAuraSpec {
    var transition by remember { mutableStateOf<VanAuraTransition?>(null) }
    var previousState by remember { mutableStateOf(state) }
    var spec by remember { mutableStateOf(target) }

    // Keyed on the target itself: a trading change retargets as smoothly as a state change.
    LaunchedEffect(target) {
        if (!spec.differsFrom(target)) {
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
    return spec
}

@Composable
fun rememberVanEffectBudget(): VanEffectBudget {
    val context = LocalContext.current
    val reducedMotion = rememberReducedMotion()
    return remember(context, reducedMotion) {
        val power = context.getSystemService(PowerManager::class.java)
        val thermal = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            runCatching { power?.currentThermalStatus ?: 0 }.getOrDefault(0)
        } else {
            0
        }
        val blurEnabled = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            runCatching {
                context.getSystemService(WindowManager::class.java)?.isCrossWindowBlurEnabled ?: false
            }.getOrDefault(false)
        } else {
            false
        }
        // P3-PERF-003 — resolved through the runtime envelope rather than beside it. The
        // ladder still decides; the envelope may only make its answer weaker. Before this,
        // a phone at four percent with power-save switched off rendered the full field,
        // because battery *level* was not an input to anything.
        VanResourceEnvelope.effectBudget(
            DeviceRuntimeReadings.read(context),
            VanEffectConditions(
                batterySaver = power?.isPowerSaveMode == true,
                thermalStatus = thermal,
                reducedMotion = reducedMotion,
                crossWindowBlurEnabled = blurEnabled,
            ),
        )
    }
}

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
        ownerArtAvailable = VanStateArt.artAvailable(context),
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

@Composable
fun rememberReducedMotion(): Boolean {
    val context = LocalContext.current
    return remember(context) {
        runCatching {
            Settings.Global.getFloat(
                context.contentResolver,
                Settings.Global.ANIMATOR_DURATION_SCALE,
                1f,
            ) == 0f
        }.getOrDefault(false)
    }
}

@Composable
fun VanCanvasAvatar(
    state: VanVisualState,
    modifier: Modifier = Modifier,
    presentation: VanPresentation = VanPresentation.COMPACT,
) {
    val reducedMotion = rememberReducedMotion()
    val phase = vanIdlePhase(state.durableState, reducedMotion)
    val frame = VanSceneFrame(
        presentation = presentation,
        phase = phase,
        blink = if (reducedMotion) 0f else blinkFor(phase),
        reducedMotion = reducedMotion,
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
    if (reducedMotion) return NEUTRAL_PHASE
    // Survives state changes on purpose: the clock is keyed on nothing, so a new state
    // gives it a new period and not a new clock.
    val clock = remember { VanAnimationClock() }
    var phase by remember { mutableStateOf(clock.phase) }
    val period = VanMotionPeriods.periodMillisFor(state)

    LaunchedEffect(animate, period) {
        if (!animate) return@LaunchedEffect
        var previous = 0L
        while (true) {
            withFrameNanos { frameNanos ->
                if (previous != 0L) sampler?.recordNanos(previous, frameNanos)
                previous = frameNanos
                phase = clock.advance(frameNanos, period)
            }
        }
    }
    return phase
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
