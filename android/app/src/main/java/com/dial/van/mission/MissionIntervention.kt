package com.dial.van.mission

/** Owner controls acknowledge gateway receipts, never the button press alone. */
object MissionIntervention {
    fun requireCancelled(expectedId: String, receivedId: String, state: String) {
        check(expectedId.isNotBlank() && receivedId == expectedId && state == "CANCELLED") {
            "VAN did not confirm cancellation of this mission. Refresh its status before trying again."
        }
    }

    fun requireMessageRecorded(recorded: Boolean, eventId: String) {
        check(recorded && eventId.isNotBlank()) {
            "VAN did not confirm recording this message. Check the timeline before sending it again."
        }
    }
}
