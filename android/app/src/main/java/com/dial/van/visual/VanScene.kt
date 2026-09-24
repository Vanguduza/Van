package com.dial.van.visual

import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/** How much of Van is composed for the surface he is appearing on. */
enum class VanPresentation {
    /** Floating overlay bubble — head, visor and orb must read at ~72dp. */
    COMPACT,

    /** Mid-size docked card with quick actions. */
    EXPANDED,

    /** Full Command Centre composition including arms and hands. */
    COMMAND_CENTRE,
}

/**
 * Animation inputs are passed in rather than sampled inside the builder so the scene stays
 * a pure function: the same frame always produces the same ops, which is what lets the JVM
 * preview renderer and the unit tests reason about it.
 */
data class VanSceneFrame(
    val presentation: VanPresentation = VanPresentation.COMPACT,
    /** Looping 0f..1f idle phase. */
    val phase: Float = 0f,
    /** 0f open, 1f fully closed. */
    val blink: Float = 0f,
    val reducedMotion: Boolean = false,
)

private data class VanRig(
    val headCx: Float,
    val headCy: Float,
    val headRx: Float,
    val headRy: Float,
    val torsoTop: Float,
    val torsoHalfW: Float,
    val orbCx: Float,
    val orbCy: Float,
    val orbR: Float,
    val ringR: Float,
    val withLimbs: Boolean,
)

/**
 * Builds the canonical Van bust as renderer-independent ops.
 *
 * This is the interim character: it is deliberately a *character*, not a status widget, so
 * the embodiment survives until the authored `.riv` lands. The identity lock in
 * `visual-authority/rive_contract.json` is honoured element for element — silver swept hair,
 * cyan transparent visor, medium-brown skin, blue eyes, black/white technical jacket over a
 * charcoal underlayer, DIAL cyan accents, and the cyan holographic orb companion.
 */
object VanScene {

    const val SKIN = 0xFFB8853CL
    const val SKIN_SHADOW = 0xFF8A5E35L
    const val HAIR = 0xFFE9EAF0L
    const val HAIR_SHADOW = 0xFFC2C7D3L
    const val EYE_IRIS = 0xFF1E88E5L
    const val EYE_IRIS_DEEP = 0xFF0D47A1L
    const val EYE_SCLERA = 0xFFF2F6FAL
    const val EYE_PUPIL = 0xFF10233AL
    const val VISOR = 0xFF00E5FFL
    const val JACKET = 0xFF15181CL
    const val JACKET_PANEL = 0xFFEDEFF3L
    const val UNDERLAYER = 0xFF2B3138L
    const val MOUTH = 0xFF4A2A1AL
    const val GLOVE = 0xFF111820L
    const val ORB_BODY = 0xFF0C2436L

    fun build(state: VanVisualState, frame: VanSceneFrame): List<VanDrawOp> {
        val palette = VanStatusPalette.forState(state.durableState)
        val rig = rigFor(frame.presentation)
        val motion = if (frame.reducedMotion) 0f else 1f
        val tau = (2f * PI).toFloat()

        val bodyBob = sin(frame.phase * tau) * 0.008f * motion
        val headBob = sin(frame.phase * tau + 0.6f) * 0.005f * motion

        val character = buildList {
            addAll(torso(rig, palette))
            if (rig.withLimbs) addAll(limbs(rig, palette, state))
            addAll(neck(rig))
        }.translated(0f, bodyBob + actionHeadDrop(state))

        val head = buildList {
            addAll(headShape(rig))
            addAll(eyes(rig, state, frame))
            addAll(brows(rig, palette, state))
            addAll(visor(rig, palette))
            addAll(mouth(rig, palette, state))
            addAll(hair(rig))
        }.translated(0f, bodyBob + headBob)

        val orbDrift = sin(frame.phase * tau + 1.9f) * 0.018f * motion
        val orb = orb(rig, palette, state, frame)
            .translated(state.attentionX * rig.orbR * 0.35f, orbDrift + state.attentionY * rig.orbR * 0.25f)

        val muted = (character + head).muted(palette.desaturation, palette.dim)

        return muted +
            statusMarks(rig, palette, state, frame) +
            hologramGlyph(rig, palette, state) +
            orb
    }

    /** Exposed so overlay chrome and previews can label state with the same words. */
    fun statusLabel(state: VanDurableState): String = VanStatusPalette.forState(state).label

    private fun rigFor(presentation: VanPresentation): VanRig = when (presentation) {
        VanPresentation.COMPACT -> VanRig(
            headCx = 0.470f,
            headCy = 0.445f,
            headRx = 0.228f,
            headRy = 0.250f,
            torsoTop = 0.735f,
            torsoHalfW = 0.300f,
            orbCx = 0.840f,
            orbCy = 0.192f,
            orbR = 0.078f,
            ringR = 0.452f,
            withLimbs = true,
        )
        VanPresentation.EXPANDED -> VanRig(
            headCx = 0.480f,
            headCy = 0.400f,
            headRx = 0.198f,
            headRy = 0.218f,
            torsoTop = 0.652f,
            torsoHalfW = 0.298f,
            orbCx = 0.855f,
            orbCy = 0.168f,
            orbR = 0.070f,
            ringR = 0.462f,
            withLimbs = true,
        )
        VanPresentation.COMMAND_CENTRE -> VanRig(
            headCx = 0.492f,
            headCy = 0.330f,
            headRx = 0.152f,
            headRy = 0.168f,
            torsoTop = 0.530f,
            torsoHalfW = 0.272f,
            orbCx = 0.812f,
            orbCy = 0.152f,
            orbR = 0.058f,
            ringR = 0.474f,
            withLimbs = true,
        )
    }

    private fun actionHeadDrop(state: VanVisualState): Float = when (VanFiniteAction.fromCode(state.actionCode)) {
        VanFiniteAction.ACK_NOD -> 0.028f
        VanFiniteAction.SHRUG -> 0.012f
        else -> 0f
    }

    private fun torso(rig: VanRig, palette: VanStatusPalette): List<VanDrawOp> {
        val cx = rig.headCx
        val top = rig.torsoTop
        val hw = rig.torsoHalfW
        val bottom = 1.02f
        val collarY = top - 0.012f

        val jacket = vanPath {
            moveTo(cx - hw, bottom)
            lineTo(cx - hw * 0.90f, top + 0.055f)
            quadTo(cx - hw * 0.78f, collarY, cx - hw * 0.34f, collarY)
            lineTo(cx + hw * 0.34f, collarY)
            quadTo(cx + hw * 0.78f, collarY, cx + hw * 0.90f, top + 0.055f)
            lineTo(cx + hw, bottom)
            close()
        }

        val underlayer = vanPath {
            moveTo(cx - hw * 0.30f, collarY)
            quadTo(cx, top + 0.075f, cx + hw * 0.30f, collarY)
            lineTo(cx + hw * 0.36f, bottom)
            lineTo(cx - hw * 0.36f, bottom)
            close()
        }

        val leftPanel = vanPath {
            moveTo(cx - hw * 0.34f, collarY)
            quadTo(cx - hw * 0.30f, top + 0.085f, cx - hw * 0.16f, bottom)
            lineTo(cx - hw * 0.46f, bottom)
            quadTo(cx - hw * 0.62f, top + 0.070f, cx - hw * 0.68f, top + 0.014f)
            close()
        }

        val rightPanel = vanPath {
            moveTo(cx + hw * 0.34f, collarY)
            quadTo(cx + hw * 0.30f, top + 0.085f, cx + hw * 0.16f, bottom)
            lineTo(cx + hw * 0.46f, bottom)
            quadTo(cx + hw * 0.62f, top + 0.070f, cx + hw * 0.68f, top + 0.014f)
            close()
        }

        val collarAccent = vanPath {
            moveTo(cx - hw * 0.66f, top + 0.020f)
            quadTo(cx - hw * 0.34f, collarY - 0.004f, cx, top + 0.070f)
            quadTo(cx + hw * 0.34f, collarY - 0.004f, cx + hw * 0.66f, top + 0.020f)
        }

        return listOf(
            VanDrawOp.PathOp(jacket, VanColors.of(JACKET)),
            VanDrawOp.PathOp(underlayer, VanColors.of(UNDERLAYER)),
            VanDrawOp.PathOp(leftPanel, VanColors.of(JACKET_PANEL, 0.92f)),
            VanDrawOp.PathOp(rightPanel, VanColors.of(JACKET_PANEL, 0.92f)),
            VanDrawOp.PathOp(collarAccent, VanColors.scaleAlpha(palette.accent, 0.85f), strokeWidth = 0.011f),
            // DIAL "D" emblem, centre chest on the dark underlayer.
            VanDrawOp.RoundRect(
                cx = cx - 0.013f,
                cy = top + 0.132f,
                halfW = 0.0045f,
                halfH = 0.022f,
                radius = 0.0045f,
                color = VanColors.scaleAlpha(palette.accent, 0.95f),
            ),
            VanDrawOp.Arc(
                cx = cx - 0.013f,
                cy = top + 0.132f,
                r = 0.022f,
                startDegrees = -90f,
                sweepDegrees = 180f,
                color = VanColors.scaleAlpha(palette.accent, 0.95f),
                strokeWidth = 0.009f,
            ),
        )
    }

    private fun limbs(rig: VanRig, palette: VanStatusPalette, state: VanVisualState): List<VanDrawOp> {
        val cx = rig.headCx
        val hw = rig.torsoHalfW
        val shoulderY = rig.torsoTop + 0.075f
        val action = VanFiniteAction.fromCode(state.actionCode)
        val presenting = state.durableState == VanDurableState.SPEAKING ||
            state.durableState == VanDurableState.DELEGATING ||
            action == VanFiniteAction.PRESENT_CARD

        var leftHandX = cx - hw * 1.12f
        var leftHandY = 0.885f
        var rightHandX = cx + hw * 1.14f
        var rightHandY = 0.868f
        if (presenting) rightHandY -= 0.085f

        when (action) {
            VanFiniteAction.HELLO_WAVE -> {
                rightHandX = cx + hw * 0.92f
                rightHandY = rig.headCy - rig.headRy * 0.15f
            }
            VanFiniteAction.ACK_NOD -> rightHandY -= 0.02f
            VanFiniteAction.POINT_LEFT -> {
                leftHandX = cx - hw * 1.38f
                leftHandY = rig.headCy + rig.headRy * 0.10f
            }
            VanFiniteAction.POINT_RIGHT -> {
                rightHandX = cx + hw * 1.42f
                rightHandY = rig.headCy + rig.headRy * 0.08f
            }
            VanFiniteAction.POINT_UP -> {
                rightHandX = cx + hw * 0.70f
                rightHandY = rig.headCy - rig.headRy * 0.55f
            }
            VanFiniteAction.POINT_DOWN -> {
                rightHandX = cx + hw * 0.70f
                rightHandY = 0.97f
            }
            VanFiniteAction.POINT_TARGET -> {
                rightHandX = cx + hw * 1.30f
                rightHandY = rig.headCy
            }
            VanFiniteAction.CELEBRATE -> {
                leftHandX = cx - hw * 0.85f
                leftHandY = rig.headCy - rig.headRy * 0.20f
                rightHandX = cx + hw * 0.85f
                rightHandY = rig.headCy - rig.headRy * 0.28f
            }
            VanFiniteAction.CAUTION -> {
                rightHandX = cx + hw * 0.55f
                rightHandY = rig.headCy + rig.headRy * 0.05f
            }
            VanFiniteAction.CONFIRM -> {
                rightHandX = cx + hw * 0.62f
                rightHandY = rig.torsoTop + 0.18f
            }
            VanFiniteAction.SHRUG -> {
                leftHandY = 0.72f
                rightHandY = 0.72f
                leftHandX = cx - hw * 1.28f
                rightHandX = cx + hw * 1.28f
            }
            VanFiniteAction.OPEN_PANEL -> {
                leftHandX = cx - hw * 1.22f
                rightHandX = cx + hw * 1.22f
                leftHandY = 0.70f
                rightHandY = 0.70f
            }
            VanFiniteAction.CLOSE_PANEL -> {
                leftHandX = cx - hw * 0.55f
                rightHandX = cx + hw * 0.55f
                leftHandY = 0.78f
                rightHandY = 0.78f
            }
            VanFiniteAction.PRESENT_CARD -> Unit
            null -> Unit
        }

        val sleeve = 0.062f
        val leftSleeve = vanPath {
            moveTo(cx - hw * 0.80f, shoulderY)
            quadTo(cx - hw * 1.24f, shoulderY + 0.150f, leftHandX, leftHandY - 0.020f)
        }
        val rightSleeve = vanPath {
            moveTo(cx + hw * 0.80f, shoulderY)
            quadTo(cx + hw * 1.28f, shoulderY + 0.130f, rightHandX, rightHandY - 0.020f)
        }

        val ops = mutableListOf(
            VanDrawOp.PathOp(leftSleeve, VanColors.of(JACKET), strokeWidth = sleeve),
            VanDrawOp.PathOp(rightSleeve, VanColors.of(JACKET), strokeWidth = sleeve),
            VanDrawOp.Oval(leftHandX, leftHandY, 0.030f, 0.026f, VanColors.of(GLOVE)),
            VanDrawOp.Oval(rightHandX, rightHandY, 0.030f, 0.026f, VanColors.of(GLOVE)),
            VanDrawOp.Circle(leftHandX, leftHandY - 0.026f, 0.026f, VanColors.scaleAlpha(palette.accent, 0.8f), 0.008f),
            VanDrawOp.Circle(rightHandX, rightHandY - 0.026f, 0.026f, VanColors.scaleAlpha(palette.accent, 0.8f), 0.008f),
        )

        if (action == VanFiniteAction.PRESENT_CARD) {
            ops += VanDrawOp.RoundRect(
                cx = rightHandX + 0.010f,
                cy = rightHandY - 0.105f,
                halfW = 0.070f,
                halfH = 0.055f,
                radius = 0.014f,
                color = VanColors.scaleAlpha(palette.accent, 0.18f),
            )
            ops += VanDrawOp.RoundRect(
                cx = rightHandX + 0.010f,
                cy = rightHandY - 0.105f,
                halfW = 0.070f,
                halfH = 0.055f,
                radius = 0.014f,
                color = VanColors.scaleAlpha(palette.accent, 0.75f),
                strokeWidth = 0.006f,
            )
        }
        if (action == VanFiniteAction.POINT_LEFT || action == VanFiniteAction.POINT_RIGHT ||
            action == VanFiniteAction.POINT_UP || action == VanFiniteAction.POINT_DOWN ||
            action == VanFiniteAction.POINT_TARGET
        ) {
            val fromLeft = action == VanFiniteAction.POINT_LEFT
            val originX = if (fromLeft) leftHandX else rightHandX
            val originY = if (fromLeft) leftHandY else rightHandY
            val tipX = originX + if (fromLeft) -0.08f else 0.06f
            val tipY = when (action) {
                VanFiniteAction.POINT_UP -> originY - 0.08f
                VanFiniteAction.POINT_DOWN -> originY + 0.08f
                else -> originY
            }
            ops += VanDrawOp.PathOp(
                vanPath {
                    moveTo(originX, originY)
                    lineTo(tipX, tipY)
                },
                VanColors.of(SKIN),
                strokeWidth = 0.016f,
            )
        }
        return ops
    }

    private fun neck(rig: VanRig): List<VanDrawOp> = listOf(
        VanDrawOp.RoundRect(
            cx = rig.headCx,
            cy = rig.headCy + rig.headRy * 0.82f,
            halfW = rig.headRx * 0.34f,
            halfH = rig.headRy * 0.30f,
            radius = rig.headRx * 0.14f,
            color = VanColors.of(SKIN_SHADOW),
        ),
    )

    private fun headShape(rig: VanRig): List<VanDrawOp> {
        val cx = rig.headCx
        val cy = rig.headCy
        val rx = rig.headRx
        val ry = rig.headRy
        val jaw = vanPath {
            moveTo(cx - rx * 0.98f, cy + ry * 0.10f)
            quadTo(cx - rx * 0.88f, cy + ry * 0.92f, cx, cy + ry * 1.02f)
            quadTo(cx + rx * 0.88f, cy + ry * 0.92f, cx + rx * 0.98f, cy + ry * 0.10f)
            close()
        }
        return listOf(
            // Ears
            VanDrawOp.Oval(cx - rx * 0.98f, cy + ry * 0.10f, rx * 0.14f, ry * 0.20f, VanColors.of(SKIN_SHADOW)),
            VanDrawOp.Oval(cx + rx * 0.98f, cy + ry * 0.10f, rx * 0.14f, ry * 0.20f, VanColors.of(SKIN_SHADOW)),
            VanDrawOp.Oval(cx, cy, rx, ry, VanColors.of(SKIN)),
            VanDrawOp.PathOp(jaw, VanColors.of(SKIN)),
        )
    }

    private fun eyes(rig: VanRig, state: VanVisualState, frame: VanSceneFrame): List<VanDrawOp> {
        val cx = rig.headCx
        val cy = rig.headCy
        val rx = rig.headRx
        val ry = rig.headRy
        val eyeY = cy - ry * 0.06f
        val dx = rx * 0.40f
        val scleraRx = rx * 0.235f
        val open = (1f - frame.blink.coerceIn(0f, 1f))
        val scleraRy = ry * 0.175f * open.coerceAtLeast(0.04f)
        val irisR = rx * 0.150f
        val gazeX = state.attentionX.coerceIn(-1f, 1f) * rx * 0.070f
        val gazeY = state.attentionY.coerceIn(-1f, 1f) * ry * 0.045f

        val ops = mutableListOf<VanDrawOp>()
        listOf(-1f, 1f).forEach { side ->
            val ex = cx + side * dx
            ops += VanDrawOp.Oval(ex, eyeY, scleraRx, scleraRy, VanColors.of(EYE_SCLERA))
            if (open > 0.2f) {
                ops += VanDrawOp.Circle(ex + gazeX, eyeY + gazeY, irisR * open, VanColors.of(EYE_IRIS))
                ops += VanDrawOp.Circle(ex + gazeX, eyeY + gazeY, irisR * 0.92f * open, VanColors.of(EYE_IRIS_DEEP, 0.45f))
                ops += VanDrawOp.Circle(ex + gazeX, eyeY + gazeY, irisR * 0.44f * open, VanColors.of(EYE_PUPIL))
                ops += VanDrawOp.Circle(
                    ex + gazeX - irisR * 0.38f,
                    eyeY + gazeY - irisR * 0.40f,
                    irisR * 0.26f * open,
                    VanColors.of(0xFFFFFFFFL, 0.88f),
                )
            }
            // Upper lid rides down over the eye during a blink.
            if (frame.blink > 0.02f) {
                ops += VanDrawOp.RoundRect(
                    cx = ex,
                    cy = eyeY - scleraRy - ry * 0.175f * (1f - frame.blink) * 0.5f,
                    halfW = scleraRx * 1.18f,
                    halfH = ry * 0.175f * frame.blink,
                    radius = ry * 0.05f,
                    color = VanColors.of(SKIN),
                )
            }
        }
        return ops
    }

    private fun brows(rig: VanRig, palette: VanStatusPalette, state: VanVisualState): List<VanDrawOp> {
        val cx = rig.headCx
        val cy = rig.headCy
        val rx = rig.headRx
        val ry = rig.headRy
        val browY = cy - ry * 0.42f
        // Concern pulls inner brow ends down; alertness lifts the outer ends.
        val concern = when (palette.mood) {
            VanMood.CONCERNED -> 1f
            VanMood.ALERT -> 0.35f
            else -> 0f
        } * (0.4f + 0.6f * state.urgency.coerceIn(0f, 1f)).coerceAtLeast(0.4f)
        val lift = if (palette.mood == VanMood.ALERT) ry * 0.035f else 0f

        return listOf(-1f, 1f).map { side ->
            val inner = cx + side * rx * 0.20f
            val outer = cx + side * rx * 0.66f
            VanDrawOp.PathOp(
                vanPath {
                    moveTo(inner, browY + ry * 0.10f * concern)
                    quadTo(
                        cx + side * rx * 0.44f,
                        browY - ry * 0.10f - lift,
                        outer,
                        browY - ry * 0.02f - lift * 0.6f,
                    )
                },
                VanColors.of(HAIR_SHADOW, 0.95f),
                strokeWidth = rx * 0.055f,
            )
        }
    }

    private fun visor(rig: VanRig, palette: VanStatusPalette): List<VanDrawOp> {
        val cx = rig.headCx
        val cy = rig.headCy
        val rx = rig.headRx
        val ry = rig.headRy
        val visorCy = cy - ry * 0.06f
        val halfW = rx * 0.98f
        val halfH = ry * 0.255f
        val specular = vanPath {
            moveTo(cx - halfW * 0.80f, visorCy + halfH * 0.55f)
            lineTo(cx - halfW * 0.30f, visorCy - halfH * 0.80f)
            lineTo(cx - halfW * 0.08f, visorCy - halfH * 0.80f)
            lineTo(cx - halfW * 0.58f, visorCy + halfH * 0.55f)
            close()
        }
        return listOf(
            VanDrawOp.RoundRect(
                cx = cx,
                cy = visorCy,
                halfW = halfW,
                halfH = halfH,
                radius = halfH * 0.85f,
                color = VanColors.of(VISOR, 0.30f),
            ),
            VanDrawOp.PathOp(specular, VanColors.of(0xFFFFFFFFL, 0.16f)),
            VanDrawOp.RoundRect(
                cx = cx,
                cy = visorCy,
                halfW = halfW,
                halfH = halfH,
                radius = halfH * 0.85f,
                color = VanColors.of(VISOR, 0.90f),
                strokeWidth = rx * 0.045f,
            ),
            // Temple mount tying the visor into the DIAL accent language.
            VanDrawOp.RoundRect(
                cx = cx + halfW * 0.99f,
                cy = visorCy,
                halfW = rx * 0.055f,
                halfH = halfH * 0.62f,
                radius = rx * 0.03f,
                color = VanColors.scaleAlpha(palette.accent, 0.9f),
            ),
        )
    }

    private fun mouth(rig: VanRig, palette: VanStatusPalette, state: VanVisualState): List<VanDrawOp> {
        val cx = rig.headCx
        val cy = rig.headCy
        val rx = rig.headRx
        val ry = rig.headRy
        val mouthY = cy + ry * 0.55f
        val openness = state.mouthOpen.coerceIn(0f, 1f)
        val speaking = state.speaking || openness > 0.05f

        if (speaking) {
            val h = ry * (0.045f + 0.115f * openness)
            val w = rx * (0.24f + 0.10f * openness)
            return listOf(
                VanDrawOp.Oval(cx, mouthY, w, h, VanColors.of(MOUTH)),
                VanDrawOp.Oval(cx, mouthY + h * 0.42f, w * 0.62f, h * 0.42f, VanColors.of(0xFFD98C7AL, 0.75f)),
            )
        }

        val curve = when (palette.mood) {
            VanMood.PLEASED -> ry * 0.16f
            VanMood.CALM -> ry * 0.11f
            VanMood.ALERT -> ry * 0.05f
            VanMood.MUTED -> 0f
            VanMood.CONCERNED -> -ry * 0.07f
        }
        return listOf(
            VanDrawOp.PathOp(
                vanPath {
                    moveTo(cx - rx * 0.28f, mouthY - curve * 0.30f)
                    quadTo(cx, mouthY + curve, cx + rx * 0.28f, mouthY - curve * 0.30f)
                },
                VanColors.of(MOUTH, 0.85f),
                strokeWidth = rx * 0.055f,
            ),
        )
    }

    /**
     * Silver swept hair as *defined locks*, not a smooth cap.
     *
     * The outer silhouette is walked left temple → crown → right temple through alternating
     * spike tips and valleys, then closed back along the hairline through three fringe locks
     * that hang over the brow. Straight segments are deliberate: rounded curves read as a
     * swim cap at overlay size, which is the exact drift the owner design sheet rejects.
     */
    private fun hair(rig: VanRig): List<VanDrawOp> {
        val cx = rig.headCx
        val cy = rig.headCy
        val rx = rig.headRx
        val ry = rig.headRy
        fun hx(u: Float) = cx + rx * u
        fun hy(v: Float) = cy + ry * v

        val mass = vanPath {
            moveTo(hx(-1.04f), hy(0.06f))
            // Spikes sweep up and back, peaking just off-centre.
            lineTo(hx(-1.34f), hy(-0.46f))
            lineTo(hx(-1.00f), hy(-0.58f))
            lineTo(hx(-1.14f), hy(-1.00f))
            lineTo(hx(-0.76f), hy(-0.90f))
            lineTo(hx(-0.60f), hy(-1.40f))
            lineTo(hx(-0.28f), hy(-1.08f))
            lineTo(hx(-0.04f), hy(-1.54f))
            lineTo(hx(0.30f), hy(-1.10f))
            lineTo(hx(0.54f), hy(-1.44f))
            lineTo(hx(0.78f), hy(-0.98f))
            lineTo(hx(1.14f), hy(-1.12f))
            lineTo(hx(1.18f), hy(-0.66f))
            lineTo(hx(1.42f), hy(-0.38f))
            lineTo(hx(1.06f), hy(0.04f))
            // Hairline home, dipping into three fringe locks over the brow.
            quadTo(hx(1.02f), hy(-0.44f), hx(0.74f), hy(-0.60f))
            lineTo(hx(0.48f), hy(-0.30f))
            lineTo(hx(0.20f), hy(-0.64f))
            lineTo(hx(-0.06f), hy(-0.34f))
            lineTo(hx(-0.34f), hy(-0.66f))
            lineTo(hx(-0.58f), hy(-0.38f))
            quadTo(hx(-0.88f), hy(-0.58f), hx(-1.04f), hy(0.06f))
            close()
        }

        // Strand shading runs along the sweep direction so the locks separate at small sizes.
        val strandLow = vanPath {
            moveTo(hx(-0.92f), hy(-0.46f))
            quadTo(hx(-0.10f), hy(-0.96f), hx(0.92f), hy(-0.74f))
        }
        val strandMid = vanPath {
            moveTo(hx(-0.78f), hy(-0.74f))
            quadTo(hx(-0.02f), hy(-1.12f), hx(0.80f), hy(-0.96f))
        }
        val highlight = vanPath {
            moveTo(hx(-0.44f), hy(-0.98f))
            quadTo(hx(0.14f), hy(-1.22f), hx(0.66f), hy(-1.06f))
        }

        return listOf(
            VanDrawOp.PathOp(mass, VanColors.of(HAIR)),
            VanDrawOp.PathOp(strandLow, VanColors.of(HAIR_SHADOW, 0.85f), strokeWidth = rx * 0.070f),
            VanDrawOp.PathOp(strandMid, VanColors.of(HAIR_SHADOW, 0.55f), strokeWidth = rx * 0.055f),
            VanDrawOp.PathOp(highlight, VanColors.of(0xFFFFFFFFL, 0.80f), strokeWidth = rx * 0.050f),
        )
    }

    private fun orb(
        rig: VanRig,
        palette: VanStatusPalette,
        state: VanVisualState,
        frame: VanSceneFrame,
    ): List<VanDrawOp> {
        val offline = state.durableState == VanDurableState.OFFLINE ||
            state.durableState == VanDurableState.SLEEPING
        val orbColor = if (offline) VanColors.desaturate(palette.accent, 0.85f) else palette.accent
        val alive = if (offline) 0.35f else 1f
        val r = rig.orbR * if (offline) 0.82f else 1f
        val ops = mutableListOf<VanDrawOp>()

        if (!offline) {
            ops += VanDrawOp.Circle(rig.orbCx, rig.orbCy, r * 1.85f, VanColors.scaleAlpha(orbColor, 0.10f))
            ops += VanDrawOp.Circle(rig.orbCx, rig.orbCy, r * 1.38f, VanColors.scaleAlpha(orbColor, 0.20f))
        }
        // Deep navy sphere with a lit face — the orb is a companion, not a status dot.
        ops += VanDrawOp.Circle(rig.orbCx, rig.orbCy, r, VanColors.of(ORB_BODY))
        ops += VanDrawOp.Circle(
            rig.orbCx,
            rig.orbCy,
            r,
            VanColors.scaleAlpha(orbColor, 0.85f * alive + 0.15f),
            strokeWidth = r * 0.14f,
        )
        val faceAlpha = 0.92f * alive + 0.08f
        listOf(-1f, 1f).forEach { side ->
            ops += VanDrawOp.Oval(
                rig.orbCx + side * r * 0.34f,
                rig.orbCy - r * 0.10f,
                r * 0.15f,
                r * 0.23f,
                VanColors.scaleAlpha(orbColor, faceAlpha),
            )
        }
        ops += VanDrawOp.PathOp(
            vanPath {
                moveTo(rig.orbCx - r * 0.34f, rig.orbCy + r * 0.34f)
                quadTo(rig.orbCx, rig.orbCy + r * 0.66f, rig.orbCx + r * 0.34f, rig.orbCy + r * 0.34f)
            },
            VanColors.scaleAlpha(orbColor, faceAlpha),
            strokeWidth = r * 0.12f,
        )
        ops += VanDrawOp.Circle(
            rig.orbCx - r * 0.44f,
            rig.orbCy - r * 0.52f,
            r * 0.20f,
            VanColors.of(0xFFFFFFFFL, 0.55f * alive + 0.10f),
        )

        // Two orbit motes read as "holographic" without adding glow.
        if (!offline) {
            val motion = if (frame.reducedMotion) 0f else 1f
            val tau = (2f * PI).toFloat()
            listOf(0f, 0.5f).forEach { offset ->
                val a = (frame.phase + offset) * tau * motion + offset * tau
                ops += VanDrawOp.Circle(
                    rig.orbCx + cos(a) * r * 1.55f,
                    rig.orbCy + sin(a) * r * 0.72f,
                    r * 0.16f,
                    VanColors.scaleAlpha(orbColor, 0.75f),
                )
            }
        }
        return ops
    }

    /**
     * State marks are broken arcs and hologram fragments — never a full ring (Gate A).
     * Distinct shapes carry warning/error/success/urgent/approval in grayscale (Gate E).
     */
    private fun statusMarks(
        rig: VanRig,
        palette: VanStatusPalette,
        @Suppress("UNUSED_PARAMETER") state: VanVisualState,
        frame: VanSceneFrame,
    ): List<VanDrawOp> {
        val cx = 0.5f
        val cy = 0.48f
        val r = rig.ringR
        val motion = if (frame.reducedMotion) 0f else 1f
        val spin = frame.phase * 40f * motion
        val width = 0.018f
        val ops = mutableListOf<VanDrawOp>()
        val ink = VanColors.scaleAlpha(palette.accent, 0.88f)

        when (palette.ringStyle) {
            VanRingStyle.NONE -> Unit
            VanRingStyle.PROGRESS -> {
                ops += VanDrawOp.Arc(cx, cy, r, -48f + spin, 86f, ink, width)
                ops += VanDrawOp.Arc(cx, cy, r * 1.06f, 122f - spin * 0.4f, 54f, VanColors.scaleAlpha(palette.accent, 0.45f), width * 0.8f)
            }
            VanRingStyle.DOTS -> {
                repeat(3) { i ->
                    val a = Math.toRadians((spin + i * 48f + 18f).toDouble()).toFloat()
                    ops += VanDrawOp.Circle(
                        cx + cos(a) * r * 0.92f,
                        cy + sin(a) * r * 0.78f,
                        0.016f,
                        VanColors.scaleAlpha(palette.accent, 0.55f + 0.12f * i),
                    )
                }
            }
            VanRingStyle.DASHED -> {
                repeat(5) { i ->
                    val start = -70f + i * 52f
                    ops += VanDrawOp.Arc(cx, cy, r, start, 22f, VanColors.scaleAlpha(palette.accent, if (i % 2 == 0) 0.8f else 0.28f), width)
                }
            }
            VanRingStyle.PULSE -> {
                ops += VanDrawOp.Arc(cx, cy, r, -30f, 72f, ink, width)
                ops += VanDrawOp.Arc(cx, cy, r * 0.90f, 150f, 64f, VanColors.scaleAlpha(palette.accent, 0.4f), width * 0.8f)
            }
            VanRingStyle.DOUBLE -> {
                ops += VanDrawOp.Arc(cx, cy, r, -150f, 96f, ink, width)
                ops += VanDrawOp.Arc(cx, cy, r, 28f, 88f, ink, width)
            }
        }
        return ops
    }

    private fun hologramGlyph(
        rig: VanRig,
        palette: VanStatusPalette,
        state: VanVisualState,
    ): List<VanDrawOp> {
        val gx = rig.headCx + rig.headRx * 1.05f
        val gy = rig.headCy + rig.headRy * 1.05f
        val ink = VanColors.scaleAlpha(palette.accent, 0.92f)
        val fill = VanColors.scaleAlpha(palette.accent, 0.42f)
        return when (state.durableState) {
            VanDurableState.WAITING_FOR_OWNER -> listOf(
                VanDrawOp.RoundRect(gx, gy, 0.110f, 0.078f, 0.018f, fill),
                VanDrawOp.RoundRect(gx, gy, 0.110f, 0.078f, 0.018f, ink, 0.012f),
                VanDrawOp.RoundRect(gx, gy - 0.012f, 0.055f, 0.010f, 0.006f, ink),
            )
            VanDurableState.WARNING -> listOf(
                VanDrawOp.PathOp(
                    vanPath {
                        moveTo(gx, gy - 0.095f)
                        lineTo(gx + 0.090f, gy + 0.070f)
                        lineTo(gx - 0.090f, gy + 0.070f)
                        close()
                    },
                    fill,
                ),
                VanDrawOp.PathOp(
                    vanPath {
                        moveTo(gx, gy - 0.095f)
                        lineTo(gx + 0.090f, gy + 0.070f)
                        lineTo(gx - 0.090f, gy + 0.070f)
                        close()
                    },
                    ink,
                    strokeWidth = 0.014f,
                ),
            )
            VanDurableState.ERROR -> listOf(
                VanDrawOp.Oval(gx, gy, 0.072f, 0.072f, fill),
                VanDrawOp.PathOp(vanPath { moveTo(gx - 0.048f, gy - 0.048f); lineTo(gx + 0.048f, gy + 0.048f) }, ink, 0.018f),
                VanDrawOp.PathOp(vanPath { moveTo(gx + 0.048f, gy - 0.048f); lineTo(gx - 0.048f, gy + 0.048f) }, ink, 0.018f),
            )
            VanDurableState.SUCCESS -> listOf(
                VanDrawOp.Circle(gx, gy, 0.078f, fill),
                VanDrawOp.PathOp(
                    vanPath {
                        moveTo(gx - 0.042f, gy)
                        lineTo(gx - 0.010f, gy + 0.036f)
                        lineTo(gx + 0.052f, gy - 0.040f)
                    },
                    ink,
                    strokeWidth = 0.018f,
                ),
            )
            VanDurableState.URGENT -> listOf(
                VanDrawOp.PathOp(
                    vanPath {
                        moveTo(gx - 0.078f, gy + 0.070f)
                        lineTo(gx, gy - 0.095f)
                        lineTo(gx + 0.078f, gy + 0.070f)
                        close()
                    },
                    fill,
                ),
                VanDrawOp.PathOp(
                    vanPath {
                        moveTo(gx - 0.078f, gy + 0.070f)
                        lineTo(gx, gy - 0.095f)
                        lineTo(gx + 0.078f, gy + 0.070f)
                    },
                    ink,
                    strokeWidth = 0.016f,
                ),
            )
            VanDurableState.LISTENING -> listOf(-0.048f, 0f, 0.048f).mapIndexed { i, dx ->
                VanDrawOp.RoundRect(gx + dx, gy, 0.014f, 0.028f + i * 0.014f, 0.006f, ink)
            }
            else -> emptyList()
        }
    }
}
