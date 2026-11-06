package com.dial.van.trading

import kotlinx.coroutines.CancellationException

sealed class Loaded<out T> {
    data object Loading : Loaded<Nothing>()
    data class Ready<T>(val value: T) : Loaded<T>()
    data class Unavailable(val reason: String) : Loaded<Nothing>()
}

/** Both transport failure and malformed source data are unavailable; neither cancels other sections. */
suspend fun <T> loadTradingData(parse: (String) -> T?, call: suspend () -> String): Loaded<T> = try {
    parse(call())?.let { Loaded.Ready(it) } ?: Loaded.Unavailable("Gateway response unreadable")
} catch (cancelled: CancellationException) {
    throw cancelled
} catch (failure: Exception) {
    Loaded.Unavailable("Trading information unavailable: ${failure.message?.take(80) ?: "no detail"}")
}
