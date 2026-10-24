package com.dial.van.gateway

import org.json.JSONObject

/** Replay only routes whose server contract matches a stable durable operation identity. */
object GatewayMutationRetry {
    /** The production boundary for an operation without a server-enforced replay identity. */
    fun <T> singleAttempt(httpStatus: (Throwable) -> Int?, call: () -> T): T = try {
        call()
    } catch (failure: Throwable) {
        val status = httpStatus(failure)
        if ((status == null && failure is java.io.IOException) || status == 408 ||
            (status != null && status >= 500)) {
            throw GatewayMutationOutcomeUnknown(failure)
        }
        throw failure
    }

    fun replaySafe(path: String, text: String): Boolean {
        val body = runCatching { JSONObject(text) }.getOrNull() ?: return false
        fun present(key: String) = body.optString(key).isNotBlank()
        return when (path.substringBefore('?')) {
            "/v1/commands" -> present("command_id") && present("idempotency_key")
            "/v1/reminders/parse" -> present("idempotency_key")
            "/v1/session/messages" -> present("message_id") && present("idempotency_key")
            "/v1/session/open" -> present("open_request_id")
            "/v1/devices/pair" -> present("device_id") && present("device_secret") &&
                present("pairing_token") && body.optString("device_access_token").length >= 32
            else -> false
        }
    }
}

class SessionOpenRecoveryException(reason: String) : IllegalStateException(reason)

class GatewayMutationOutcomeUnknown(cause: Throwable) : java.io.IOException(
    "The gateway response was lost. This change may already have been applied; check its current state before trying again.",
    cause,
)
