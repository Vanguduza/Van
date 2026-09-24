package com.dial.van.dialdev

import com.dial.van.design.StatusSemantics

/**
 * The smaller DIAL vocabularies a development screen shows — subsystem health, the capability
 * ladder (§6.11), finding severity, evidence admission, check results — each an enum with an
 * exhaustive, `else`-free role mapping. A value this build does not know parses to null and is
 * shown as its own raw text in the `disabled` role ([roleOrDisabled]); it is never folded into
 * a familiar-looking neighbour.
 */
enum class DialDevHealth { HEALTHY, DEGRADED, UNAVAILABLE, UNKNOWN;
    companion object {
        fun parse(raw: String?): DialDevHealth? = when (raw?.trim()?.uppercase()) {
            "HEALTHY", "OK", "UP", "LIVE", "READY", "GREEN" -> HEALTHY
            "DEGRADED", "PARTIAL", "WARN", "WARNING", "AMBER" -> DEGRADED
            "UNAVAILABLE", "DOWN", "FAILED", "ERROR", "RED", "UNREACHABLE" -> UNAVAILABLE
            "UNKNOWN", "UNVERIFIED" -> UNKNOWN
            else -> null
        }
    }
}

/** §6.11 capability ladder, in order. */
enum class DialDevLadder { INSTALLED, AUTHENTICATED, LIVE_QUALIFIED, ORCHESTRATED, INTEGRATED;
    companion object {
        fun parse(raw: String?): DialDevLadder? = entries.firstOrNull { it.name == raw?.trim()?.uppercase() }
    }
}

enum class DialDevSeverity { CRITICAL, HIGH, MEDIUM, LOW, INFO;
    companion object {
        fun parse(raw: String?): DialDevSeverity? = entries.firstOrNull { it.name == raw?.trim()?.uppercase() }
    }
}

/** Evidence admission (§6.10): only ADMITTED evidence counts toward a gate. */
enum class DialDevAdmission { ADMITTED, CANDIDATE, REJECTED, SUPERSEDED;
    companion object {
        fun parse(raw: String?): DialDevAdmission? = entries.firstOrNull { it.name == raw?.trim()?.uppercase() }
    }
}

/** A check / CI / test result. */
enum class DialDevResult { PASS, FAIL, RUNNING, PENDING, SKIPPED, ERROR;
    companion object {
        fun parse(raw: String?): DialDevResult? = when (raw?.trim()?.uppercase()) {
            "PASS", "PASSED", "SUCCESS", "GREEN" -> PASS
            "FAIL", "FAILED", "FAILURE", "RED" -> FAIL
            "RUNNING", "IN_PROGRESS" -> RUNNING
            "PENDING", "QUEUED", "WAITING" -> PENDING
            "SKIPPED", "NOT_RUN" -> SKIPPED
            "ERROR", "ERRORED" -> ERROR
            else -> null
        }
    }
}

/** Rev 1 §09.12 progress events, as the task timeline shows them. */
enum class DialDevProgressEvent {
    CONTEXT_LOADED, WORKTREE_READY, INSPECTION_COMPLETE, IMPLEMENTATION_STARTED, TESTING_STARTED,
    BLOCKED, CHECKPOINT_CREATED, REVIEW_REQUESTED, COMPLETION_CANDIDATE;
    companion object {
        fun parse(raw: String?): DialDevProgressEvent? = entries.firstOrNull { it.name == raw?.trim()?.uppercase() }
    }
}

object DialDevRoles {
    /** A completion candidate is `cognition` (claimed, not admitted) — never `favourable`. */
    fun progress(event: DialDevProgressEvent): String = when (event) {
        DialDevProgressEvent.CONTEXT_LOADED,
        DialDevProgressEvent.WORKTREE_READY,
        DialDevProgressEvent.INSPECTION_COMPLETE,
        -> StatusSemantics.ROLE_MONITOR
        DialDevProgressEvent.IMPLEMENTATION_STARTED -> StatusSemantics.ROLE_ENGAGED
        DialDevProgressEvent.TESTING_STARTED,
        DialDevProgressEvent.REVIEW_REQUESTED,
        DialDevProgressEvent.COMPLETION_CANDIDATE,
        -> StatusSemantics.ROLE_COGNITION
        DialDevProgressEvent.BLOCKED -> StatusSemantics.ROLE_DETERIORATING
        DialDevProgressEvent.CHECKPOINT_CREATED -> StatusSemantics.ROLE_ENGAGED
    }

    fun health(value: DialDevHealth): String = when (value) {
        DialDevHealth.HEALTHY -> StatusSemantics.ROLE_FAVOURABLE
        DialDevHealth.DEGRADED -> StatusSemantics.ROLE_EVENT_RISK
        DialDevHealth.UNAVAILABLE -> StatusSemantics.ROLE_CRITICAL
        DialDevHealth.UNKNOWN -> StatusSemantics.ROLE_DISABLED
    }

    /** Lower rungs are real but partial; only INTEGRATED reads favourable. */
    fun ladder(value: DialDevLadder): String = when (value) {
        DialDevLadder.INSTALLED -> StatusSemantics.ROLE_HYPOTHESIS
        DialDevLadder.AUTHENTICATED -> StatusSemantics.ROLE_MONITOR
        DialDevLadder.LIVE_QUALIFIED -> StatusSemantics.ROLE_COGNITION
        DialDevLadder.ORCHESTRATED -> StatusSemantics.ROLE_ENGAGED
        DialDevLadder.INTEGRATED -> StatusSemantics.ROLE_FAVOURABLE
    }

    fun severity(value: DialDevSeverity): String = when (value) {
        DialDevSeverity.CRITICAL -> StatusSemantics.ROLE_CRITICAL
        DialDevSeverity.HIGH -> StatusSemantics.ROLE_DETERIORATING
        DialDevSeverity.MEDIUM -> StatusSemantics.ROLE_EVENT_RISK
        DialDevSeverity.LOW -> StatusSemantics.ROLE_MONITOR
        DialDevSeverity.INFO -> StatusSemantics.ROLE_DISABLED
    }

    /** A candidate is not evidence yet: `cognition`, never `favourable`. */
    fun admission(value: DialDevAdmission): String = when (value) {
        DialDevAdmission.ADMITTED -> StatusSemantics.ROLE_FAVOURABLE
        DialDevAdmission.CANDIDATE -> StatusSemantics.ROLE_COGNITION
        DialDevAdmission.REJECTED -> StatusSemantics.ROLE_CRITICAL
        DialDevAdmission.SUPERSEDED -> StatusSemantics.ROLE_DISABLED
    }

    fun result(value: DialDevResult): String = when (value) {
        DialDevResult.PASS -> StatusSemantics.ROLE_FAVOURABLE
        DialDevResult.FAIL -> StatusSemantics.ROLE_CRITICAL
        DialDevResult.RUNNING -> StatusSemantics.ROLE_ENGAGED
        DialDevResult.PENDING -> StatusSemantics.ROLE_MONITOR
        DialDevResult.SKIPPED -> StatusSemantics.ROLE_DISABLED
        DialDevResult.ERROR -> StatusSemantics.ROLE_DETERIORATING
    }

    /** Parse-and-map, with an unknown value shown in the `disabled` role rather than guessed. */
    fun <E> roleOrDisabled(parsed: E?, map: (E) -> String): String =
        parsed?.let(map) ?: StatusSemantics.ROLE_DISABLED

    /**
     * A state word from a list whose vocabulary DIAL does not pin (a research job, a manager
     * slot's qualification, a memory candidate): tried against each known vocabulary in turn —
     * task state, check result, admission, health — and `disabled` when none knows it.
     */
    fun forAnyState(raw: String?): String {
        DialDevState.parse(raw)?.let { return DialDevSemantics.present(it).role }
        DialDevResult.parse(raw)?.let { return result(it) }
        DialDevAdmission.parse(raw)?.let { return admission(it) }
        DialDevLadder.parse(raw)?.let { return ladder(it) }
        return roleOrDisabled(DialDevHealth.parse(raw), ::health)
    }

    /** The label a chip shows: the raw word DIAL sent, or "UNKNOWN" when it sent none. */
    fun chipLabel(raw: String?): String = raw?.trim()?.takeIf { it.isNotEmpty() }?.uppercase()?.replace('_', ' ') ?: "UNKNOWN"
}
