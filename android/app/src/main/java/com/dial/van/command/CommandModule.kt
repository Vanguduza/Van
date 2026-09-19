package com.dial.van.command


/**
 * The Command Centre's navigation surface.
 *
 * P3-AND-009 — every screen named here used to live in one 1,342-line
 * `CommandCentreActivity.kt`, alongside the Activity, the navigation, fourteen module
 * bodies and the shared components. A file that size is not reviewable, and that is not a
 * tidiness complaint: the status projection P0-EXEC-003 found painting unverified outcomes
 * in the working colour sat at line 1,310 of it.
 */

internal enum class CommandModule(val id: String, val title: String) {
    OVERVIEW("overview", "Home"),
    CHAT("chat", "Chat"),
    DECISIONS("decisions", "Decisions"),
    // P2-AND-015 — the mission surfaces §§33, 35 and 48 describe, which were
    // rendered nowhere: MissionRepository was constructed by no production file.
    MISSIONS("missions", "Work"),
    TASKS("tasks", "Tasks"),
    PROJECTS("projects", "Projects"),
    ACTIVITY("activity", "Activity"),
    BROWSER_AUTOMATION("browser_automation", "Browser & Automation"),
    BROWSER_TASKS("browser_tasks", "Browser Tasks"),
    BROWSER_ESCALATIONS("browser_escalations", "Browser Escalations"),
    BROWSER_SESSIONS("browser_sessions", "Browser Sessions"),
    BROWSER_POLICY("browser_policy", "Browser Policy"),
    SYSTEMS("systems", "Systems"),
    CONNECTIONS("connections", "Connections"),
    // P2-AND-017 — setPolicy and setQuietHours had no caller, so VAN held a
    // notification-listener grant with no owner control over it.
    NOTIFICATIONS("notifications", "Notifications"),
    // P2-AND-018 — recordCorrection and pinTerm had no caller, so the personal
    // speech model was read on every turn and could never learn a word.
    SPEECH("speech", "Speech"),
    SETTINGS("settings", "Settings"),
    ;

    companion object {
        fun fromId(id: String?): CommandModule = entries.firstOrNull { it.id == id } ?: OVERVIEW
    }
}
