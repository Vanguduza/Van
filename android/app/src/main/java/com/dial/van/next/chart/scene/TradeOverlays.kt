package com.dial.van.next.chart.scene

/**
 * What the chart knows about the owner's trades. Two kinds, never mixed (§7.8.6, REA-VAN-006):
 *
 * - [PositionOverlay] / [OrderOverlay] come from the broker reconciler and are drawn as
 *   fact. A stop is drawn as confirmed only if the broker confirmed it.
 * - [DraftOverlay] is what the owner is dragging. It is drawn in the draft style, carries
 *   no authority, and turns into a trade only through the §7.4 review and approval flow.
 */
enum class Side { LONG, SHORT }

data class PositionOverlay(
    val positionId: String,
    val side: Side,
    val entry: Double,
    val stop: Double?,
    val stopConfirmed: Boolean,
    val target: Double?,
    val label: String,
)

enum class OrderState { REQUESTED, WORKING, PARTIAL, FILLED, REJECTED, CANCELLED, EXPIRED, OUTCOME_UNKNOWN }

data class OrderOverlay(val orderId: String, val side: Side, val price: Double, val state: OrderState, val label: String) {
    /** Only orders still resting at the broker are drawn as lines. */
    val drawn: Boolean get() = state == OrderState.WORKING || state == OrderState.PARTIAL || state == OrderState.REQUESTED
}

data class DraftOverlay(val draftId: String, val side: Side, val entry: Double?, val stop: Double?, val target: Double?)

data class TradeOverlays(
    val positions: List<PositionOverlay> = emptyList(),
    val orders: List<OrderOverlay> = emptyList(),
    val draft: DraftOverlay? = null,
)
