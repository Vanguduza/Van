package com.dial.van.trading

/** Resolves legacy overlay links to destinations the trading graph actually serves. */
object TradingNavigation {
    const val ROOT = "overview"

    fun resolveRoute(requested: String?): String {
        val route = requested?.trim().orEmpty()
        return when (route) {
            "overview", "positions", "potential", "history", "accounts", "accounts/add", "strategies", "cognition", "tickets" -> route
            "trades/CURRENT" -> "positions"
            "trades/PAST" -> "history"
            "trades/POTENTIAL" -> "potential"
            else -> {
                val id = when {
                    route.startsWith("trade/") -> route.removePrefix("trade/")
                    route.startsWith("positions/") -> route.removePrefix("positions/")
                    else -> ""
                }
                if (id.isNotEmpty() && id.all { it.isLetterOrDigit() || it in "-_." }) {
                    "positions/$id"
                } else ROOT
            }
        }
    }

    /** The graph keeps Overview beneath a launch link, including parameterised detail. */
    fun launchDestination(requested: String?, alreadyHandled: Boolean): String? {
        if (alreadyHandled) return null
        return resolveRoute(requested).takeUnless { it == ROOT }
    }
}
