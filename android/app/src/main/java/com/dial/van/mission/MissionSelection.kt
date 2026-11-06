package com.dial.van.mission

/** The named mission stays visible even after it leaves the running/waiting lists. */
data class MissionPresentation(
    val requested: MissionSummary?,
    val running: List<MissionSummary>,
    val waiting: List<MissionSummary>,
)

object MissionSelection {
    fun present(
        requestedId: String?,
        running: List<MissionSummary>,
        waiting: List<MissionSummary>,
        fetched: MissionSummary? = null,
    ): MissionPresentation {
        val requested = requestedId?.takeIf { it.isNotBlank() }?.let { id ->
            (running + waiting).firstOrNull { it.missionId == id }
                ?: fetched?.takeIf { it.missionId == id }
        }
        return MissionPresentation(
            requested = requested,
            running = running.filterNot { it.missionId == requested?.missionId },
            waiting = waiting.filterNot { it.missionId == requested?.missionId },
        )
    }
}
