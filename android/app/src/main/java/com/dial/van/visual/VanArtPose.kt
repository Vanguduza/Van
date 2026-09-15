package com.dial.van.visual

/**
 * Owner-supplied character art poses.
 *
 * The bitmaps are cut from the owner's design boards in `visual-authority/assets/pack/` by
 * `:visual-preview:extractOwnerArt` and land in `res/drawable-nodpi/` under [assetName].
 *
 * This enum is deliberately *not* part of `visual-authority/rive_contract.json`. The contract's
 * durable state IDs are untouched; [VanArtPoses.forState] is the mapping layer from those
 * canonical states onto the poses the owner's pack actually contains.
 */
enum class VanArtPose(val assetName: String) {
    IDLE("van_state_idle"),
    LISTENING("van_state_listening"),
    THINKING("van_state_thinking"),
    WORKING("van_state_working"),
    SEARCHING("van_state_searching"),
    NOTIFICATIONS("van_state_notifications"),
    SUCCESS("van_state_success"),
    WARNING("van_state_warning"),
}

object VanArtPoses {

    /**
     * Maps every contract durable state onto an owner pose.
     *
     * Where the pack has no dedicated pose the nearest owner-drawn pose is reused and the
     * status layer (aura accent, glass edge, copy) carries the difference — per §16, no state
     * is allowed to rely on colour alone, so the surrounding chrome always names the state too.
     *
     * OFFLINE, SLEEPING and DEGRADED intentionally reuse a lit pose and are then muted by
     * [VanStatusPalette.desaturation] and [VanStatusPalette.dim] (§6 OFFLINE / DEGRADED:
     * "VAN remains visible and recognisable", "should not look broken or corrupted").
     */
    fun forState(state: VanDurableState): VanArtPose = when (state) {
        VanDurableState.IDLE,
        VanDurableState.CONNECTING,
        VanDurableState.SPEAKING,
        VanDurableState.SLEEPING,
        VanDurableState.OFFLINE,
        -> VanArtPose.IDLE

        VanDurableState.LISTENING -> VanArtPose.LISTENING

        VanDurableState.THINKING,
        VanDurableState.DELEGATING,
        -> VanArtPose.THINKING

        VanDurableState.SEARCHING -> VanArtPose.SEARCHING

        VanDurableState.WORKING -> VanArtPose.WORKING

        // The owner's NOTIFICATIONS card is the "owner attention" pose.
        VanDurableState.ATTENTIVE,
        VanDurableState.WAITING,
        VanDurableState.WAITING_FOR_OWNER,
        -> VanArtPose.NOTIFICATIONS

        VanDurableState.SUCCESS -> VanArtPose.SUCCESS

        VanDurableState.WARNING,
        VanDurableState.ERROR,
        VanDurableState.URGENT,
        VanDurableState.DEGRADED,
        -> VanArtPose.WARNING
    }

    /** Poses whose owner art already contains the prop the state needs (waveform, tick, …). */
    fun hasDedicatedPose(state: VanDurableState): Boolean = when (state) {
        VanDurableState.LISTENING,
        VanDurableState.THINKING,
        VanDurableState.SEARCHING,
        VanDurableState.WORKING,
        VanDurableState.SUCCESS,
        VanDurableState.WARNING,
        VanDurableState.IDLE,
        -> true
        else -> false
    }
}
