package com.dial.van.command.settings

import org.json.JSONObject

/** Owner choices come from the gateway; submission still requires its sealed A4 approval. */
data class DomainAutonomyOptions(val domains: List<String>, val levels: List<String>) {
    fun commandText(domain: String, level: String): String {
        require(domain in domains && level in levels) { "Refresh the available autonomy choices." }
        return COMMAND_PREFIX + JSONObject().put("domain", domain).put("level", level).toString()
    }

    companion object {
        const val COMMAND_PREFIX = "set domain autonomy ceiling "
        private val SUPPORTED_LEVELS = listOf("S0", "S1", "S2", "S3", "S4")

        fun parse(body: JSONObject): DomainAutonomyOptions? = runCatching {
            require(body.getString("typed_command_prefix") == COMMAND_PREFIX)
            val domains = body.getJSONArray("known_domains").let { rows ->
                require(rows.length() <= 1000)
                (0 until rows.length()).map { index ->
                    (rows.get(index) as? String ?: error("Invalid domain")).also {
                        require(it.isNotEmpty() && it.length <= 128 && it == it.trim())
                        require(it.none { char -> char.isISOControl() })
                        require(it.matches(Regex("[a-z][a-z0-9_-]*(?:\\.[a-z][a-z0-9_-]*){0,7}")))
                    }
                }
            }
            require(domains.distinct().size == domains.size)
            val levels = body.getJSONArray("supported_levels").let { rows ->
                (0 until rows.length()).map { rows.get(it) as? String ?: error("Invalid level") }
            }
            require(levels == SUPPORTED_LEVELS)
            DomainAutonomyOptions(domains, levels)
        }.getOrNull()
    }
}
