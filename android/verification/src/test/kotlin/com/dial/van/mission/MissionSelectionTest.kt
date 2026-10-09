package com.dial.van.mission

import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class MissionSelectionTest {
    private fun mission(id: String, state: String = "RUNNING") = MissionParsing.missionSummary(
        JSONObject().put("mission_id", id).put("state", state).put("is_terminal", state == "VERIFIED_SUCCESS"),
    )

    @Test
    fun `deep linked running mission is selected once and other running work remains visible`() {
        val named = mission("named")
        val other = mission("other")
        val view = MissionSelection.present("named", listOf(named, other), emptyList())
        assertEquals(named, view.requested)
        assertEquals(listOf(other), view.running)
    }

    @Test
    fun `deep linked waiting mission is selected without being shown again in waiting list`() {
        val named = mission("named", "WAITING_FOR_OWNER")
        val view = MissionSelection.present("named", emptyList(), listOf(named))
        assertEquals(named, view.requested)
        assertEquals(emptyList(), view.waiting)
    }

    @Test
    fun `completed mission fetched by ID stays visible after leaving active lists`() {
        val done = mission("done", "VERIFIED_SUCCESS")
        val view = MissionSelection.present("done", emptyList(), emptyList(), done)
        assertEquals(done, view.requested)
    }

    @Test
    fun `a response for another mission cannot satisfy the requested ID`() {
        assertNull(MissionSelection.present("named", emptyList(), emptyList(), mission("other")).requested)
    }

    @Test
    fun `plain Work keeps running and waiting lists intact`() {
        val running = listOf(mission("running"))
        val waiting = listOf(mission("waiting", "WAITING_FOR_OWNER"))
        val view = MissionSelection.present(null, running, waiting)
        assertNull(view.requested)
        assertEquals(running, view.running)
        assertEquals(waiting, view.waiting)
    }
}
