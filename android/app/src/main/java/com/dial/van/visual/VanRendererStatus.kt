package com.dial.van.visual

/**
 * GAP-F-014 — what the owner reads about which painter is actually driving VAN.
 *
 * [VanVisualRuntime.decide] already computes this every time the embodiment resolves a
 * renderer; nothing published it anywhere an owner-facing screen could read it, because
 * `VanAvatar`/`VanEmbodiment`'s `onDecision` callback had no caller anywhere in the app.
 * This is the pure fact it should carry, so Settings/diagnostics can show
 * "Character: Canvas fallback (Rive asset not installed)" — see [DegradedBridge] and
 * [VanRendererStatusPublisher] for how it reaches there.
 */
data class VanRendererStatus(
    val renderer: VanRenderer,
    val reason: VanCanvasReason,
    val sentence: String,
) {
    /** Anything short of the authored Rive artboard is a fallback worth surfacing. */
    val isFallback: Boolean get() = renderer != VanRenderer.RIVE

    companion object {
        fun from(decision: VanRenderDecision): VanRendererStatus = VanRendererStatus(
            renderer = decision.renderer,
            reason = decision.reason,
            sentence = VanVisualRuntime.describe(decision),
        )
    }
}

/**
 * Publishes a render decision through [DegradedBridge].
 *
 * Wired as [VanCanvasFallback]'s default `onDecision`, so every existing `VanAvatar`/
 * `VanEmbodiment` call site publishes without asking for it explicitly — see the doc on
 * [VanRendererStatus] for why that default had no effect before this.
 */
object VanRendererStatusPublisher {
    fun publish(decision: VanRenderDecision) {
        DegradedBridge.rendererStatus(VanRendererStatus.from(decision))
    }
}
