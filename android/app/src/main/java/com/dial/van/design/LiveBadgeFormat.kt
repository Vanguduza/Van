package com.dial.van.design

/**
 * DNA §3: `LiveBadge`'s `"STALE hh:mm"` reading. Split out of
 * `com.dial.van.design.components.LiveBadge` (which has the Compose imports a
 * `@Composable` needs) so this one line of arithmetic is pure Kotlin and runs in
 * `android/verification` — the same reasoning every other file in this package follows.
 */
object LiveBadgeFormat {
    /** `ageMs` → `"hh:mm"`, floored — an age of exactly one hour reads `01:00`, not `00:60`. */
    fun hhmm(ageMs: Long): String {
        val totalMinutes = ageMs.coerceAtLeast(0L) / 60_000L
        val hours = totalMinutes / 60L
        val minutes = totalMinutes % 60L
        return "%02d:%02d".format(hours, minutes)
    }
}
