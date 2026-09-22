package com.dial.van.trading.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.fragment.app.FragmentActivity
import com.dial.van.VanApplication
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel
import com.dial.van.security.BiometricGate
import com.dial.van.trading.AccountOnboarding
import com.dial.van.trading.AccountOnboarding.Broker
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

/**
 * Add / link a trading account, migrated onto the design system. Protocol unchanged from the
 * pre-migration screen: every submit is gated by the owner biometric (A4) and signed with the
 * device secret; credentials are sent once to the gateway and cleared from these fields
 * afterwards.
 */
@Composable
fun AccountOnboardingScreen(app: VanApplication, onDone: () -> Unit) {
    val tokens = LocalVanTokens.current
    val ctx = LocalContext.current
    val activity = ctx as? FragmentActivity
    val gate = remember(activity) { activity?.let { BiometricGate(it) } }
    val scope = rememberCoroutineScope()
    var broker by remember { mutableStateOf(Broker.DERIV) }
    var status by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }

    fun submit(action: String, args: JsonObject, then: (AccountOnboarding.ActionOutcome) -> Unit = {}) {
        val send: (JsonObject?) -> Unit = { proof ->
            busy = true; status = "Signing and sending…"
            scope.launch {
                val outcome = runCatching { app.gatewayClient.tradingAccountAction(action, args, proof) }
                    .fold(onSuccess = { (code, body) -> AccountOnboarding.parseOutcome(action, body, code) }, onFailure = { AccountOnboarding.ActionOutcome(false, "Gateway unreachable: ${it.message?.take(80)}") })
                status = outcome.message; busy = false; then(outcome)
            }
        }

        if (!AccountOnboarding.requiresOwnerApproval(action)) { send(null); return }
        if (gate == null) { status = "Owner approval is unavailable on this screen."; return }

        busy = true; status = "Requesting owner approval…"
        scope.launch {
            val challenge = runCatching { app.gatewayClient.tradingAccountChallenge(action, args) }.getOrNull()
            val parsed = challenge?.takeIf { it.first in 200..299 }
                ?.let { runCatching { Json.parseToJsonElement(it.second).jsonObject }.getOrNull() }
            val canonical = parsed?.get("approval_challenge")?.jsonPrimitive?.contentOrNull
            val challengeId = parsed?.get("approval_challenge_id")?.jsonPrimitive?.contentOrNull
            if (canonical.isNullOrBlank() || challengeId.isNullOrBlank()) {
                busy = false
                status = "Could not obtain an approval challenge; nothing was sent."
                return@launch
            }
            val signature = runCatching { app.gatewayClient.newA4ApprovalSignature() }.getOrNull()
            if (signature == null) {
                busy = false
                status = "Owner approval key unavailable; nothing was sent."
                return@launch
            }
            busy = false
            gate.requestA4CommandApproval(
                signature = signature,
                challenge = canonical,
                title = "Approve trading account change",
                subtitle = AccountOnboarding.approvalSubtitle(action),
                onApproved = { signatureBase64 ->
                    send(
                        buildJsonObject {
                            put("challenge_id", challengeId)
                            put("signature_b64", signatureBase64)
                            put("algorithm", "ECDSA_P256_SHA256")
                        },
                    )
                },
                onDenied = { reason -> status = "Owner approval was not granted: $reason" },
            )
        }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = tokens.space.pageGutter, vertical = tokens.space.space3),
        verticalArrangement = Arrangement.spacedBy(tokens.space.space3),
    ) {
        item { SectionHeader(title = "Add trading account") }
        item { TradingTabs(Broker.entries.map { it.label }, broker.label) { l -> broker = Broker.entries.first { it.label == l } } }
        item { Text(broker.blurb, style = tokens.type.label, color = tokens.color.textTertiary) }
        item {
            when (broker) {
                Broker.DERIV -> DerivForm(ctx, busy, ::submit)
                Broker.CTRADER -> CtraderForm(ctx, busy, ::submit)
                Broker.MT5_EA -> Mt5EaForm(ctx, busy, ::submit)
                Broker.PAPER -> PaperForm(busy, ::submit)
            }
        }
        if (status.isNotEmpty()) {
            item {
                val warn = status.startsWith("Gateway") || status.contains("failed") || status.contains("denied")
                Text(status, style = tokens.type.body, color = if (warn) tokens.color.forStatusRole(StatusSemantics.ROLE_EVENT_RISK) else tokens.color.textSecondary)
            }
        }
        item {
            androidx.compose.material3.TextButton(onClick = onDone) {
                Text("Done →", style = tokens.type.label, color = tokens.color.accentCyan)
            }
        }
        item {
            TradingDisclosure(
                "Credentials are sent once, over the device-signed channel, to van-trading-core's " +
                    "0600 secrets store. They are never kept on this phone or in the gateway. A real " +
                    "account links as READ ONLY until an owner-signed mandate changes its mode.",
            )
        }
    }
}

@Composable
private fun Field(label: String, value: String, onChange: (String) -> Unit, secret: Boolean = false, keyboard: KeyboardType = KeyboardType.Text, error: String? = null) {
    val tokens = LocalVanTokens.current
    OutlinedTextField(
        value = value, onValueChange = onChange, label = { Text(label, style = tokens.type.label) }, singleLine = true, isError = error != null,
        supportingText = error?.let { { Text(it, style = tokens.type.label) } },
        visualTransformation = if (secret) PasswordVisualTransformation() else androidx.compose.ui.text.input.VisualTransformation.None,
        keyboardOptions = KeyboardOptions(keyboardType = if (secret) KeyboardType.Password else keyboard),
        colors = OutlinedTextFieldDefaults.colors(
            focusedTextColor = tokens.color.textPrimary, unfocusedTextColor = tokens.color.textPrimary,
            focusedBorderColor = tokens.color.accentCyan, unfocusedBorderColor = tokens.color.lineHair,
            focusedLabelColor = tokens.color.accentCyan, unfocusedLabelColor = tokens.color.textTertiary,
        ),
        modifier = Modifier.fillMaxWidth(),
    )
}

@Composable
private fun Action(text: String, enabled: Boolean, solid: Boolean = false, onClick: () -> Unit) {
    val tokens = LocalVanTokens.current
    val emphasisColor = tokens.color.forStatusRole(StatusSemantics.ROLE_EVENT_RISK)
    Button(
        onClick = onClick, enabled = enabled,
        colors = ButtonDefaults.buttonColors(
            containerColor = if (solid) emphasisColor else tokens.color.accentCyan.copy(alpha = 0.18f),
            contentColor = if (solid) tokens.color.textInverse else tokens.color.accentCyan,
        ),
        shape = RoundedCornerShape(tokens.radius.m),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(text, style = if (solid) tokens.type.headline else tokens.type.body)
    }
}

private fun openBrowser(ctx: Context, url: String) = ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
private fun copy(ctx: Context, label: String, text: String) = (ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText(label, text))

/** Browser sign-in shared by Deriv and cTrader: start → open → poll pending → pick account → link. */
@Composable
private fun OAuthLink(ctx: Context, busy: Boolean, startArgs: JsonObject, linkAction: String, linkArgs: (AccountOnboarding.DiscoveredAccount, String) -> JsonObject, submit: (String, JsonObject, (AccountOnboarding.ActionOutcome) -> Unit) -> Unit) {
    val tokens = LocalVanTokens.current
    var state by remember { mutableStateOf<String?>(null) }
    var found by remember { mutableStateOf<List<AccountOnboarding.DiscoveredAccount>>(emptyList()) }
    var polling by remember { mutableStateOf(false) }
    var label by remember { mutableStateOf("") }
    LaunchedEffect(state, polling) {
        val s = state ?: return@LaunchedEffect
        var tries = 0
        while (polling && tries < 60) {
            delay(3000); tries += 1
            submit("oauth_pending", buildJsonObject { put("state", s) }) { out -> if (out.ok) { found = AccountOnboarding.parseDiscovered(out.raw); polling = false } else if (out.raw?.get("expired") != null) polling = false }
        }
    }
    Action("Sign in with the broker in your browser", !busy) {
        submit("oauth_start", startArgs) { out -> if (out.ok && out.url != null) { state = out.state; found = emptyList(); polling = true; openBrowser(ctx, out.url) } }
    }
    if (polling) Text("Finish the sign-in in the browser, then return here. Checking…", style = tokens.type.label, color = tokens.color.textTertiary)
    if (found.isNotEmpty()) {
        Field("Label (optional)", label, { label = it })
        found.forEach { acc ->
            Row(
                modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(tokens.radius.m)).background(tokens.color.surface1)
                    .clickable(enabled = !busy) {
                        val s = state ?: return@clickable
                        submit(linkAction, JsonObject(linkArgs(acc, label).toMutableMap().apply { put("state", JsonPrimitive(s)) })) { if (it.ok) found = emptyList() }
                    }
                    .padding(tokens.space.space3),
                verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
            ) {
                Text(acc.label, style = tokens.type.body, color = tokens.color.textPrimary, modifier = Modifier.weight(1f))
                StatusChip(
                    label = if (acc.demo) "DEMO" else "LIVE → READ ONLY",
                    role = if (acc.demo) StatusSemantics.ROLE_EVENT_RISK else StatusSemantics.ROLE_CRITICAL,
                )
            }
        }
    }
}

@Composable
private fun DerivForm(ctx: Context, busy: Boolean, submit: (String, JsonObject, (AccountOnboarding.ActionOutcome) -> Unit) -> Unit) {
    val tokens = LocalVanTokens.current
    var appId by remember { mutableStateOf("1089") }
    var alias by remember { mutableStateOf("deriv_demo") }
    var token by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var code by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var residence by remember { mutableStateOf("zw") }
    var codeSent by remember { mutableStateOf(false) }
    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
        VanPanel(header = { Text("Link an existing Deriv account", style = tokens.type.headline, color = tokens.color.textPrimary) }) {
            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                Field("Deriv app id", appId, { appId = it }, keyboard = KeyboardType.Number)
                OAuthLink(ctx, busy, buildJsonObject { put("broker", "deriv"); put("app_id", appId) }, "deriv_oauth_link", { acc, lbl -> buildJsonObject { put("loginid", acc.id); put("alias", AccountOnboarding.aliasFrom(lbl.ifBlank { "deriv_${acc.id}" })); put("label", lbl) } }, submit)
                Field("Alias", alias, { alias = it.lowercase() }, error = AccountOnboarding.validateAlias(alias))
                Field("API token (from app.deriv.com → API token, scopes read + trade)", token, { token = it }, secret = true)
                Action("Save token and verify", !busy && token.isNotBlank() && AccountOnboarding.validateAlias(alias) == null) {
                    submit("account_upsert", buildJsonObject { put("alias", alias); put("broker", "DERIV"); put("server", appId); put("label", "Deriv $alias") }) { up ->
                        if (up.ok) submit("account_credentials", buildJsonObject { put("alias", alias); put("secrets", buildJsonObject { put("DERIV_API_TOKEN", token); put("DERIV_APP_ID", appId) }) }) { cr ->
                            token = ""
                            if (cr.ok) submit("account_verify", buildJsonObject { put("alias", alias) }) {}
                        }
                    }
                }
            }
        }
        VanPanel(header = { Text("Create a new Deriv demo account", style = tokens.type.headline, color = tokens.color.textPrimary) }) {
            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                Field("Email", email, { email = it }, keyboard = KeyboardType.Email, error = if (email.isBlank()) null else AccountOnboarding.validateEmail(email))
                Action(if (codeSent) "Resend verification code" else "Send verification code", !busy && AccountOnboarding.validateEmail(email) == null) {
                    submit("deriv_verify_email", buildJsonObject { put("email", email); put("app_id", appId) }) { if (it.ok) codeSent = true }
                }
                if (codeSent) {
                    Field("Verification code from the email", code, { code = it.trim() })
                    Field("New account password", password, { password = it }, secret = true, error = if (password.isBlank()) null else AccountOnboarding.validatePassword(password))
                    Field("Residence (ISO code, e.g. zw)", residence, { residence = it.lowercase() })
                    Field("Alias", alias, { alias = it.lowercase() }, error = AccountOnboarding.validateAlias(alias))
                    Action("Create demo account", !busy && code.isNotBlank() && AccountOnboarding.validatePassword(password) == null && residence.length == 2, solid = true) {
                        submit("deriv_create_demo", buildJsonObject { put("alias", alias); put("email", email); put("verification_code", code); put("client_password", password); put("residence", residence); put("app_id", appId) }) { password = ""; code = "" }
                    }
                }
            }
        }
    }
}

@Composable
private fun CtraderForm(ctx: Context, busy: Boolean, submit: (String, JsonObject, (AccountOnboarding.ActionOutcome) -> Unit) -> Unit) {
    val tokens = LocalVanTokens.current
    var clientId by remember { mutableStateOf("") }
    var clientSecret by remember { mutableStateOf("") }
    var accessToken by remember { mutableStateOf("") }
    var refreshToken by remember { mutableStateOf("") }
    var ctid by remember { mutableStateOf("") }
    var alias by remember { mutableStateOf("ctrader_demo") }
    var live by remember { mutableStateOf(false) }
    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
        VanPanel(header = { Text("cTrader application (once)", style = tokens.type.headline, color = tokens.color.textPrimary) }) {
            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                Text("Register an application at openapi.ctrader.com and paste its credentials. Its redirect URI must be the gateway callback shown after the first sign-in.", style = tokens.type.label, color = tokens.color.textTertiary)
                Field("Client id", clientId, { clientId = it.trim() })
                Field("Client secret", clientSecret, { clientSecret = it.trim() }, secret = true)
            }
        }
        VanPanel(header = { Text("Link with cTrader ID (browser)", style = tokens.type.headline, color = tokens.color.textPrimary) }) {
            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                OAuthLink(
                    ctx, busy, buildJsonObject { put("broker", "ctrader"); put("client_id", clientId); put("client_secret", clientSecret) }, "ctrader_link",
                    { acc, lbl -> buildJsonObject { put("ctid_trader_account_id", acc.id.toLongOrNull() ?: 0L); put("is_live", !acc.demo); put("alias", AccountOnboarding.aliasFrom(lbl.ifBlank { "ctrader_${acc.id}" })); put("label", lbl); put("currency", acc.currency) } }, submit,
                )
                Text("No cTrader account yet? Open one with the broker's cTrader app (FP Markets, IC Markets, Pepperstone…), then sign in here.", style = tokens.type.label, color = tokens.color.textTertiary)
            }
        }
        VanPanel(header = { Text("Or paste tokens (cTrader Open API playground)", style = tokens.type.headline, color = tokens.color.textPrimary) }) {
            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                Field("Access token", accessToken, { accessToken = it.trim() }, secret = true)
                Field("Refresh token", refreshToken, { refreshToken = it.trim() }, secret = true)
                Field("ctidTraderAccountId", ctid, { ctid = it.trim() }, keyboard = KeyboardType.Number)
                Field("Alias", alias, { alias = it.lowercase() }, error = AccountOnboarding.validateAlias(alias))
                TradingTabs(listOf("Demo", "Live"), if (live) "Live" else "Demo") { live = it == "Live" }
                Action("Link and verify", !busy && clientId.isNotBlank() && clientSecret.isNotBlank() && accessToken.isNotBlank() && ctid.isNotBlank()) {
                    submit("ctrader_link", buildJsonObject { put("alias", alias); put("client_id", clientId); put("client_secret", clientSecret); put("access_token", accessToken); put("refresh_token", refreshToken); put("ctid_trader_account_id", ctid.toLongOrNull() ?: 0L); put("is_live", live); put("label", "cTrader $alias") }) { out ->
                        accessToken = ""; refreshToken = ""; clientSecret = ""
                        if (out.ok) submit("account_verify", buildJsonObject { put("alias", alias) }) {}
                    }
                }
            }
        }
    }
}

@Composable
private fun Mt5EaForm(ctx: Context, busy: Boolean, submit: (String, JsonObject, (AccountOnboarding.ActionOutcome) -> Unit) -> Unit) {
    val tokens = LocalVanTokens.current
    var login by remember { mutableStateOf("") }
    var server by remember { mutableStateOf("") }
    var label by remember { mutableStateOf("") }
    var alias by remember { mutableStateOf("mt5_ea") }
    var issued by remember { mutableStateOf<AccountOnboarding.ActionOutcome?>(null) }
    VanPanel(header = { Text("MT5 account served by VanBridgeEA", style = tokens.type.headline, color = tokens.color.textPrimary) }) {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            Text(
                "The MT5 login and password stay in the terminal (desktop or MetaQuotes VPS). Van issues a signing key you paste into the EA; the EA pulls commands from van-trading-core. No Windows machine is needed on Van's side.",
                style = tokens.type.label, color = tokens.color.textTertiary,
            )
            Field("MT5 login", login, { login = it.trim() }, keyboard = KeyboardType.Number, error = if (login.isBlank()) null else AccountOnboarding.validateMt5Login(login))
            Field("Broker server (as shown in MT5)", server, { server = it.trim() })
            Field("Label", label, { label = it; alias = AccountOnboarding.aliasFrom(it.ifBlank { "mt5_ea" }) })
            Field("Alias", alias, { alias = it.lowercase() }, error = AccountOnboarding.validateAlias(alias))
            Action("Register and issue EA signing key", !busy && AccountOnboarding.validateMt5Login(login) == null && server.isNotBlank(), solid = true) {
                submit("mt5_ea_issue_key", buildJsonObject { put("alias", alias); put("login", login); put("server", server); put("label", label) }) { issued = it }
            }
            issued?.signingKey?.let { key ->
                Text("EA inputs (shown once)", style = tokens.type.label, color = tokens.color.forStatusRole(StatusSemantics.ROLE_EVENT_RISK))
                (issued?.eaInputs ?: emptyMap()).forEach { (k, v) -> Text("$k = $v", style = tokens.type.data, color = tokens.color.textSecondary) }
                Action("Copy signing key", true) { copy(ctx, "VanBridgeEA SigningKey", key) }
                Text("Next: attach VanBridgeEA.mq5 to a chart, allow WebRequest for the bridge URL, paste these inputs, then tap Verify below once the EA is polling.", style = tokens.type.label, color = tokens.color.textTertiary)
                Action("Verify EA is polling", !busy) { submit("account_verify", buildJsonObject { put("alias", alias) }) {} }
            }
        }
    }
}

@Composable
private fun PaperForm(busy: Boolean, submit: (String, JsonObject, (AccountOnboarding.ActionOutcome) -> Unit) -> Unit) {
    val tokens = LocalVanTokens.current
    var alias by remember { mutableStateOf("paper_lab") }
    var currency by remember { mutableStateOf("USD") }
    VanPanel(header = { Text("Paper account", style = tokens.type.headline, color = tokens.color.textPrimary) }) {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            Field("Alias", alias, { alias = it.lowercase() }, error = AccountOnboarding.validateAlias(alias))
            Field("Currency", currency, { currency = it.uppercase() })
            Action("Create paper account", !busy && AccountOnboarding.validateAlias(alias) == null) {
                submit("account_upsert", buildJsonObject { put("alias", alias); put("broker", "PAPER"); put("currency", currency); put("label", "Paper $alias") }) {}
            }
        }
    }
}
