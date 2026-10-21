package com.dial.van.command.settings

import org.json.JSONArray
import org.json.JSONObject

/** Exact consent scope, prepared only from current registered action contracts. */
object OwnerPermissionDraft {
    fun command(contracts: JSONObject, selected: JSONObject, parameters: JSONObject,
        expiresAtMs: Long, maxUses: Int, nowMs: Long): String {
        require(contracts.optString("command_prefix") == "grant owner permission " && contracts.optBoolean("native_authority_required")) {
            "The gateway has not supplied a valid owner grant contract."
        }
        val advertised = contracts.optJSONArray("contracts") ?: error("Permission contracts are missing.")
        require((0 until advertised.length()).any { index ->
            val entry = advertised.getJSONObject(index)
            entry.optString("permission") == selected.optString("permission") &&
                entry.optString("action_id") == selected.optString("action_id") && entry.toString() == selected.toString()
        }) { "Choose one of the current registered action scopes." }
        require(selected.optString("action_class") in setOf("A1", "A2", "A3", "A4")) { "This action cannot receive an owner consent grant." }
        require(expiresAtMs > nowMs && expiresAtMs - nowMs <= contracts.optLong("max_duration_ms")) { "Choose an expiry within the advertised limit." }
        require(maxUses in 1..contracts.optInt("max_uses").coerceAtMost(1000)) { "Choose a bounded use budget." }
        val schema = selected.getJSONObject("parameter_schema")
        val properties = schema.optJSONObject("properties") ?: JSONObject()
        val names = parameters.keys().asSequence().toSet()
        require(names.size <= 32 && names.all { properties.has(it) }) { "Supply only parameters declared for this exact action." }
        val required = schema.optJSONArray("required")
        if (required != null) require((0 until required.length()).all { names.contains(required.getString(it)) }) { "All declared required parameters must be supplied." }
        names.forEach { name ->
            val declaration = properties.optJSONObject(name)
            val kind = declaration?.optString("type") ?: properties.optString(name)
            val value = parameters.get(name)
            val valid = when (kind) {
                "string" -> value is String
                "integer" -> value is Int || value is Long
                "number" -> value is Number
                "array" -> value is JSONArray
                "object" -> value is JSONObject
                "boolean" -> value is Boolean
                else -> false
            }
            require(valid) { "Parameter $name must have the declared $kind type." }
        }
        inspect(parameters)
        val body = JSONObject().put("permission", selected.getString("permission"))
            .put("action_id", selected.getString("action_id")).put("parameters", parameters)
            .put("expires_at_ms", expiresAtMs).put("max_uses", maxUses)
        require(body.toString().toByteArray(Charsets.UTF_8).size <= 8192) { "This consent scope is too large." }
        return contracts.getString("command_prefix") + body.toString()
    }

    private fun inspect(value: Any?) {
        when (value) {
            is JSONObject -> value.keys().asSequence().toList().forEach { key ->
                require(!Regex("(?i)(token|password|secret|cookie|private_key)").containsMatchIn(key)) { "Credentials cannot be part of a permission scope." }
                inspect(value.opt(key))
            }
            is JSONArray -> { require(value.length() <= 64) { "Scope arrays are too large." }; (0 until value.length()).forEach { inspect(value.opt(it)) } }
            is String -> {
                require(value.trim() !in setOf("*", "**") && value.length <= 4096) { "Wildcard or unbounded scopes are unavailable." }
                require(!Regex("(?i)(bearer\\s+[A-Za-z0-9._-]{12,}|ya29\\.|gh[pousr]_[A-Za-z0-9]{16,}|cookie\\s*[:=]|set-cookie|refresh_token|access_token\\s*[:=]|-----BEGIN)").containsMatchIn(value)) { "Credentials cannot be part of a permission scope." }
            }
        }
    }
}
