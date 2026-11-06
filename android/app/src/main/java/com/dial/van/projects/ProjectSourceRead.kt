package com.dial.van.projects

import kotlinx.coroutines.CancellationException

/** An unavailable source is never an empty collection or a successful negative fact. */
data class ProjectSourceRead<T>(val value: T? = null, val failure: String? = null) {
    val available: Boolean get() = failure == null && value != null
}

suspend fun <T> readProjectSource(call: suspend () -> T): ProjectSourceRead<T> = try {
    ProjectSourceRead(value = call())
} catch (cancelled: CancellationException) {
    throw cancelled
} catch (failure: Exception) {
    ProjectSourceRead(failure = failure.message ?: "This source could not be read.")
}

object ProjectSourcePresentation {
    /** Known blockers remain actionable even when another health signal is unavailable. */
    fun health(derived: ProjectHealth, truthAvailable: Boolean, missionsAvailable: Boolean,
        attentionAvailable: Boolean): ProjectHealth = when {
        derived == ProjectHealth.BLOCKED -> derived
        !truthAvailable || !missionsAvailable || !attentionAvailable -> ProjectHealth.UNKNOWN
        else -> derived
    }

    fun phase(derived: String, truthAvailable: Boolean, missionsAvailable: Boolean): String =
        if (truthAvailable && missionsAvailable) derived else "Phase could not be confirmed"
}
