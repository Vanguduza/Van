package com.dial.van.visual

import android.content.Context
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import android.view.WindowManager
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.ColorMatrix
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import java.io.IOException
import kotlin.math.PI
import kotlin.math.min
import kotlin.math.sin

/**
 * Entry point for every Van appearance.
 *
 * Resolves the renderer once per composition target and degrades to the interim Canvas
 * character whenever Rive cannot be trusted to paint a truthful Van.
 */
@Composable
fun VanAvatar(
    state: VanVisualState,
    modifier: Modifier = Modifier,
    presentation: VanPresentation = VanPresentation.COMPACT,
    onDecision: (VanRenderDecision) -> Unit = {},
) {
    val context = LocalContext.current
    var decision by remember(context) { mutableStateOf(resolveRenderer(context)) }

    LaunchedEffect(decision) { onDecision(decision) }

    when (decision.renderer) {
        VanRenderer.RIVE -> VanRiveAvatar(
            state = state,
            modifier = modifier,
            onLoadFailed = {
                decision = VanVisualRuntime.decide(
                    assetBytes = null,
                    riveRuntimeAvailable = false,
                    ownerArtAvailable = VanStateArt.artAvailable(context),
                    loadFailed = true,
                )
            },
        )

        VanRenderer.OWNER_ART -> VanOwnerArtAvatar(state = state, modifier = modifier)

        VanRenderer.CANVAS -> VanCanvasAvatar(
            state = state,
            modifier = modifier,
            presentation = presentation,
        )
    }
}

/**
 * Owner-supplied bitmap pose.
 *
 * Per §1 the character is the solid anchor, so the bitmap remains opaque and restrained. Unlike
 * the old static fallback, the pose receives tiny state-aware whole-character motion so VAN never
 * freezes while the living field moves around him. The motion is intentionally much smaller than
 * the aura motion; it must read as breathing/attention, not as a floating sticker effect.
 */
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
 * Van in his interaction shell, composed in the order fixed by §10:
 * aura bloom → filaments → character → orb, with the glass supplied by the caller underneath.
 */
@Composable
fun VanEmbodiment(
    state: VanVisualState,
    modifier: Modifier = Modifier,
    presentation: VanPresentation = VanPresentation.COMPACT,
    budget: VanEffectBudget = VanEffectBudget.FULL,
    onDecision: (VanRenderDecision) -> Unit = {},
    /** Body size relative to the aura canvas. Rest uses hit/avatar so Zone C has air. */
    characterFraction: Float = 1f,
) {
    val spec = VanAuraSpecs.forState(state.durableState, budget)
    val phase = vanIdlePhase(state.durableState, !budget.allowMotion)
    val body = characterFraction.coerceIn(0.40f, 1f)

    Box(modifier = modifier, contentAlignment = Alignment.Center) {
        // 5 & 6. Aura bloom and electrical filaments, behind Van and in front of the glass.
        VanAuraLayer(
            spec = spec,
            phase = phase,
            budget = budget,
            characterScale = body,
            modifier = Modifier.matchParentSize(),
        )
        // 7 & 8. Van and his orb — the art poses already carry the orb.
        VanAvatar(
            state = state,
            modifier = Modifier.fillMaxSize(body),
            presentation = presentation,
            onDecision = onDecision,
        )
    }
}

/** Resolves §11's effect budget from live device signals. */
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
        VanEffectPolicy.resolve(
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
    )
}

private fun riveRuntimeAvailable(): Boolean = try {
    Class.forName("app.rive.runtime.kotlin.RiveAnimationView")
    true
} catch (_: Throwable) {
    false
}

/**
 * True when the owner has turned system animations off. Van then holds a still, readable
 * pose instead of breathing, spinning or blinking.
 */
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

/**
 * The interim character. Every element traces to the locked identity, and the status layer
 * stays inside the acceptance matrix bounds: bounded motion, restrained glow, and truthful
 * muting when offline or degraded.
 */
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

/** Idle clock. Alert states tick faster but never leave the bounded-motion range. */
@Composable
private fun vanIdlePhase(state: VanDurableState, reducedMotion: Boolean): Float {
    if (reducedMotion) return NEUTRAL_PHASE
    val durationMs = when (state) {
        VanDurableState.LISTENING,
        VanDurableState.WORKING,
        VanDurableState.SEARCHING,
        VanDurableState.CONNECTING,
        -> 2000
        VanDurableState.URGENT,
        VanDurableState.WARNING,
        VanDurableState.ERROR,
        VanDurableState.WAITING_FOR_OWNER,
        -> 2800
        VanDurableState.SLEEPING,
        VanDurableState.OFFLINE,
        -> 6000
        else -> 4200
    }
    val transition = rememberInfiniteTransition(label = "van-idle")
    val value by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = durationMs, easing = LinearEasing),
            repeatMode = RepeatMode.Restart,
        ),
        label = "van-phase",
    )
    return value
}

/** One unhurried blink at the end of each idle cycle. */
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

/** Paints a [VanScene] program, fitted and centred so proportions never stretch. */
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
