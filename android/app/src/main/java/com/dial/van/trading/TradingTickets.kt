package com.dial.van.trading

import java.math.BigDecimal
import org.json.JSONObject

data class TradingTicket(
    val id: String, val symbol: String?, val side: String?, val quantity: String?,
    val status: String, val fillPrice: String?, val filledQuantity: String?,
    val contractNote: String?, val confirmationHash: String?,
)

data class TradingTicketList(val ledgerAvailable: Boolean, val tickets: List<TradingTicket>) {
    companion object {
        fun parse(body: String): TradingTicketList? = runCatching {
            val root = JSONObject(body)
            val available = root.get("ledger_available") as? Boolean ?: return null
            val rows = root.getJSONArray("tickets")
            require(rows.length() <= 5000)
            val tickets = (0 until rows.length()).map { index ->
                val row = rows.getJSONObject(index)
                val id = row.getString("ticket").also { require(it.isNotBlank() && it.length <= 128) }
                val status = row.getString("status").also { require(it in setOf("OPEN", "CONFIRMED")) }
                fun text(key: String): String? = if (row.isNull(key)) null else row.get(key).toString()
                TradingTicket(id, text("symbol"), text("side"), text("qty"), status,
                    text("fill_price"), text("filled_qty"), text("contract_note_ref"), text("confirmation_hash"))
            }
            require(tickets.map { it.id }.distinct().size == tickets.size)
            require(available || tickets.isEmpty())
            TradingTicketList(available, tickets)
        }.getOrNull()
    }
}

data class TradingTicketConfirmation(
    val ticketId: String, val fillPrice: String, val filledQty: String, val contractNoteRef: String,
) {
    fun commandText(): String = COMMAND_PREFIX + JSONObject().put("ticket_id", ticketId)
        .put("fill_price", fillPrice).put("filled_qty", filledQty)
        .put("contract_note_ref", contractNoteRef).toString()

    companion object {
        const val COMMAND_PREFIX = "confirm trading ticket "
        const val CLIENT_CONTEXT_KEY = "owner_ticket_authority_ref"
        fun prepare(ticket: TradingTicket, price: String, quantity: String, note: String): TradingTicketConfirmation {
            require(ticket.status == "OPEN") { "This ticket is already confirmed." }
            require(ticket.id.isNotBlank() && ticket.id.length <= 128) { "Ticket identity is invalid." }
            fun amount(value: String): BigDecimal {
                require(value.trim().matches(Regex("[0-9]{1,18}(\\.[0-9]{1,8})?"))) { "Enter a positive decimal with at most eight decimal places." }
                return BigDecimal(value.trim()).also { require(it > BigDecimal.ZERO) { "Amounts must be positive." } }
            }
            val px = amount(price)
            val qty = amount(quantity)
            ticket.quantity?.let { limit ->
                val maximum = runCatching { BigDecimal(limit) }.getOrNull()
                require(maximum != null && maximum > BigDecimal.ZERO) { "Ticket quantity cannot be verified." }
                require(qty <= maximum) { "Filled quantity exceeds the ticket quantity." }
            }
            val reference = note.trim()
            require(reference.isNotEmpty() && reference.length <= 256 && reference.none { it.isISOControl() }) { "Enter a broker contract note reference of up to 256 characters." }
            return TradingTicketConfirmation(ticket.id, px.stripTrailingZeros().toPlainString(),
                qty.stripTrailingZeros().toPlainString(), reference)
        }
    }
}
