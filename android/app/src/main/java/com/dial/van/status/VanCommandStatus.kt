package com.dial.van.status

/**
 * The status a conversation message carries, and how an owner status becomes one.
 *
 * This lives in the pure `status` package rather than beside the controller so that the
 * mapping can be compiled and executed by `android/verification`, which has no Android
 * toolchain. Finding P0-EXEC-003 was a `when` in the controller that nothing could test.
 */
enum class VanCommandStatus {
    LOCAL_DRAFT,
    SUBMITTING,
    APPROVAL_REQUIRED,
    ACCEPTED,
    IN_FLIGHT,
    SUCCEEDED,
    /** Finished, but partly. Not a success and not a failure (P0-EXEC-003). */
    PARTIALLY_SUCCEEDED,
    /** It finished and VAN could not confirm it worked. Retrying blindly may double it. */
    COULD_NOT_VERIFY,
    FAILED,
    /** VAN would not do this. Different from failing to do it, and acted on differently. */
    REFUSED,
    CANCELLED,
    EXPIRED,
    /**
     * The gateway said something this build does not recognise.
     *
     * The defect this replaces was `else -> ACCEPTED`: every unknown status, including
     * every status the gateway grew after this build shipped, read to the owner as
     * "under way". An honest "I do not know" is the only safe default.
     */
    UNKNOWN,
}

/**
 * The one place an owner status becomes a message status.
 *
 * Exhaustive over [OwnerWorkStatus] on purpose: no `else` branch, so adding an owner
 * status makes this stop compiling rather than silently pick a neighbour.
 */
fun commandStatusFor(owner: OwnerWorkStatus): VanCommandStatus = when (owner) {
    OwnerWorkStatus.WAITING_ON_YOU -> VanCommandStatus.APPROVAL_REQUIRED
    OwnerWorkStatus.WORKING -> VanCommandStatus.ACCEPTED
    OwnerWorkStatus.WAITING_ON_SOMETHING_ELSE -> VanCommandStatus.IN_FLIGHT
    OwnerWorkStatus.DONE -> VanCommandStatus.SUCCEEDED
    OwnerWorkStatus.DONE_WITH_GAPS -> VanCommandStatus.PARTIALLY_SUCCEEDED
    OwnerWorkStatus.COULD_NOT_VERIFY -> VanCommandStatus.COULD_NOT_VERIFY
    OwnerWorkStatus.FAILED -> VanCommandStatus.FAILED
    OwnerWorkStatus.STOPPED -> VanCommandStatus.CANCELLED
    // P0-EXEC-002 — EXPIRED already existed here and nothing ever produced it, because
    // nothing ever noticed a dispatch that never came back. It does now.
    OwnerWorkStatus.NEVER_HEARD_BACK -> VanCommandStatus.EXPIRED
    OwnerWorkStatus.REFUSED -> VanCommandStatus.REFUSED
    OwnerWorkStatus.UNKNOWN -> VanCommandStatus.UNKNOWN
}
