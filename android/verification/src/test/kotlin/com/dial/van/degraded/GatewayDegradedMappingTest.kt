package com.dial.van.degraded

import org.json.JSONArray
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class GatewayDegradedMappingTest {

    private fun capabilityJson(
        code: String,
        broken: String = "broken sentence",
        stillWorks: String = "still works sentence",
        willNotDo: String = "will not do sentence",
        restoreAction: String = "restore sentence",
    ): JSONObject = JSONObject()
        .put("code", code)
        .put("broken", broken)
        .put("still_works", stillWorks)
        .put("will_not_do", willNotDo)
        .put("restore_action", restoreAction)

    @Test
    fun `parse reads every well-formed row`() {
        val health = JSONObject().put(
            "degraded",
            JSONArray().put(capabilityJson("TRADING_LEDGER_UNAVAILABLE")).put(capabilityJson("HERMES_OFFLINE")),
        )
        val capabilities = GatewayDegradedMapping.parse(health)
        assertEquals(listOf("TRADING_LEDGER_UNAVAILABLE", "HERMES_OFFLINE"), capabilities.map { it.code })
    }

    @Test
    fun `parse is empty for a missing degraded array`() {
        assertTrue(GatewayDegradedMapping.parse(JSONObject()).isEmpty())
    }

    @Test
    fun `parse drops a row with no code rather than throwing`() {
        val health = JSONObject().put("degraded", JSONArray().put(JSONObject().put("broken", "x")))
        assertTrue(GatewayDegradedMapping.parse(health).isEmpty())
    }

    @Test
    fun `HERMES_OFFLINE maps onto the existing hermes subsystem id`() {
        assertEquals("hermes", GatewayDegradedMapping.subsystemIdFor("HERMES_OFFLINE"))
    }

    @Test
    fun `an unmapped code gets its own gw-prefixed id`() {
        assertEquals("gw:trading_ledger_unavailable", GatewayDegradedMapping.subsystemIdFor("TRADING_LEDGER_UNAVAILABLE"))
        assertEquals("gw:storage_problem", GatewayDegradedMapping.subsystemIdFor("STORAGE_PROBLEM"))
    }

    @Test
    fun `labelFor renders a readable title from the code`() {
        assertEquals("Trading ledger unavailable", GatewayDegradedMapping.labelFor("TRADING_LEDGER_UNAVAILABLE"))
    }

    @Test
    fun `detailFor names what is broken, what still works, and how to restore it`() {
        val capability = GatewayDegradedMapping.GatewayCapability(
            code = "TRADING_LEDGER_UNAVAILABLE",
            broken = "The trade ledger cannot be read.",
            stillWorks = "Local reminders",
            willNotDo = "Trading reads",
            restoreAction = "Restart the gateway",
        )
        val detail = GatewayDegradedMapping.detailFor(capability)
        assertTrue(detail.contains("cannot be read"))
        assertTrue(detail.contains("Still works: Local reminders"))
        assertTrue(detail.contains("Will not: Trading reads"))
        assertTrue(detail.contains("To restore: Restart the gateway"))
    }
}

class DegradedModeStoreGatewayHealthTest {

    @Test
    fun `an unmapped backend code adds its own broken row`() {
        val store = DegradedModeStore()
        val health = JSONObject().put(
            "degraded",
            JSONArray().put(
                JSONObject()
                    .put("code", "TRADING_LEDGER_UNAVAILABLE")
                    .put("broken", "The ledger is unreadable.")
                    .put("still_works", "Reminders")
                    .put("will_not_do", "Trading reads")
                    .put("restore_action", "Restart the gateway"),
            ),
        )
        store.applyGatewayHealth(health)
        val row = store.snapshot().subsystems.first { it.id == "gw:trading_ledger_unavailable" }
        assertEquals(SubsystemStatus.BROKEN, row.status)
        assertTrue(row.detail.contains("ledger is unreadable"))
        assertTrue(store.snapshot().active)
    }

    @Test
    fun `HERMES_OFFLINE updates the existing hermes row rather than adding a second one`() {
        val store = DegradedModeStore()
        val health = JSONObject().put(
            "degraded",
            JSONArray().put(
                JSONObject()
                    .put("code", "HERMES_OFFLINE")
                    .put("broken", "Hermes is unreachable.")
                    .put("still_works", "Local reminders")
                    .put("will_not_do", "Agent reasoning")
                    .put("restore_action", "Restore Hermes"),
            ),
        )
        store.applyGatewayHealth(health)
        val hermesRows = store.snapshot().subsystems.filter { it.id == "hermes" }
        assertEquals(1, hermesRows.size)
        assertEquals(SubsystemStatus.BROKEN, hermesRows.first().status)
    }

    @Test
    fun `a resolved code clears its row on the next apply`() {
        val store = DegradedModeStore()
        val broken = JSONObject().put(
            "degraded",
            JSONArray().put(JSONObject().put("code", "STORAGE_PROBLEM").put("broken", "x").put("still_works", "y").put("will_not_do", "z").put("restore_action", "w")),
        )
        store.applyGatewayHealth(broken)
        assertTrue(store.snapshot().subsystems.any { it.id == "gw:storage_problem" })

        store.applyGatewayHealth(JSONObject().put("degraded", JSONArray()))
        assertTrue(store.snapshot().subsystems.none { it.id == "gw:storage_problem" })
    }

    @Test
    fun `device-signal rows survive a gateway-health apply untouched`() {
        val store = DegradedModeStore()
        store.mark("overlay", SubsystemStatus.BROKEN, "overlay permission missing", RestoreAction.OPEN_SETTINGS)
        store.applyGatewayHealth(JSONObject().put("degraded", JSONArray()))
        val overlay = store.snapshot().subsystems.first { it.id == "overlay" }
        assertEquals(SubsystemStatus.BROKEN, overlay.status)
        assertEquals("overlay permission missing", overlay.detail)
    }

    @Test
    fun `the String overload matches DegradedBridge GatewayHealthSink and tolerates bad JSON`() {
        val store = DegradedModeStore()
        store.applyGatewayHealth("not json at all")
        assertTrue(store.snapshot().subsystems.none { it.id.startsWith("gw:") })

        store.applyGatewayHealth(
            JSONObject().put(
                "degraded",
                JSONArray().put(JSONObject().put("code", "RESEARCH_UNAVAILABLE").put("broken", "x").put("still_works", "y").put("will_not_do", "z").put("restore_action", "w")),
            ).toString(),
        )
        assertTrue(store.snapshot().subsystems.any { it.id == "gw:research_unavailable" })
    }
}
