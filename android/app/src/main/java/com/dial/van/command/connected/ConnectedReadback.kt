package com.dial.van.command.connected

import kotlinx.coroutines.CancellationException
import org.json.JSONObject

/** Connection reads and owner revocation have separate, explicit confirmation outcomes. */
object ConnectedReadback {
    data class Source(val value: JSONObject? = null, val failure: String? = null)
    suspend fun source(call: suspend () -> JSONObject): Source = try {
        Source(value = call())
    } catch (cancel: CancellationException) { throw cancel }
    catch (failure: Exception) { Source(failure = failure.message ?: "Source unavailable") }

    data class Revocation(val status: JSONObject? = null, val error: String? = null) {
        val confirmed: Boolean get() = status != null && error == null
    }
    suspend fun revoke(request: suspend () -> JSONObject, read: suspend () -> JSONObject): Revocation = try {
        val receipt = request()
        require(!receipt.getBoolean("connected"))
        val fresh = read()
        require(!fresh.getBoolean("connected"))
        Revocation(status = fresh)
    } catch (cancel: CancellationException) { throw cancel }
    catch (failure: Exception) {
        Revocation(error = "Workspace revocation could not be confirmed. The request may have been applied; refresh the connection state before trying again.")
    }
}
