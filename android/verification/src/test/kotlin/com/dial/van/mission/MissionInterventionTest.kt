package com.dial.van.mission

import kotlin.test.Test
import kotlin.test.assertFailsWith

class MissionInterventionTest {
    @Test fun `a matching cancelled receipt permits the cancellation acknowledgment`() {
        MissionIntervention.requireCancelled("mission-1", "mission-1", "CANCELLED")
    }

    @Test fun `a different mission or nonterminal state cannot acknowledge cancellation`() {
        assertFailsWith<IllegalStateException> { MissionIntervention.requireCancelled("mission-1", "mission-2", "CANCELLED") }
        assertFailsWith<IllegalStateException> { MissionIntervention.requireCancelled("mission-1", "mission-1", "RUNNING") }
    }

    @Test fun `recorded messages require an event receipt`() {
        MissionIntervention.requireMessageRecorded(true, "event-1")
        assertFailsWith<IllegalStateException> { MissionIntervention.requireMessageRecorded(false, "event-1") }
        assertFailsWith<IllegalStateException> { MissionIntervention.requireMessageRecorded(true, "") }
    }
}
