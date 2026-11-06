package com.dial.van.trading.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.fragment.app.FragmentActivity
import com.dial.van.VanApplication
import com.dial.van.control.VanCommandSource
import com.dial.van.control.VanMessageRole
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.components.ApprovalSheet
import com.dial.van.design.components.VanPanel
import com.dial.van.security.BiometricGate
import com.dial.van.security.OwnerApprovalKeyManager
import com.dial.van.trading.Loaded
import com.dial.van.trading.TradingRepository
import com.dial.van.trading.TradingTicket
import com.dial.van.trading.TradingTicketConfirmation
import com.dial.van.trading.TradingTicketList

@Composable
fun TicketsScreen(app: VanApplication, repo: TradingRepository) {
    val tokens = LocalVanTokens.current
    val activity = LocalContext.current as? FragmentActivity
    val gate = remember(activity) { activity?.let(::BiometricGate) }
    var tick by remember { mutableIntStateOf(0) }
    var tickets: Loaded<TradingTicketList> by remember { mutableStateOf(Loaded.Loading) }
    var refreshing by remember { mutableStateOf(false) }
    var selected: TradingTicket? by remember { mutableStateOf(null) }
    var authorityInFlight by remember { mutableStateOf(false) }
    var feedback by remember { mutableStateOf<String?>(null) }
    val conversation by app.commandController.state.collectAsState()
    val ownerIndex = conversation.messages.indexOfLast {
        it.role == VanMessageRole.OWNER && it.text.startsWith(TradingTicketConfirmation.COMMAND_PREFIX)
    }
    val reply = if (ownerIndex < 0) null else conversation.messages.drop(ownerIndex + 1).firstOrNull()
    val pending = conversation.pendingA4Approval?.takeIf {
        it.command.text.startsWith(TradingTicketConfirmation.COMMAND_PREFIX)
    }
    LaunchedEffect(tick) {
        refreshing = true
        try { tickets = repo.tickets() } finally { refreshing = false }
    }
    LaunchedEffect(reply?.status, reply?.text) {
        if (reply != null && !conversation.submitting && pending == null) tick++
    }
    LazyColumn(modifier = Modifier.fillMaxSize(), contentPadding = PaddingValues(tokens.space.pageGutter),
        verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
        item {
            Text("Owner broker tickets", style = tokens.type.title, color = tokens.color.textPrimary)
            Text("Record a fill already completed with your broker. Confirmation records evidence in the trading ledger; it does not place or execute an order.", style = tokens.type.body, color = tokens.color.textSecondary)
            TextButton(enabled = !refreshing, onClick = { tick++ }) { Text(if (refreshing) "Refreshing…" else "Refresh") }
        }
        item {
            feedback?.let { Text(it, color = tokens.color.textSecondary) }
            if (authorityInFlight) Text("Owner authority approval pending.", color = tokens.color.textSecondary)
            pending?.let { challenge ->
                VanPanel { Column {
                    Text("Approve the exact recorded fill", style = tokens.type.title)
                    Text(challenge.resolvedParametersJson ?: challenge.resolvedActionId)
                    TextButton(enabled = activity != null, onClick = { activity?.let { app.commandController.approvePendingA4(it) } }) { Text("Approve with biometric") }
                    TextButton(onClick = { app.commandController.discardPendingA4(challenge.challengeId) }) { Text("Decline") }
                } }
            }
            reply?.let { Text("${it.status?.name ?: "Response"}: ${it.text}", color = tokens.color.textSecondary) }
        }
        when (val loaded = tickets) {
            Loaded.Loading -> item { Text("Reading broker tickets…") }
            is Loaded.Unavailable -> item { Text("Broker tickets could not be read. Refresh to retry.") }
            is Loaded.Ready -> {
                if (!loaded.value.ledgerAvailable) item { Text("The trading ledger is unavailable; ticket state is unknown.") }
                else if (loaded.value.tickets.isEmpty()) item { Text("The current ledger read contains no owner broker tickets.") }
                items(loaded.value.tickets, key = { it.id }) { ticket ->
                    VanPanel { Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                        Text("${ticket.id} · ${ticket.symbol ?: "Symbol unavailable"}", style = tokens.type.body)
                        Text("${ticket.status} · ${ticket.side ?: "Side unavailable"} · quantity ${ticket.quantity ?: "unknown"}")
                        ticket.fillPrice?.let { Text("Recorded fill: ${ticket.filledQuantity ?: "?"} at $it") }
                        ticket.contractNote?.let { Text("Contract note: $it") }
                        ticket.confirmationHash?.let { Text("Ledger receipt: $it", style = tokens.type.label) }
                        if (ticket.status == "OPEN") TextButton(enabled = !authorityInFlight && !conversation.submitting && pending == null,
                            onClick = { feedback = null; selected = ticket }) { Text("Record broker confirmation") }
                    } }
                }
            }
        }
    }
    selected?.let { ticket ->
        var price by remember(ticket.id) { mutableStateOf("") }
        var quantity by remember(ticket.id) { mutableStateOf(ticket.quantity.orEmpty()) }
        var note by remember(ticket.id) { mutableStateOf("") }
        ApprovalSheet(title = "Confirm ${ticket.id}", actionDigest = "Records only this broker fill. First authorize the ticket, then approve the gateway's exact fill parameters with biometrics.",
            approveLabel = "Authorize ticket", onDismiss = { selected = null }, confirmation = {
                Column {
                    OutlinedTextField(price, { price = it }, label = { Text("Fill price") }, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(quantity, { quantity = it }, label = { Text("Filled quantity") }, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(note, { note = it }, label = { Text("Broker contract note reference") }, modifier = Modifier.fillMaxWidth())
                }
            }, onApprove = {
                val confirmation = runCatching { TradingTicketConfirmation.prepare(ticket, price, quantity, note) }.getOrElse { return@ApprovalSheet Result.failure(it) }
                if (gate == null || authorityInFlight) return@ApprovalSheet Result.failure(IllegalStateException("Owner biometric approval is unavailable or already pending."))
                val prepared = runCatching { OwnerApprovalKeyManager().prepareOwnerAuthority(act = "ticket-confirm", subject = ticket.id) }
                    .getOrElse { return@ApprovalSheet Result.failure(IllegalStateException("Owner authority key is unavailable.")) }
                val signature = runCatching { app.gatewayClient.newA4ApprovalSignature() }
                    .getOrElse { return@ApprovalSheet Result.failure(IllegalStateException("Owner authority key is unavailable.")) }
                authorityInFlight = true
                gate.requestA4CommandApproval(signature, prepared.canonical, "Authorize ticket confirmation", ticket.id,
                    onApproved = { signed ->
                        authorityInFlight = false
                        val ref = runCatching { prepared.assembleFromSignatureBase64(signed) }.getOrNull()
                        if (ref == null) feedback = "Ticket authority could not be assembled; nothing was sent."
                        else app.commandController.submitText(text = confirmation.commandText(), source = VanCommandSource.QUICK_ACTION,
                            actionClass = "A4", clientContext = mapOf(TradingTicketConfirmation.CLIENT_CONTEXT_KEY to ref))
                    }, onDenied = { authorityInFlight = false; feedback = "Ticket authority was declined; nothing was sent." })
                Result.success(Unit)
            })
    }
}
