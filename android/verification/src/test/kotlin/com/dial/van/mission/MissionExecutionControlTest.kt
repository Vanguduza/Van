package com.dial.van.mission

import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.test.assertFails

class MissionExecutionControlTest {
    private fun control() = JSONObject().put("status", "CONTROL_RECORDED").put("mission_id", "mission").put("control_id", "control")
        .put("request_id", "request").put("operation", "PAUSE").put("expected_generation", 2).put("generation", 3)
        .put("payload_digest", "sha256:" + "a".repeat(64)).put("desired_execution", "PAUSED").put("hermes_run_id", "run").put("reason", "Wait")
    @Test fun `pause receipt binds original request generation reason and desired fence`() {
        val request = MissionExecutionControl.request("PAUSE", 2, "request", "Wait")
        assertTrue(MissionExecutionControl.confirms("mission", "PAUSE", request, control()))
        for ((field, value) in listOf("mission_id" to "other", "request_id" to "other", "expected_generation" to 3,
            "generation" to 4, "reason" to "Changed", "desired_execution" to "RUNNING"))
            assertFalse(MissionExecutionControl.confirms("mission", "PAUSE", request, control().put(field, value)), field)
    }
    @Test fun `direction recovery requires exact owner text rather than mere recorded status`() {
        val request = MissionExecutionControl.request("DIRECTION", 2, "request", "Use the current draft")
        val receipt = control().put("operation", "DIRECTION").put("reason", "").put("direction", "Use the current draft")
        assertTrue(MissionExecutionControl.confirms("mission", "DIRECTION", request, receipt))
        assertFalse(MissionExecutionControl.confirms("mission", "DIRECTION", request, receipt.put("direction", "Other draft")))
        assertFails { MissionExecutionControl.request("DIRECTION", 2, "request", "") }
    }
    @Test fun `worker acknowledgement must match exact run control original generation and no process claim`() {
        val receipt = control()
        val report = JSONObject().put("status", "CHECKPOINT_RECORDED").put("mission_id", "mission").put("control_id", "control")
            .put("payload_digest", receipt.getString("payload_digest")).put("hermes_run_id", "run").put("original_control_generation", 3)
            .put("authority_granted", false).put("process_stopped_verified", false)
        assertTrue(MissionExecutionControl.workerMatches(receipt, report))
        assertFalse(MissionExecutionControl.workerMatches(receipt, report.put("hermes_run_id", "another")))
        assertFalse(MissionExecutionControl.workerMatches(receipt, report.put("hermes_run_id", "run").put("authority_granted", true)))
        report.remove("authority_granted")
        assertFalse(MissionExecutionControl.workerMatches(receipt, report))
    }
}
