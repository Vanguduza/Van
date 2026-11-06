package com.dial.van.overlay

import android.view.WindowManager
import kotlin.math.min

/** Measured native-window binding for the pure available-space workboard policy. */
internal class OverlayWorkboardWindow(
    private val host: OverlayInteractionHost,
    private val screen: () -> OverlayScreen,
    private val measured: () -> OverlaySize,
    private val dp: (Int) -> Int,
) {
    private val session = WorkboardPlacementSession()

    fun prepare(previous: VanOverlayPresentation, next: VanOverlayPresentation) {
        val params = host.params ?: return
        val opening = WorkboardPlacement.isBoard(next)
        if (opening) {
            if (!WorkboardPlacement.isBoard(previous)) session.opened(
                OverlayPlacement(params.x, params.y), measured(),
            )
            apply(next, update = false)
        } else {
            val rest = session.close()
            params.width = WindowManager.LayoutParams.WRAP_CONTENT
            params.height = WindowManager.LayoutParams.WRAP_CONTENT
            host.boardSizeChanged(null)
            if (rest != null) {
                val size = VanOverlayController.fallbackSizeFor(next, dp, screen())
                val at = VanOverlayController.clamp(rest.x, rest.y, size.widthPx, size.heightPx, screen())
                params.x = at.x; params.y = at.y
            }
        }
    }

    fun reconcile(): Boolean {
        if (!WorkboardPlacement.isBoard(host.uiState.presentation)) return false
        val p = host.params ?: return true
        session.opened(OverlayPlacement(p.x, p.y), measured())
        apply(host.uiState.presentation, update = true)
        return true
    }

    fun dragged() {
        if (WorkboardPlacement.isBoard(host.uiState.presentation)) host.params?.let {
            session.moved(OverlayPlacement(it.x, it.y))
        }
    }

    private fun apply(presentation: VanOverlayPresentation, update: Boolean) {
        val params = host.params ?: return
        val bounds = screen()
        val fontScale = host.context.resources.configuration.fontScale.coerceIn(1f, 1.6f)
        val base = VanOverlayController.fallbackSizeFor(presentation, dp, bounds)
        val desired = if (presentation == VanOverlayPresentation.WORKBOARD_MAXIMIZED) base
            else OverlaySize(base.widthPx, (base.heightPx * fontScale).toInt())
        val anchor = session.anchor ?: OverlayRect(params.x.toDouble(), params.y.toDouble(),
            params.x + measured().widthPx.toDouble(), params.y + measured().heightPx.toDouble())
        val ime = host.keyboardTopPx.takeIf { host.visibility.keyboardVisible && it != Int.MAX_VALUE }
        val layout = WorkboardPlacement.plan(bounds, anchor, desired,
            minimum = OverlaySize(min(dp(240), desired.widthPx), min(dp(200), desired.heightPx)),
            keyboardTopPx = ime, gapPx = dp(8), marginPx = dp(8),
            preferredManualPosition = session.manualPosition)
        val changed = params.x != layout.position.x || params.y != layout.position.y ||
            params.width != layout.size.widthPx || params.height != layout.size.heightPx
        params.x = layout.position.x; params.y = layout.position.y
        params.width = layout.size.widthPx; params.height = layout.size.heightPx
        host.boardSizeChanged(layout.size)
        if (update && changed && host.updateWindow()) host.persistState()
    }
}
