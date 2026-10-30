package com.dial.van.mission

import org.json.JSONObject

/** Dispatch fences and worker reports are different observations. Neither proves OS suspension. */
object MissionExecutionControl {
    fun request(operation: String, generation: Int, requestId: String, message: String): JSONObject {
        require(operation in setOf("PAUSE", "RESUME", "DIRECTION") && generation >= 0 && requestId.isNotBlank()) { "Current mission control identity is required." }
        val body = JSONObject().put("request_id", requestId).put("expected_generation", generation)
        if (operation == "DIRECTION") {
            require(message.isNotBlank() && message.length <= 16000 && '\u0000' !in message) { "Supply bounded direction for this mission." }
            body.put("message", message.trim())
        } else {
            require(message.length <= 2000 && '\u0000' !in message) { "The control reason is too long." }
            body.put("reason", message.trim())
        }
        return body
    }
    fun confirms(missionId: String, operation: String, request: JSONObject, receipt: JSONObject): Boolean =
        receipt.optString("status") == "CONTROL_RECORDED" && receipt.optString("mission_id") == missionId &&
            receipt.optString("request_id") == request.optString("request_id") && receipt.optString("operation") == operation &&
            receipt.optInt("expected_generation", -1) == request.optInt("expected_generation") &&
            receipt.optInt("generation", -1) == request.optInt("expected_generation") + 1 &&
            receipt.optString("payload_digest").matches(Regex("sha256:[a-f0-9]{64}")) &&
            (operation != "DIRECTION" || receipt.optString("direction") == request.optString("message")) &&
            receipt.optString("reason") == request.optString("reason", "") &&
            when (operation) { "PAUSE" -> receipt.optString("desired_execution") == "PAUSED"; "RESUME" -> receipt.optString("desired_execution") == "RUNNING"; else -> true }

    fun workerMatches(control: JSONObject, report: JSONObject): Boolean =
        report.optString("status") in setOf("CHECKPOINT_RECORDED", "DIRECTION_ADOPTION_RECORDED") &&
            report.optString("control_id") == control.optString("control_id") &&
            report.optString("mission_id") == control.optString("mission_id") &&
            report.optString("payload_digest") == control.optString("payload_digest") &&
            !control.isNull("hermes_run_id") && report.optString("hermes_run_id") == control.optString("hermes_run_id") &&
            report.optInt("original_control_generation", -1) == control.optInt("generation") &&
            report.opt("authority_granted") == false && report.opt("process_stopped_verified") == false
}
