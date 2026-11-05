package com.dial.van.visual

import com.dial.van.command.nav.VanRoute

/** Classification is limited to the application's canonical registered navigation tree. */
enum class VanOwnedScreen { HOME, WORK, PROJECTS, TASKS, DECISIONS, TRADING, MEMORY, RESEARCH, BROWSER,
    DEVICE_CONTROL, ASSETS, AGENTS, WORKSPACES, DESIGN, BUILD, SECURITY, REVIEW, CONNECTIONS, SETTINGS }

object VanOwnedScreenContext {
    fun classify(route: String): VanOwnedScreen? {
        val template = VanRoute.templateFor(route) ?: return null
        return when (template) {
            VanRoute.HOME -> VanOwnedScreen.HOME
            VanRoute.ATTENTION, VanRoute.REMINDERS -> VanOwnedScreen.DECISIONS
            VanRoute.TRADING -> VanOwnedScreen.TRADING
            VanRoute.MEMORY, VanRoute.UNDERSTANDING, VanRoute.ADAPTATIONS, VanRoute.GOALS, VanRoute.OWNER_KNOWLEDGE, VanRoute.WORK_DEV_MEMORY -> VanOwnedScreen.MEMORY
            VanRoute.PROJECTS, VanRoute.PROJECT_DETAIL_TEMPLATE, VanRoute.PROJECT_RATIONALE_TEMPLATE, VanRoute.WORK_DEV_PLAN, VanRoute.WORK_DEV_GRAPH -> VanOwnedScreen.PROJECTS
            VanRoute.WORK_ACTIVITY, VanRoute.WORK_MISSION_TEMPLATE, VanRoute.WORK_DEV_TASKS, VanRoute.WORK_DEV_TASK -> VanOwnedScreen.TASKS
            VanRoute.WORK_BROWSER, VanRoute.WORK_BROWSER_TASKS, VanRoute.WORK_BROWSER_ESCALATIONS,
            VanRoute.WORK_BROWSER_SESSIONS, VanRoute.WORK_BROWSER_POLICY, VanRoute.OWNER_BROWSER_OUTCOME -> VanOwnedScreen.BROWSER
            VanRoute.OWNER_RESEARCH, VanRoute.WORK_DEV_RESEARCH -> VanOwnedScreen.RESEARCH
            VanRoute.WORK_ARTEMIS -> VanOwnedScreen.DEVICE_CONTROL
            VanRoute.WORK_ASSETS, VanRoute.WORK_DOCUMENT_TEMPLATE, VanRoute.WORK_THREAD_TEMPLATE, VanRoute.WORK_DEV_EVIDENCE -> VanOwnedScreen.ASSETS
            VanRoute.WORK_DEV_AGENTS -> VanOwnedScreen.AGENTS
            VanRoute.WORK_DEV_WORKSPACES, VanRoute.WORK_DEV_WORKSPACE -> VanOwnedScreen.WORKSPACES
            VanRoute.WORK_DEV_DESIGN -> VanOwnedScreen.DESIGN
            VanRoute.WORK_DEV_CI -> VanOwnedScreen.BUILD
            VanRoute.WORK_DEV_SECURITY, VanRoute.SETTINGS_PERMISSIONS -> VanOwnedScreen.SECURITY
            VanRoute.WORK_DEV_REVIEWS -> VanOwnedScreen.REVIEW
            VanRoute.CONNECTED, VanRoute.OWNER_DIAGNOSTICS -> VanOwnedScreen.CONNECTIONS
            VanRoute.SETTINGS, VanRoute.SETTINGS_JEV, VanRoute.SETTINGS_VOICE, VanRoute.SETTINGS_NOTIFICATIONS -> VanOwnedScreen.SETTINGS
            else -> VanOwnedScreen.WORK
        }
    }

    /** Both alternatives still require a measured visible VAN-owned target. */
    fun pointing(screen: VanOwnedScreen?): VanContextGesture = when (screen) {
        VanOwnedScreen.MEMORY, VanOwnedScreen.RESEARCH, VanOwnedScreen.ASSETS,
        VanOwnedScreen.DESIGN, VanOwnedScreen.REVIEW -> VanContextGesture.INSPECT_TARGET
        else -> VanContextGesture.GUIDE_NEXT_STEP
    }
}

/** Later screen instances cannot be cleared by stale disposal of an older one. */
class VanScreenLease {
    private var lease = 0L
    var screen: VanOwnedScreen? = null; private set
    fun observe(instance: Long, route: String) {
        if (instance < 1 || instance < lease) return
        lease = instance; screen = VanOwnedScreenContext.classify(route)
    }
    fun clear(instance: Long) { if (instance == lease) screen = null }
}

object VanContextEventPolicy {
    fun command(status: String): VanContextGesture? = when (status) {
        "denied", "rejected", "rejected_untrusted" -> VanContextGesture.POLITE_REFUSAL
        "failed", "error" -> VanContextGesture.ACKNOWLEDGE_ERROR
        else -> null
    }
    fun decision(open: Boolean, choices: Int, expired: Boolean): VanContextGesture? =
        if (!open || expired || choices !in 1..100) null
        else if (choices >= 2) VanContextGesture.COMPARE_OPTIONS else VanContextGesture.REQUEST_CLARIFICATION
    fun compare(choices: Int): VanContextGesture? = if (choices in 2..100) VanContextGesture.COMPARE_OPTIONS else null
    fun recovered(previous: VanHealthState?, current: VanHealthState): Boolean =
        previous != null && previous != VanHealthState.NOMINAL && current == VanHealthState.NOMINAL
}
