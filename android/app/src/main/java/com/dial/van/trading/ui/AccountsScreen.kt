package com.dial.van.trading.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel
import com.dial.van.trading.AccountCard
import com.dial.van.trading.DataState
import com.dial.van.trading.Loaded
import com.dial.van.trading.SafetyIdentity
import com.dial.van.trading.TradingFormat
import com.dial.van.trading.TradingRepository

/**
 * DNA §4 Trading destination 6, "Accounts": migrated onto the design system from the deleted
 * `ui/TradingComponents.kt`'s raw-colour `AccountRow`, protocol unchanged.
 *
 * @DataSource("GET /v1/trading/accounts")
 */
@Composable
fun AccountsScreen(repo: TradingRepository, nav: TradingNav, nowMs: () -> Long) {
    val tokens = LocalVanTokens.current
    var tick by remember { mutableIntStateOf(0) }
    var accounts: Loaded<List<AccountCard>> by remember { mutableStateOf(Loaded.Loading) }
    LaunchedEffect(tick) { accounts = repo.accounts() }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = tokens.space.pageGutter, vertical = tokens.space.space3),
        verticalArrangement = Arrangement.spacedBy(tokens.space.space2),
    ) {
        item {
            SectionHeader(
                title = "Accounts",
                trailing = {
                    Row {
                        TextButton(onClick = nav.openAccountAdd) { Text("+ Add", style = tokens.type.label, color = tokens.color.accentCyan) }
                        TradingRefreshAction { tick += 1 }
                    }
                },
            )
        }
        val loaded = accounts
        when (loaded) {
            Loaded.Loading -> item { Text("Reading the ledger…", style = tokens.type.body, color = tokens.color.textSecondary) }
            is Loaded.Unavailable -> item {
                Text(TradingFormat.unavailableState(loaded.reason), style = tokens.type.body, color = tokens.color.forStatusRole(StatusSemantics.ROLE_EVENT_RISK))
            }
            is Loaded.Ready -> {
                if (loaded.value.isEmpty()) {
                    item {
                        Text(TradingFormat.emptyState("accounts"), style = tokens.type.body, color = tokens.color.textSecondary)
                    }
                } else {
                    items(loaded.value, key = { it.alias }) { account -> AccountRow(account, nowMs()) }
                }
            }
        }
        item {
            TradingDisclosure(
                "Connection health, balances and risk state come from ACCOUNT_SNAPSHOT events " +
                    "written by each session. Credentials are never exposed in UI state or logs.",
            )
        }
    }
}

@Composable
private fun AccountRow(account: AccountCard, nowMs: Long) {
    val tokens = LocalVanTokens.current
    VanPanel(dense = true) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                    Text(account.label, style = tokens.type.headline, color = tokens.color.textPrimary)
                    StatusChip(
                        label = account.safety.label,
                        role = if (account.safety == SafetyIdentity.LIVE) StatusSemantics.ROLE_CRITICAL else StatusSemantics.ROLE_DISABLED,
                        filled = account.safety == SafetyIdentity.LIVE,
                    )
                    StatusChip(
                        label = account.connection.label,
                        role = if (account.connection == DataState.LIVE) StatusSemantics.ROLE_FAVOURABLE else StatusSemantics.ROLE_EVENT_RISK,
                    )
                }
                Text(
                    "${account.broker} · ${account.mode} · ${account.currency} · ${account.openPositions} open · synced ${TradingFormat.age(nowMs, account.lastSyncMs)}",
                    style = tokens.type.label,
                    color = tokens.color.textTertiary,
                )
                if (account.killSwitch.isNotEmpty()) {
                    Text("Kill switch: ${account.killSwitch.joinToString()}", style = tokens.type.label, color = tokens.color.forStatusRole(StatusSemantics.ROLE_CRITICAL))
                }
            }
            Column(horizontalAlignment = androidx.compose.ui.Alignment.End) {
                Text(account.equity.plain, style = tokens.type.data, color = tokens.color.textPrimary)
                Text(account.dayPnl.signed, style = tokens.type.data, color = tokens.color.textSecondary)
            }
        }
    }
}
