package com.dial.van.visual

import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/** How much of Van is composed for the surface he is appearing on. */
enum class VanPresentation {
    /** Floating overlay bubble — framed on head and shoulders so the face reads at ~72dp. */
    COMPACT,

    /** Mid-size docked card with quick actions. */
    EXPANDED,

    /** Full Command Centre composition: the whole figure, framed like the Rive artboard. */
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

/**
 * Maps Candidate B board pixels into the framed unit square. Every coordinate in [VanScene]
 * is a point measured on the native Candidate B front view, so the fallback is drawn from the
 * same landmarks as the reference pack and the flame aura, not from a separate guess.
 */
private class Pen(val framing: VanFraming) {
    fun x(boardX: Float): Float = framing.x(VanBodyLayout.u(boardX))
    fun y(boardY: Float): Float = framing.y(VanBodyLayout.v(boardY))
    fun l(boardPx: Float): Float = VanBodyLayout.len(boardPx) * framing.zoom

    /** The board y that lands at framed [y]; used to keep limbs inside a zoomed frame. */
    fun boardYAt(y: Float): Float = 8f + (framing.unframeY(y) - 0.07f) / VanBodyLayout.len(1f)

    /**
     * Lower-body shapes are clamped to just outside the box. A zoomed framing crops the legs,
     * and a clamped polygon stays drawable where a dropped one would leave a hole at the edge.
     */
    fun poly(color: Int, vararg board: Pair<Float, Float>): VanDrawOp.PathOp = VanDrawOp.PathOp(
        vanPath {
            board.forEachIndexed { i, (bx, by) ->
                val px = x(bx).coerceIn(-0.10f, 1.10f)
                val py = y(by).coerceIn(-0.10f, 1.10f)
                if (i == 0) moveTo(px, py) else lineTo(px, py)
            }
            close()
        },
        color,
    )
}

/**
 * Builds VAN as renderer-independent ops: Candidate B (CF-D-05-REV2_1) drawn procedurally.
 *
 * This is the interim character until the authored `.riv` lands. It follows the identity lock
 * element for element: spiky silver hair, a clear blue goggle visor with cyan trim and dark
 * side pods over large blue eyes, medium-brown skin (#AF6A53), a black/white technical jacket
 * over a charcoal underlayer, full black gloves, black cargo trousers and white boots, DIAL cyan
 * accents, and the dark orb companion with two vertical cyan bar eyes. The compact overlay
 * frames head and shoulders ([VanFraming.COMPACT]); the Command Centre shows the whole figure,
 * framed like the Rive artboard.
 */
object VanScene {

    const val SKIN = 0xFFAF6A53L
    const val SKIN_SHADOW = 0xFF774137L
    const val HAIR = 0xFFE9EDF3L
    const val HAIR_SHADOW = 0xFFB1A3A8L
    const val BROW = 0xFF3A2A26L
    const val EYE_IRIS = 0xFF1E88E5L
    const val EYE_IRIS_DEEP = 0xFF0D47A1L
    const val EYE_SCLERA = 0xFFF2F6FAL
    const val EYE_PUPIL = 0xFF10233AL
    /** The clear goggle lens (identity lock `visor.lens`). */
    const val VISOR = 0xFF3F8ACEL
    const val VISOR_FRAME = 0xFF00E5FFL
    const val VISOR_POD = 0xFF1F212AL
    const val JACKET = 0xFF15181CL
    const val JACKET_PANEL = 0xFFEDEFF3L
    const val UNDERLAYER = 0xFF2B3138L
    const val MOUTH = 0xFF4A2A1AL
    const val GLOVE = 0xFF111820L
    const val ORB_BODY = 0xFF020C1CL
    const val ORB_FACE = 0xFF0A1A2EL
    const val ORB_EYE = 0xFF00E5FFL

    fun build(state: VanVisualState, frame: VanSceneFrame): List<VanDrawOp> {
        val palette = VanStatusPalette.forState(state.durableState)
        val pen = Pen(VanFraming.forPresentation(frame.presentation))
        val motion = if (frame.reducedMotion) 0f else 1f
        val tau = (2f * PI).toFloat()

        val bodyBob = sin(frame.phase * tau) * 0.006f * motion * pen.framing.zoom
        val headBob = sin(frame.phase * tau + 0.6f) * 0.004f * motion * pen.framing.zoom

        val character = buildList {
            addAll(backLayers(pen))
            addAll(legs(pen, palette))
            addAll(torso(pen, palette))
            addAll(arms(pen, palette, state))
            addAll(neck(pen))
        }.translated(0f, bodyBob)

        val head = buildList {
            addAll(headShape(pen))
            addAll(eyes(pen, state, frame))
            addAll(brows(pen, palette, state))
            addAll(visor(pen, palette))
            addAll(mouth(pen, palette, state))
            addAll(hair(pen))
        }.translated(0f, bodyBob + headBob + actionHeadDrop(state) * pen.framing.zoom)

        val orbDrift = sin(frame.phase * tau + 1.9f) * 0.012f * motion * pen.framing.zoom
        val orb = orb(pen, palette, state, frame)
            .translated(state.attentionX * pen.l(18f), orbDrift + state.attentionY * pen.l(12f))

        val muted = (character + head).muted(palette.desaturation, palette.dim)

        return muted +
            statusMarks(pen, palette, state, frame) +
            hologramGlyph(pen, palette, state) +
            orb
    }

    /**
     * Only the state marks: broken status arcs and the hologram glyph (triangle, card, cross,
     * tick…). Drawn over the interim Candidate B art, which is a still and cannot carry them,
     * so critical states stay distinguishable by shape in grayscale (Gate E) whichever
     * renderer is showing VAN.
     */
    fun stateMarks(state: VanVisualState, frame: VanSceneFrame): List<VanDrawOp> {
        val palette = VanStatusPalette.forState(state.durableState)
        val pen = Pen(VanFraming.forPresentation(frame.presentation))
        return statusMarks(pen, palette, state, frame) + hologramGlyph(pen, palette, state)
    }

    /** Exposed so overlay chrome and previews can label state with the same words. */
    fun statusLabel(state: VanDurableState): String = VanStatusPalette.forState(state).label

    /** Where the orb sits in a framing — the companion floats over VAN's open palm. */
    fun orbCentre(presentation: VanPresentation): Pair<Float, Float> {
        val pen = Pen(VanFraming.forPresentation(presentation))
        return pen.x(ORB_X) to pen.y(ORB_Y)
    }

    private const val ORB_X = 67f
    private const val ORB_Y = 171f
    private const val ORB_R = 50f
    private const val FACE_X = 190f

    private fun actionHeadDrop(state: VanVisualState): Float = when (VanFiniteAction.fromCode(state.actionCode)) {
        VanFiniteAction.ACK_NOD -> 0.016f
        VanFiniteAction.SHRUG -> 0.008f
        else -> 0f
    }

    private fun backLayers(pen: Pen): List<VanDrawOp> = listOf(
        VanDrawOp.Oval(pen.x(FACE_X), pen.y(86f), pen.l(90f), pen.l(60f), VanColors.of(HAIR_SHADOW)),
        pen.poly(VanColors.of(JACKET), 128f to 168f, 262f to 168f, 292f to 222f, 108f to 222f),
    )

    private fun legs(pen: Pen, palette: VanStatusPalette): List<VanDrawOp> {
        val trousers = VanColors.of(JACKET)
        val accent = VanColors.scaleAlpha(palette.accent, 0.9f)
        return listOf(
            pen.poly(trousers, 135f to 330f, 197f to 330f, 180f to 414f, 124f to 414f),
            pen.poly(trousers, 125f to 410f, 179f to 410f, 164f to 460f, 114f to 460f),
            pen.poly(trousers, 208f to 330f, 270f to 330f, 278f to 414f, 222f to 414f),
            pen.poly(trousers, 223f to 410f, 277f to 410f, 294f to 460f, 242f to 460f),
            pen.poly(accent, 122f to 368f, 152f to 376f, 150f to 384f, 121f to 377f),
            pen.poly(accent, 234f to 384f, 266f to 368f, 268f to 377f, 236f to 392f),
            // White technical boots with dark soles and the cyan triangle badge.
            pen.poly(VanColors.of(JACKET_PANEL), 84f to 448f, 184f to 448f, 192f to 500f, 190f to 516f, 84f to 516f, 80f to 500f),
            pen.poly(VanColors.of(JACKET), 80f to 506f, 192f to 506f, 190f to 518f, 82f to 518f),
            pen.poly(accent, 126f to 462f, 148f to 462f, 137f to 478f),
            pen.poly(VanColors.of(JACKET_PANEL), 232f to 448f, 310f to 448f, 316f to 500f, 314f to 516f, 230f to 516f, 228f to 500f),
            pen.poly(VanColors.of(JACKET), 228f to 506f, 316f to 506f, 314f to 518f, 230f to 518f),
            pen.poly(accent, 262f to 462f, 284f to 462f, 273f to 478f),
        )
    }

    private fun torso(pen: Pen, palette: VanStatusPalette): List<VanDrawOp> {
        val panel = VanColors.of(JACKET_PANEL, 0.96f)
        val accent = VanColors.scaleAlpha(palette.accent, 0.9f)
        return listOf(
            pen.poly(VanColors.of(JACKET), 106f to 192f, 300f to 192f, 314f to 340f, 98f to 340f),
            pen.poly(VanColors.of(UNDERLAYER), 170f to 196f, 232f to 196f, 228f to 300f, 172f to 300f),
            // White shoulder yokes and lower side panels over the black body.
            pen.poly(panel, 106f to 192f, 150f to 188f, 140f to 240f, 100f to 252f),
            pen.poly(panel, 300f to 192f, 252f to 188f, 262f to 240f, 306f to 252f),
            pen.poly(panel, 98f to 262f, 150f to 272f, 162f to 340f, 98f to 340f),
            pen.poly(panel, 306f to 262f, 250f to 272f, 238f to 340f, 314f to 340f),
            pen.poly(VanColors.of(JACKET), 150f to 300f, 250f to 300f, 250f to 312f, 150f to 312f),
            // Hood collar and its cyan trim.
            pen.poly(VanColors.of(JACKET), 134f to 180f, 176f to 162f, 188f to 204f, 150f to 214f),
            pen.poly(VanColors.of(JACKET), 266f to 180f, 208f to 162f, 202f to 204f, 250f to 214f),
            VanDrawOp.PathOp(
                vanPath {
                    moveTo(pen.x(136f), pen.y(184f))
                    quadTo(pen.x(170f), pen.y(160f), pen.x(190f), pen.y(206f))
                    quadTo(pen.x(212f), pen.y(160f), pen.x(264f), pen.y(184f))
                },
                accent,
                strokeWidth = pen.l(4f),
            ),
            // Zip and flank piping.
            VanDrawOp.PathOp(vanPath { moveTo(pen.x(186f), pen.y(204f)); lineTo(pen.x(186f), pen.y(336f)) }, accent, strokeWidth = pen.l(3.5f)),
            VanDrawOp.PathOp(vanPath { moveTo(pen.x(146f), pen.y(206f)); lineTo(pen.x(150f), pen.y(320f)) }, accent, strokeWidth = pen.l(3f)),
            // DIAL "D" emblem on the right chest.
            VanDrawOp.RoundRect(
                cx = pen.x(216f), cy = pen.y(236f), halfW = pen.l(2.6f), halfH = pen.l(12f), radius = pen.l(2.6f),
                color = VanColors.scaleAlpha(palette.accent, 0.95f),
            ),
            VanDrawOp.Arc(
                cx = pen.x(216f), cy = pen.y(236f), r = pen.l(12f), startDegrees = -90f, sweepDegrees = 180f,
                color = VanColors.scaleAlpha(palette.accent, 0.95f), strokeWidth = pen.l(4.5f),
            ),
        )
    }

    private fun arms(pen: Pen, palette: VanStatusPalette, state: VanVisualState): List<VanDrawOp> {
        val action = VanFiniteAction.fromCode(state.actionCode)
        val presenting = state.durableState == VanDurableState.SPEAKING ||
            state.durableState == VanDurableState.DELEGATING ||
            action == VanFiniteAction.PRESENT_CARD

        // Candidate B's rest pose: viewer-left palm open under the orb, viewer-right arm down.
        var left = 48f to 262f
        var right = 302f to 350f
        if (presenting) right = 318f to 300f
        when (action) {
            VanFiniteAction.HELLO_WAVE -> right = 306f to 72f
            VanFiniteAction.ACK_NOD -> right = 302f to 336f
            VanFiniteAction.POINT_LEFT -> left = 18f to 196f
            VanFiniteAction.POINT_RIGHT -> right = 372f to 200f
            VanFiniteAction.POINT_UP -> right = 292f to 40f
            VanFiniteAction.POINT_DOWN -> right = 330f to 400f
            VanFiniteAction.POINT_TARGET -> right = 362f to 150f
            VanFiniteAction.CELEBRATE -> { left = 88f to 64f; right = 304f to 52f }
            VanFiniteAction.CAUTION -> right = 282f to 150f
            VanFiniteAction.CONFIRM -> right = 250f to 250f
            VanFiniteAction.SHRUG -> { left = 78f to 228f; right = 324f to 228f }
            VanFiniteAction.OPEN_PANEL -> { left = 38f to 286f; right = 362f to 286f }
            VanFiniteAction.CLOSE_PANEL -> { left = 152f to 296f; right = 248f to 296f }
            VanFiniteAction.PRESENT_CARD -> Unit
            null -> Unit
        }

        val ops = mutableListOf<VanDrawOp>()
        for ((shoulder, hand, side) in listOf(Triple(136f to 206f, left, -1f), Triple(270f to 206f, right, 1f))) {
            val (sx, sy) = shoulder
            val hx = hand.first
            // A zoomed framing crops the hanging hand; keep the glove inside the box.
            val hy = minOf(hand.second, pen.boardYAt(0.97f))
            // The elbow bows outward and down, so every hand target reads as a bent arm.
            val ex = (sx + hx) / 2f + side * 26f
            val ey = (sy + hy) / 2f + 22f
            ops += VanDrawOp.PathOp(
                vanPath { moveTo(pen.x(sx), pen.y(sy)); quadTo(pen.x(ex), pen.y(ey), pen.x((ex + hx) / 2f), pen.y((ey + hy) / 2f)) },
                VanColors.of(JACKET_PANEL),
                strokeWidth = pen.l(40f),
            )
            ops += VanDrawOp.PathOp(
                vanPath { moveTo(pen.x((ex + hx) / 2f), pen.y((ey + hy) / 2f)); lineTo(pen.x(hx), pen.y(hy)) },
                VanColors.of(JACKET),
                strokeWidth = pen.l(34f),
            )
            ops += VanDrawOp.Oval(pen.x(hx), pen.y(hy), pen.l(24f), pen.l(20f), VanColors.of(GLOVE))
            ops += VanDrawOp.Circle(
                pen.x(hx), pen.y(hy) - pen.l(18f), pen.l(15f),
                VanColors.scaleAlpha(palette.accent, 0.8f), pen.l(4f),
            )
        }

        if (action == VanFiniteAction.PRESENT_CARD) {
            val (hx, hy) = right
            ops += VanDrawOp.RoundRect(pen.x(hx + 6f), pen.y(hy - 62f), pen.l(42f), pen.l(32f), pen.l(8f), VanColors.scaleAlpha(palette.accent, 0.18f))
            ops += VanDrawOp.RoundRect(pen.x(hx + 6f), pen.y(hy - 62f), pen.l(42f), pen.l(32f), pen.l(8f), VanColors.scaleAlpha(palette.accent, 0.75f), pen.l(3.5f))
        }
        if (action == VanFiniteAction.POINT_LEFT || action == VanFiniteAction.POINT_RIGHT ||
            action == VanFiniteAction.POINT_UP || action == VanFiniteAction.POINT_DOWN ||
            action == VanFiniteAction.POINT_TARGET
        ) {
            val fromLeft = action == VanFiniteAction.POINT_LEFT
            val (ox, oy) = if (fromLeft) left else right
            val tipX = ox + if (fromLeft) -44f else 36f
            val tipY = when (action) {
                VanFiniteAction.POINT_UP -> oy - 44f
                VanFiniteAction.POINT_DOWN -> oy + 44f
                else -> oy
            }
            // Full gloves (CF-D-05-REV2_1): the pointing finger is glove, not skin.
            ops += VanDrawOp.PathOp(
                vanPath { moveTo(pen.x(ox), pen.y(oy)); lineTo(pen.x(tipX), pen.y(tipY)) },
                VanColors.of(GLOVE),
                strokeWidth = pen.l(10f),
            )
        }
        return ops
    }

    private fun neck(pen: Pen): List<VanDrawOp> = listOf(
        VanDrawOp.RoundRect(
            cx = pen.x(191f), cy = pen.y(178f), halfW = pen.l(16f), halfH = pen.l(15f), radius = pen.l(6f),
            color = VanColors.of(SKIN_SHADOW),
        ),
    )

    private fun headShape(pen: Pen): List<VanDrawOp> {
        val jaw = vanPath {
            moveTo(pen.x(128f), pen.y(118f))
            quadTo(pen.x(136f), pen.y(166f), pen.x(FACE_X), pen.y(172f))
            quadTo(pen.x(244f), pen.y(166f), pen.x(252f), pen.y(118f))
            close()
        }
        return listOf(
            VanDrawOp.Oval(pen.x(126f), pen.y(130f), pen.l(10f), pen.l(15f), VanColors.of(SKIN_SHADOW)),
            VanDrawOp.Oval(pen.x(256f), pen.y(130f), pen.l(10f), pen.l(15f), VanColors.of(SKIN_SHADOW)),
            VanDrawOp.Oval(pen.x(FACE_X), pen.y(114f), pen.l(64f), pen.l(54f), VanColors.of(SKIN)),
            VanDrawOp.PathOp(jaw, VanColors.of(SKIN)),
        )
    }

    private fun eyes(pen: Pen, state: VanVisualState, frame: VanSceneFrame): List<VanDrawOp> {
        val eyeY = pen.y(122f)
        val open = (1f - frame.blink.coerceIn(0f, 1f))
        val scleraRx = pen.l(17f)
        val scleraRy = pen.l(14f) * open.coerceAtLeast(0.04f)
        val irisR = pen.l(11.5f)
        val gazeX = state.attentionX.coerceIn(-1f, 1f) * pen.l(4f)
        val gazeY = state.attentionY.coerceIn(-1f, 1f) * pen.l(2.5f)

        val ops = mutableListOf<VanDrawOp>()
        for (bx in listOf(158f, 220f)) {
            val ex = pen.x(bx)
            ops += VanDrawOp.Oval(ex, eyeY, scleraRx, scleraRy, VanColors.of(EYE_SCLERA))
            if (open > 0.2f) {
                ops += VanDrawOp.Circle(ex + gazeX, eyeY + gazeY, irisR * open, VanColors.of(EYE_IRIS))
                ops += VanDrawOp.Circle(ex + gazeX, eyeY + gazeY, irisR * 0.92f * open, VanColors.of(EYE_IRIS_DEEP, 0.45f))
                ops += VanDrawOp.Circle(ex + gazeX, eyeY + gazeY, irisR * 0.46f * open, VanColors.of(EYE_PUPIL))
                ops += VanDrawOp.Circle(
                    ex + gazeX - irisR * 0.38f,
                    eyeY + gazeY - irisR * 0.42f,
                    irisR * 0.28f * open,
                    VanColors.of(0xFFFFFFFFL, 0.9f),
                )
            }
            if (frame.blink > 0.02f) {
                ops += VanDrawOp.RoundRect(
                    cx = ex,
                    cy = eyeY - scleraRy - pen.l(14f) * (1f - frame.blink) * 0.5f,
                    halfW = scleraRx * 1.18f,
                    halfH = pen.l(14f) * frame.blink,
                    radius = pen.l(4f),
                    color = VanColors.of(SKIN),
                )
            }
        }
        return ops
    }

    private fun brows(pen: Pen, palette: VanStatusPalette, state: VanVisualState): List<VanDrawOp> {
        val concern = when (palette.mood) {
            VanMood.CONCERNED -> 1f
            VanMood.ALERT -> 0.35f
            else -> 0f
        } * (0.4f + 0.6f * state.urgency.coerceIn(0f, 1f)).coerceAtLeast(0.4f)
        val lift = if (palette.mood == VanMood.ALERT) 4f else 0f
        return listOf(158f to -1f, 220f to 1f).map { (bx, side) ->
            val inner = bx - side * 14f
            val outer = bx + side * 18f
            VanDrawOp.PathOp(
                vanPath {
                    moveTo(pen.x(inner), pen.y(100f + 7f * concern))
                    quadTo(pen.x(bx), pen.y(92f - lift), pen.x(outer), pen.y(97f - lift * 0.6f))
                },
                VanColors.of(BROW, 0.95f),
                strokeWidth = pen.l(5f),
            )
        }
    }

    private fun visor(pen: Pen, palette: VanStatusPalette): List<VanDrawOp> {
        val cx = pen.x(190f)
        val cy = pen.y(122f)
        val halfW = pen.l(66f)
        val halfH = pen.l(22f)
        val specular = vanPath {
            moveTo(cx - halfW * 0.80f, cy + halfH * 0.55f)
            lineTo(cx - halfW * 0.34f, cy - halfH * 0.80f)
            lineTo(cx - halfW * 0.12f, cy - halfH * 0.80f)
            lineTo(cx - halfW * 0.58f, cy + halfH * 0.55f)
            close()
        }
        return listOf(
            // Clear lens first, so the large blue eyes read through it.
            VanDrawOp.RoundRect(cx, cy, halfW, halfH, halfH * 0.85f, VanColors.of(VISOR, 0.30f)),
            VanDrawOp.PathOp(specular, VanColors.of(0xFFFFFFFFL, 0.18f)),
            VanDrawOp.RoundRect(cx, cy, halfW, halfH, halfH * 0.85f, VanColors.of(VISOR_FRAME, 0.92f), strokeWidth = pen.l(3.5f)),
            // Dark side pods, each with a cyan status light.
            VanDrawOp.Oval(cx - halfW - pen.l(3f), cy, pen.l(8f), pen.l(15f), VanColors.of(VISOR_POD)),
            VanDrawOp.Oval(cx + halfW + pen.l(3f), cy, pen.l(8f), pen.l(15f), VanColors.of(VISOR_POD)),
            VanDrawOp.Circle(cx + halfW + pen.l(3f), cy, pen.l(3f), VanColors.scaleAlpha(palette.accent, 0.95f)),
        )
    }

    private fun mouth(pen: Pen, palette: VanStatusPalette, state: VanVisualState): List<VanDrawOp> {
        val mx = pen.x(193f)
        val my = pen.y(153f)
        val openness = state.mouthOpen.coerceIn(0f, 1f)
        val speaking = state.speaking || openness > 0.05f
        if (speaking) {
            val h = pen.l(3f + 9f * openness)
            val w = pen.l(13f + 5f * openness)
            return listOf(
                VanDrawOp.Oval(mx, my, w, h, VanColors.of(MOUTH)),
                VanDrawOp.Oval(mx, my + h * 0.42f, w * 0.62f, h * 0.42f, VanColors.of(0xFFD98C7AL, 0.75f)),
            )
        }
        val curve = when (palette.mood) {
            VanMood.PLEASED -> pen.l(8f)
            VanMood.CALM -> pen.l(5.5f)
            VanMood.ALERT -> pen.l(2.5f)
            VanMood.MUTED -> 0f
            VanMood.CONCERNED -> -pen.l(3.5f)
        }
        return listOf(
            VanDrawOp.PathOp(
                vanPath {
                    moveTo(mx - pen.l(16f), my - curve * 0.30f)
                    quadTo(mx, my + curve, mx + pen.l(16f), my - curve * 0.30f)
                },
                VanColors.of(MOUTH, 0.85f),
                strokeWidth = pen.l(3.5f),
            ),
        )
    }

    /**
     * Spiky, voluminous silver hair as defined locks: the outline is walked through Candidate
     * B's spike tips and valleys, then closed along a fringe that falls over the brow.
     * Straight segments are deliberate: rounded curves read as a swim cap at overlay size.
     */
    private fun hair(pen: Pen): List<VanDrawOp> {
        val tips = listOf(
            104f to 118f, 94f to 92f, 110f to 72f, 100f to 52f, 126f to 44f, 124f to 20f, 156f to 26f,
            170f to 8f, 196f to 20f, 224f to 8f, 234f to 32f, 264f to 30f, 260f to 54f, 288f to 68f,
            268f to 84f, 280f to 106f, 256f to 100f, 244f to 86f, 226f to 100f, 212f to 86f, 196f to 102f,
            184f to 88f, 166f to 100f, 154f to 88f, 138f to 100f, 126f to 98f, 116f to 122f,
        )
        val mass = vanPath {
            tips.forEachIndexed { i, (bx, by) ->
                if (i == 0) moveTo(pen.x(bx), pen.y(by)) else lineTo(pen.x(bx), pen.y(by))
            }
            close()
        }
        val strandLow = vanPath {
            moveTo(pen.x(116f), pen.y(78f)); quadTo(pen.x(180f), pen.y(46f), pen.x(262f), pen.y(66f))
        }
        val strandMid = vanPath {
            moveTo(pen.x(132f), pen.y(56f)); quadTo(pen.x(190f), pen.y(28f), pen.x(248f), pen.y(46f))
        }
        val highlight = vanPath {
            moveTo(pen.x(150f), pen.y(40f)); quadTo(pen.x(192f), pen.y(22f), pen.x(232f), pen.y(30f))
        }
        return listOf(
            VanDrawOp.PathOp(mass, VanColors.of(HAIR)),
            VanDrawOp.PathOp(strandLow, VanColors.of(HAIR_SHADOW, 0.85f), strokeWidth = pen.l(4.5f)),
            VanDrawOp.PathOp(strandMid, VanColors.of(HAIR_SHADOW, 0.55f), strokeWidth = pen.l(3.5f)),
            VanDrawOp.PathOp(highlight, VanColors.of(0xFFFFFFFFL, 0.80f), strokeWidth = pen.l(3f)),
        )
    }

    /** The dark orb companion: navy-black shell, cyan rim, two vertical cyan bar eyes, no mouth. */
    private fun orb(
        pen: Pen,
        palette: VanStatusPalette,
        state: VanVisualState,
        frame: VanSceneFrame,
    ): List<VanDrawOp> {
        val offline = state.durableState == VanDurableState.OFFLINE ||
            state.durableState == VanDurableState.SLEEPING
        val eye = if (offline) VanColors.desaturate(VanColors.of(ORB_EYE), 0.85f) else VanColors.of(ORB_EYE)
        val alive = if (offline) 0.35f else 1f
        val cx = pen.x(ORB_X)
        val cy = pen.y(ORB_Y)
        val r = pen.l(ORB_R) * if (offline) 0.9f else 1f
        val ops = mutableListOf<VanDrawOp>()
        if (!offline) {
            ops += VanDrawOp.Circle(cx, cy, r * 1.30f, VanColors.scaleAlpha(palette.accent, 0.12f))
        }
        ops += VanDrawOp.Circle(cx, cy, r, VanColors.of(ORB_BODY))
        ops += VanDrawOp.Circle(cx, cy, r * 0.94f, VanColors.scaleAlpha(eye, 0.70f * alive + 0.15f), strokeWidth = r * 0.06f)
        ops += VanDrawOp.Circle(cx + r * 0.18f, cy - r * 0.04f, r * 0.64f, VanColors.of(ORB_FACE))
        // Bar eyes squash into a blink with VAN's own blink.
        val squash = (1f - frame.blink.coerceIn(0f, 1f) * 0.85f)
        for (dx in listOf(0.02f, 0.40f)) {
            ops += VanDrawOp.RoundRect(
                cx = cx + r * dx,
                cy = cy - r * 0.04f,
                halfW = r * 0.075f,
                halfH = r * 0.24f * squash,
                radius = r * 0.075f,
                color = VanColors.scaleAlpha(eye, 0.92f * alive + 0.08f),
            )
        }
        ops += VanDrawOp.Circle(cx - r * 0.46f, cy - r * 0.50f, r * 0.16f, VanColors.of(0xFFFFFFFFL, 0.45f * alive + 0.10f))
        return ops
    }

    /**
     * State marks are broken arcs and hologram fragments — never a full ring (Gate A).
     * Distinct shapes carry warning/error/success/urgent/approval in grayscale (Gate E).
     */
    private fun statusMarks(
        pen: Pen,
        palette: VanStatusPalette,
        @Suppress("UNUSED_PARAMETER") state: VanVisualState,
        frame: VanSceneFrame,
    ): List<VanDrawOp> {
        val cx = 0.5f
        val cy = 0.48f
        val r = 0.47f - 0.012f * (pen.framing.zoom - 1f)
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
        pen: Pen,
        palette: VanStatusPalette,
        state: VanVisualState,
    ): List<VanDrawOp> {
        val gx = pen.x(292f).coerceAtMost(0.86f)
        val gy = pen.y(176f)
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
