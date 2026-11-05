package com.dial.van.overlay

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.LayoutCoordinates
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.platform.LocalView
import com.dial.van.visual.VanLiveVisualState
import com.dial.van.visual.VanPointerGaze

/** Resolves each materialized gesture node's coordinates before moving its native window. */
@OptIn(ExperimentalFoundationApi::class)
internal fun Modifier.vanGestures(
    interaction: OverlayWindowInteraction,
    onTap: () -> Unit,
    onDoubleTap: () -> Unit,
    onLongPress: () -> Unit,
    clicks: Boolean = true,
): Modifier = composed {
    val view = LocalView.current
    // Each materialized gesture owns its coordinates, including AnimatedContent nodes.
    var coordinates by remember(view) { mutableStateOf<LayoutCoordinates?>(null) }
    val screenLocation = remember(view) { IntArray(2) }
    val windowLocation = remember(view) { IntArray(2) }

    fun screenPoint(localPosition: Offset): OverlayPoint? {
        val node = coordinates ?: return null
        if (!node.isAttached || !view.isAttachedToWindow ||
            !localPosition.x.isFinite() || !localPosition.y.isFinite()) return null
        return runCatching {
            // Resolve the nested gesture node before composing the View's actual origins.
            val inWindow = node.localToWindow(localPosition)
            view.getLocationOnScreen(screenLocation)
            view.getLocationInWindow(windowLocation)
            VanOverlayController.windowPointToScreen(
                OverlayPoint(inWindow.x.toDouble(), inWindow.y.toDouble()),
                OverlayPoint(screenLocation[0].toDouble(), screenLocation[1].toDouble()),
                OverlayPoint(windowLocation[0].toDouble(), windowLocation[1].toDouble()),
            )
        }.getOrNull()
    }

    fun attendTo(localPosition: Offset) {
        val bounds = coordinates?.takeIf { it.isAttached }?.size ?: return
        VanPointerGaze.fromLocal(
            localPosition.x, localPosition.y, bounds.width.toFloat(), bounds.height.toFloat(),
        )?.let { (x, y) -> VanLiveVisualState.attention(x, y) }
    }

    this
        .onGloballyPositioned { coordinates = it }
        .pointerInput(view) {
            detectDragGestures(
                onDragStart = { position ->
                    interaction.captureDragPointer(screenPoint(position))
                    if (clicks) attendTo(position)
                    interaction.beginDrag()
                },
                onDrag = { change, amount ->
                    // Real owner touch in VAN's own node; never infer cross-app focus.
                    interaction.captureDragPointer(screenPoint(change.position))
                    if (clicks) attendTo(change.position)
                    change.consume()
                    interaction.dragBy(amount.x, amount.y)
                },
                onDragEnd = {
                    if (coordinates?.isAttached != true || !view.isAttachedToWindow) {
                        interaction.captureDragPointer(null)
                    }
                    interaction.finishDrag()
                    VanLiveVisualState.attention(0f, 0f)
                },
                onDragCancel = {
                    interaction.cancelDrag()
                    VanLiveVisualState.attention(0f, 0f)
                },
            )
        }
        .then(if (clicks) Modifier.combinedClickable(
            onClick = { onTap() },
            onDoubleClick = { onDoubleTap() },
            onLongClick = { onLongPress() },
        ) else Modifier)
}
