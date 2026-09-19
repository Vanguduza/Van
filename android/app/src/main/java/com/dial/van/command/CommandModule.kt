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
    SETTINGS("settings", "Settings"),
    ;

    companion object {
        fun fromId(id: String?): CommandModule = entries.firstOrNull { it.id == id } ?: OVERVIEW
    }
}
