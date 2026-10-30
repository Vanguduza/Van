package com.dial.van.command.work

import com.dial.van.design.StatusSemantics
import org.json.JSONArray
import org.json.JSONObject

internal fun jsonObjects(array: JSONArray): List<JSONObject> = buildList {
    for (index in 0 until array.length()) {
        array.optJSONObject(index)?.let(::add)
    }
}


internal fun statusRole(status: String): String = when (status.uppercase()) {
    "COMPLETED", "FILLED", "ACCEPTED", "ACTIVE" -> StatusSemantics.ROLE_FAVOURABLE
    "FAILED", "CANCELLED", "DISMISSED" -> StatusSemantics.ROLE_CRITICAL
    "PAUSED", "ARCHIVED", "WAITING" -> StatusSemantics.ROLE_EVENT_RISK
    else -> StatusSemantics.ROLE_MONITOR
}
