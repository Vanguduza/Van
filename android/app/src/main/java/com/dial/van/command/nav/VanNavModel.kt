package com.dial.van.command.nav

/**
 * The pure half of the Command Centre's one `NavHost` (DNA §4). Replaces `CommandNav`.
 *
 * [VanRoute] is the registry (templates, parents, primaries, deep links); this is the model
 * built on top of it — legacy-intent compatibility (the overlay/notification/onboarding
 * callers that still start `CommandCentreActivity` with an old `CommandModule` id in the
 * `"module"` extra) and the "one level, not a history" back-to-parent rule `CommandNav.back`
 * used to provide, now expressed against [VanRoute.PARENTS].
 */
object VanNavModel {

    /**
     * `CommandModule.id` → the new route it maps onto, for the handful of external callers
     * (the overlay's double-tap/notification-tap intents, none of which currently pass a
     * value) that may still carry an old module id in the `"module"` extra after this
     * rebuild ships. Unknown/blank ids resolve to Home, same as [VanRoute.restore].
     */
    private val LEGACY_MODULE_TO_ROUTE: Map<String, String> = mapOf(
        "overview" to VanRoute.HOME,
        "chat" to VanRoute.WORK,
        "tasks" to VanRoute.WORK,
        "missions" to VanRoute.WORK,
        "activity" to VanRoute.WORK,
        "decisions" to VanRoute.ATTENTION,
        "projects" to VanRoute.PROJECTS,
        "browser_automation" to VanRoute.WORK_BROWSER,
        "browser_tasks" to VanRoute.WORK_BROWSER_TASKS,
        "browser_escalations" to VanRoute.WORK_BROWSER_ESCALATIONS,
        "browser_sessions" to VanRoute.WORK_BROWSER_SESSIONS,
        "browser_policy" to VanRoute.WORK_BROWSER_POLICY,
        "systems" to VanRoute.CONNECTED,
        "connections" to VanRoute.CONNECTED,
        "notifications" to VanRoute.SETTINGS,
        "speech" to VanRoute.SETTINGS,
        "settings" to VanRoute.SETTINGS,
    )

    /**
     * What `CommandCentreActivity.onCreate`'s launch intent resolves to. `extraModule` is
     * whatever the intent's `"module"` string extra held — a new route id (this build's own
     * deep links), an old `CommandModule` id (an external caller built before this rebuild),
     * or null/blank (a plain launch). A value that is neither known form falls back to Home,
     * never to a crash on an unregistered `NavHost` destination.
     */
    fun startDestination(extraModule: String?): String {
        val value = extraModule?.trim().orEmpty()
        if (value.isEmpty()) return VanRoute.HOME
        if (VanRoute.isKnown(value)) return value
        return LEGACY_MODULE_TO_ROUTE[value] ?: VanRoute.HOME
    }

    /** Process-death restoration (P3-AND-007): the saved route id, or Home if unrecognised. */
    fun restore(savedRoute: String?): String = VanRoute.restore(savedRoute)

    /** What a `van://…` link resolves to, or null when it is not one of ours. */
    fun deepLink(uri: String): String? = VanRoute.parseDeepLink(uri)

    /**
     * One level, not a history (the rule `CommandNav.back` stated): where the system back
     * button/gesture goes from [currentRoute], or null when it should leave the app (only
     * true at [VanRoute.HOME], the graph's root).
     */
    fun back(currentRoute: String): String? = VanRoute.parentOf(currentRoute)

    /** Whether [currentRoute] is one of the five adaptive-nav primaries (DNA §4). */
    fun isPrimary(currentRoute: String): Boolean =
        VanRoute.templateFor(currentRoute) in VanRoute.PRIMARY
}
