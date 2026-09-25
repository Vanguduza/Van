package com.dial.van.command.nav

/**
 * The Command Centre's typed destinations (DNA §4), and everything about them that does not
 * need Compose to decide: which route a saved/restored id resolves to, which route is a
 * child of which, which routes sit on the primary bar versus behind "More", and how a
 * `van://` deep link becomes a concrete route.
 *
 * Pure Kotlin — no Android, no Compose — so process-death restoration and deep-link parsing
 * are executed in `android/verification` rather than only exercised by hand on a device.
 * `com.dial.van.command.CommandCentreActivity`'s `NavHost` is the one place a [VanRoute]
 * becomes pixels; this file only decides *which* route.
 *
 * Replaces `CommandNav`/`CommandModule`: DNA §4 names eight top-level destinations (plus
 * Work's browser/automation and mission children) rather than the flat seventeen-module grid
 * those two files enumerated.
 */
object VanRoute {

    // ---- Route templates -------------------------------------------------------------
    // A "template" is the string passed to `NavHost`'s `composable(route = ...)` — it may
    // contain `{argName}` placeholders. A "concrete" route is one with every placeholder
    // filled in, ready to pass to `NavController.navigate(...)`.

    const val HOME = "home"
    const val ATTENTION = "attention"
    const val WORK = "work"
    const val WORK_ACTIVITY = "work/activity"
    const val WORK_ARTEMIS = "work/artemis"
    const val WORK_BROWSER = "work/browser"
    const val WORK_BROWSER_TASKS = "work/browser/tasks"
    const val WORK_BROWSER_ESCALATIONS = "work/browser/escalations"
    const val WORK_BROWSER_SESSIONS = "work/browser/sessions"
    const val WORK_BROWSER_POLICY = "work/browser/policy"
    const val WORK_MISSION_TEMPLATE = "work/missions/{missionId}"
    const val TRADING = "trading"
    const val MEMORY = "memory"
    const val PROJECTS = "projects"
    const val PROJECT_DETAIL_TEMPLATE = "projects/{projectId}"
    const val CONNECTED = "connected"
    const val SETTINGS = "settings"
    const val JEV = "jev"
    /**
     * Full-screen children of Settings for the two legacy bodies this rebuild reuses rather
     * than duplicates (`SpeechModule`, `NotificationPolicyModule`) — both are themselves a
     * `LazyColumn { fillMaxSize() }`, which cannot be embedded as an item inside Settings'
     * own list, so they get their own destination instead of a nested panel.
     */
    const val SETTINGS_VOICE = "settings/voice"
    const val SETTINGS_NOTIFICATIONS = "settings/notifications"

    fun missionRoute(missionId: String): String = "work/missions/${encode(missionId)}"
    fun projectRoute(projectId: String): String = "projects/${encode(projectId)}"

    /** Every template this app's `NavHost` declares a `composable` for. */
    val ALL_TEMPLATES: List<String> = listOf(
        HOME, ATTENTION, WORK, WORK_ACTIVITY, WORK_ARTEMIS, WORK_BROWSER, WORK_BROWSER_TASKS, WORK_BROWSER_ESCALATIONS,
        WORK_BROWSER_SESSIONS, WORK_BROWSER_POLICY, WORK_MISSION_TEMPLATE, TRADING, MEMORY,
        PROJECTS, PROJECT_DETAIL_TEMPLATE, CONNECTED, SETTINGS, JEV,
        SETTINGS_VOICE, SETTINGS_NOTIFICATIONS,
    )

    /**
     * Adaptive nav (DNA §4): the five primaries on the bottom bar at [com.dial.van.design.VanDensity.Regular]
     * or the side rail at [com.dial.van.design.VanDensity.Wide].
     */
    val PRIMARY: List<String> = listOf(HOME, ATTENTION, WORK, TRADING, MEMORY)

    /** Everything else, reached through the "More" sheet. */
    val MORE: List<String> = listOf(PROJECTS, CONNECTED, SETTINGS, JEV)

    /** Child route template → its parent template, for "up"/back-to-parent affordances. */
    val PARENTS: Map<String, String> = mapOf(
        ATTENTION to HOME,
        WORK to HOME,
        WORK_ACTIVITY to WORK,
        WORK_ARTEMIS to WORK,
        WORK_BROWSER to WORK,
        WORK_BROWSER_TASKS to WORK_BROWSER,
        WORK_BROWSER_ESCALATIONS to WORK_BROWSER,
        WORK_BROWSER_SESSIONS to WORK_BROWSER,
        WORK_BROWSER_POLICY to WORK_BROWSER,
        WORK_MISSION_TEMPLATE to WORK,
        TRADING to HOME,
        MEMORY to HOME,
        PROJECTS to HOME,
        PROJECT_DETAIL_TEMPLATE to PROJECTS,
        CONNECTED to HOME,
        SETTINGS to HOME,
        JEV to HOME,
        SETTINGS_VOICE to SETTINGS,
        SETTINGS_NOTIFICATIONS to SETTINGS,
    )

    /** The template a concrete route matches, or null when nothing in [ALL_TEMPLATES] fits. */
    fun templateFor(concreteRoute: String): String? {
        val segments = concreteRoute.substringBefore('?').split('/').filter { it.isNotEmpty() }
        return ALL_TEMPLATES.firstOrNull { matches(it, segments) }
    }

    /** Whether [concreteRoute] resolves to a known destination. */
    fun isKnown(concreteRoute: String): Boolean = templateFor(concreteRoute) != null

    /** The parent of whatever [concreteRoute] resolves to, or null at the root (Home). */
    fun parentOf(concreteRoute: String): String? {
        val template = templateFor(concreteRoute) ?: return null
        return PARENTS[template]
    }

    private fun matches(template: String, segments: List<String>): Boolean {
        val templateSegments = template.split('/')
        if (templateSegments.size != segments.size) return false
        return templateSegments.zip(segments).all { (t, s) ->
            (t.startsWith('{') && t.endsWith('}') && s.isNotBlank()) || t == s
        }
    }

    private fun encode(value: String): String =
        value.replace("/", "%2F")

    // ---- Process-death restoration ------------------------------------------------------

    /**
     * P3-AND-007's rule, restated for the new nav graph: what comes back after Android
     * reclaims the process is a route id, never an ordinal, and an id this build does not
     * recognise (an older/newer app version's route) falls back to [HOME] rather than
     * crashing the `NavHost` on an unregistered destination.
     */
    fun restore(savedRoute: String?): String =
        savedRoute?.takeIf { isKnown(it) } ?: HOME

    // ---- Deep links (`van://<route>`) ----------------------------------------------------

    const val DEEP_LINK_SCHEME = "van"

    /**
     * Parses a `van://home`, `van://projects/proj-123`, `van://work/missions/m1` style URI
     * into a concrete route this app's `NavHost` can navigate to, or null when the URI is not
     * one of ours or names an unknown destination.
     */
    fun parseDeepLink(uri: String): String? {
        val body = when {
            uri.startsWith("$DEEP_LINK_SCHEME://") -> uri.removePrefix("$DEEP_LINK_SCHEME://")
            else -> return null
        }
        val withoutQuery = body.substringBefore('?').substringBefore('#').trim('/')
        if (withoutQuery.isEmpty()) return HOME
        return if (isKnown(withoutQuery)) withoutQuery else null
    }

    /** The `van://…` form of a concrete route, for sharing/notification deep links. */
    fun toDeepLink(concreteRoute: String): String = "$DEEP_LINK_SCHEME://$concreteRoute"
}
