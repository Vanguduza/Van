package com.dial.van.visual

import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min

/** Coordinates from one explicitly owned VAN window, never external-app inspection. */
data class VanOwnedRect(val left: Float, val top: Float, val right: Float, val bottom: Float) {
    val width: Float get() = right - left
    val height: Float get() = bottom - top
    val centerX: Float get() = left + width / 2f
    val centerY: Float get() = top + height / 2f
    fun valid(): Boolean = listOf(left, top, right, bottom).all { it.isFinite() } && width > 0f && height > 0f
    fun clippedTo(other: VanOwnedRect): VanOwnedRect? = VanOwnedRect(
        max(left, other.left), max(top, other.top), min(right, other.right), min(bottom, other.bottom),
    ).takeIf { valid() && other.valid() && it.valid() }
}

data class VanOwnedLayout(
    val windowId: String,
    val bounds: VanOwnedRect,
    val viewport: VanOwnedRect,
    val visible: Boolean,
)

data class VanResolvedUiTarget(
    val id: String,
    val lease: Long,
    val revision: Long,
    val directionX: Float,
    val directionY: Float,
    val cueTarget: VanCueTarget,
)

/**
 * Main-thread caller supplies fresh, monotonic layout snapshots. A stale instance
 * cannot unregister its replacement; resize/scroll updates are revisioned, not
 * queued as old animation events. No API in this class clicks or executes a target.
 */
class VanUiTargetRegistry(private val capacity: Int = 64, private val maxAgeMs: Long = 1_500L) {
    private data class Entry(val id: String, val lease: Long, val revision: Long, val layout: VanOwnedLayout, val atMs: Long)
    private val targets = LinkedHashMap<String, Entry>()
    private var anchor: Entry? = null
    private var generation = 0L

    init { require(capacity in 1..256); require(maxAgeMs in 1..10_000) }

    fun observeTarget(id: String, lease: Long, layout: VanOwnedLayout, nowMs: Long) {
        if (id.isBlank() || id.length > 180 || lease < 1 || nowMs < 0) return
        val old = targets[id]
        if (old != null && old.lease > lease) return
        val revision = if (old?.lease == lease && old.layout == layout) old.revision else ++generation
        targets.remove(id)
        targets[id] = Entry(id, lease, revision, layout, nowMs)
        while (targets.size > capacity) targets.remove(targets.keys.first())
    }

    fun observeAvatar(lease: Long, layout: VanOwnedLayout, nowMs: Long) {
        if (lease < 1 || nowMs < 0 || (anchor != null && requireNotNull(anchor).lease > lease)) return
        val old = anchor
        anchor = Entry("avatar", lease, if (old?.lease == lease && old.layout == layout) old.revision else ++generation, layout, nowMs)
    }

    fun removeTarget(id: String, lease: Long) { if (targets[id]?.lease == lease) targets.remove(id) }
    fun removeAvatar(lease: Long) { if (anchor?.lease == lease) anchor = null }
    fun clear() { targets.clear(); anchor = null; generation++ }
    fun count(): Int = targets.size

    fun resolve(id: String, nowMs: Long): VanResolvedUiTarget? {
        val target = targets[id] ?: return null
        val avatar = anchor ?: return null
        if (!fresh(target, nowMs) || !fresh(avatar, nowMs)) return null
        val t = target.layout; val a = avatar.layout
        if (!t.visible || !a.visible || t.windowId.isBlank() || t.windowId != a.windowId) return null
        if (t.viewport != a.viewport || !a.bounds.valid() || !a.viewport.valid()) return null
        val box = t.bounds.clippedTo(t.viewport) ?: return null
        if (box.width * box.height < t.bounds.width * t.bounds.height * 0.5f) return null
        // Fit.CONTAIN maps the canonical 593px artboard to the square inside the
        // actual renderer view. Shoulder coordinates are the refined R5 rest pose.
        val side = min(a.bounds.width, a.bounds.height)
        val originX = a.bounds.left + (a.bounds.width - side) / 2f
        val originY = a.bounds.top + (a.bounds.height - side) / 2f
        val shoulderX = originX + side * (355.4957f / 593f)
        val shoulderY = originY + side * (253.5234f / 593f)
        val dx = box.centerX - shoulderX; val dy = box.centerY - shoulderY
        val distance = hypot(dx, dy)
        if (!distance.isFinite() || distance < 1f) return null
        val revision = max(target.revision, avatar.revision)
        return VanResolvedUiTarget(id, target.lease, revision, dx / distance, dy / distance,
            VanCueTarget(box.left - t.viewport.left, box.top - t.viewport.top,
                box.right - t.viewport.left, box.bottom - t.viewport.top,
                t.viewport.width, t.viewport.height, revision, revision, true))
    }

    private fun fresh(entry: Entry, now: Long): Boolean = now >= entry.atMs && now - entry.atMs <= maxAgeMs
}
