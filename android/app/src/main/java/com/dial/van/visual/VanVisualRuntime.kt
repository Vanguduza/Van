package com.dial.van.visual

/** Which painter is actually driving Van right now. */
enum class VanRenderer {
    /** Authored `van.riv` artboard. Still EXTERNAL work — never assumed present. */
    RIVE,

    /** Retired legacy bitmap rung. Kept only for binary/source compatibility; decide() never selects it. */
    OWNER_ART,

    /** Procedural Canvas character — last-resort interim embodiment. */
    CANVAS,

    /**
     * Real Candidate B art (native cut-out) — the owner's chosen interim VAN until `van.riv`
     * loads. A still that bobs; preferred over the procedural drawing whenever it is bundled.
     */
    CANDIDATE_B,
}

/** Why the authored artboard is not driving Van — surfaced in diagnostics rather than hidden. */
enum class VanCanvasReason {
    /** Rive is rendering; no fallback in play. */
    NOT_APPLICABLE,

    /** No `van.riv` in assets — the authored artboard is still EXTERNAL work. */
    ASSET_MISSING,

    /** A file exists but is too small to be a real artboard (placeholder or truncated). */
    ASSET_UNUSABLE,

    /** The Rive runtime classes or native library are unavailable on this device. */
    RUNTIME_UNAVAILABLE,

    /** The artboard/state machine failed to load or bind at runtime. */
    LOAD_FAILED,
}

data class VanRenderDecision(
    val renderer: VanRenderer,
    val reason: VanCanvasReason,
) {
    val usesCanvas: Boolean get() = renderer == VanRenderer.CANVAS
    val usesOwnerArt: Boolean get() = renderer == VanRenderer.OWNER_ART
    val usesCandidateB: Boolean get() = renderer == VanRenderer.CANDIDATE_B
}

/**
 * Chooses the painter for Van.
 *
 * Fails closed on visuals, and in the owner's stated order of preference: the authored Rive
 * artboard when it is genuinely loadable, otherwise real Candidate B art, otherwise the
 * procedural Canvas character. The retired owner-art poses are never selected. Anything short of a loadable artboard with a working runtime
 * leaves Rive, because a blank or half-bound avatar would misrepresent Van's state.
 */
object VanVisualRuntime {

    /** Smallest plausible authored artboard; below this we assume a placeholder. */
    const val MIN_ARTBOARD_BYTES = 1024L

    fun decide(
        assetBytes: Long?,
        riveRuntimeAvailable: Boolean,
        ownerArtAvailable: Boolean = false,
        loadFailed: Boolean = false,
        candidateBAvailable: Boolean = false,
    ): VanRenderDecision {
        val reason = when {
            loadFailed -> VanCanvasReason.LOAD_FAILED
            assetBytes == null -> VanCanvasReason.ASSET_MISSING
            assetBytes < MIN_ARTBOARD_BYTES -> VanCanvasReason.ASSET_UNUSABLE
            !riveRuntimeAvailable -> VanCanvasReason.RUNTIME_UNAVAILABLE
            else -> return VanRenderDecision(VanRenderer.RIVE, VanCanvasReason.NOT_APPLICABLE)
        }
        // Rejected/low-resolution owner-art bitmaps are deliberately retired. Even if an old
        // caller claims they are available, fail closed to the approved Canvas identity until
        // an accepted Rive asset loads. Candidate B art is the approved identity, not a rejected
        // bitmap, so it outranks the procedural drawing when it is bundled.
        if (candidateBAvailable) return VanRenderDecision(VanRenderer.CANDIDATE_B, reason)
        return VanRenderDecision(VanRenderer.CANVAS, reason)
    }

    fun describe(decision: VanRenderDecision): String = when (decision.renderer) {
        VanRenderer.RIVE -> "Rive artboard active"
        VanRenderer.OWNER_ART -> "Retired owner-art renderer (must never be selected) — ${describe(decision.reason)}"
        VanRenderer.CANVAS -> "Interim Canvas Van — ${describe(decision.reason)}"
        VanRenderer.CANDIDATE_B -> "Interim Candidate B art — ${describe(decision.reason)}"
    }

    fun describe(reason: VanCanvasReason): String = when (reason) {
        VanCanvasReason.NOT_APPLICABLE -> "Rive artboard active"
        VanCanvasReason.ASSET_MISSING -> "authored van.riv not installed"
        VanCanvasReason.ASSET_UNUSABLE -> "van.riv too small to be a real artboard"
        VanCanvasReason.RUNTIME_UNAVAILABLE -> "Rive runtime unavailable on this device"
        VanCanvasReason.LOAD_FAILED -> "Rive artboard failed to load"
    }
}
