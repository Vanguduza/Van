package com.dial.van.trading.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.fragment.app.FragmentActivity
import com.dial.van.VanApplication
import com.dial.van.security.BiometricGate
import com.dial.van.trading.AccountOnboarding
import com.dial.van.trading.AccountOnboarding.Broker
import com.dial.van.visual.VanGlassTokens
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Add / link a trading account from the app (owner direction: no CLI). Every submit is gated by
 * the owner biometric (A4) and signed with the device secret; credentials are sent once to the
 * gateway, which forwards them to the trading VM, and are cleared from these fields afterwards.
 * Deriv and cTrader can also be linked by signing in through the browser (OAuth), and a Deriv
 * demo account can be created here just like inside MT5.
 */
@Composable
fun AccountOnboardingScreen(env: ScreenEnv, padding: PaddingValues, app: VanApplication, onDone: () -> Unit) {
    val ctx = LocalContext.current
    val activity = ctx as? FragmentActivity
    val gate = remember(activity) { activity?.let { BiometricGate(it) } }
    val scope = rememberCoroutineScope()
    var broker by remember { mutableStateOf(Broker.DERIV) }
    var status by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }

    fun submit(action: String, args: JsonObject, then: (AccountOnboarding.ActionOutcome) -> Unit = {}) {
        val run: () -> Unit = {
            busy = true; status = "Signing and sending…"
            scope.launch {
                val outcome = runCatching { app.gatewayClient.tradingAccountAction(action, args) }
                    .fold(onSuccess = { (code, body) -> AccountOnboarding.parseOutcome(action, body, code) }, onFailure = { AccountOnboarding.ActionOutcome(false, "Gateway unreachable: ${it.message?.take(80)}") })
                status = outcome.message; busy = false; then(outcome)
            }
        }
        // A4: owner biometric before any account or credential change; read-only polls skip the prompt.
        if (action == "oauth_pending" || action == "account_verify" || gate == null) run() else gate.requestA4Approval(subtitle = "Confirm trading account change", onApproved = run, onDenied = { status = "Biometric denied; nothing was sent." })
    }

    LazyColumn(modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 14.dp), verticalArrangement = Arrangement.spacedBy(10.dp), contentPadding = PaddingValues(vertical = 10.dp)) {
        item { Text("Add trading account", color = Color.White, fontSize = 20.sp, fontWeight = FontWeight.Bold) }
        item { TabRowChips(Broker.entries.map { it.label }, broker.label) { l -> broker = Broker.entries.first { it.label == l } } }
        item { Text(broker.blurb, color = TradingColors.muted, fontSize = 11.sp) }
        item {
            when (broker) {
                Broker.DERIV -> DerivForm(env, ctx, busy, ::submit)
                Broker.CTRADER -> CtraderForm(env, ctx, busy, ::submit)
                Broker.MT5_EA -> Mt5EaForm(env, ctx, busy, ::submit)
                Broker.PAPER -> PaperForm(env, busy, ::submit)
            }
        }
        if (status.isNotEmpty()) item { Text(status, color = if (status.startsWith("Gateway") || status.contains("failed") || status.contains("denied")) TradingColors.warning else TradingColors.text, fontSize = 12.sp) }
        item { Text("Done →", color = TradingColors.accent, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.clickable(onClick = onDone)) }
        item { Text("Credentials are sent once, over the device-signed channel, to van-trading-core's 0600 secrets store. They are never kept on this phone or in the gateway. A real account links as READ ONLY until an owner-signed mandate changes its mode.", color = TradingColors.muted, fontSize = 9.sp) }
    }
}

@Composable
private fun Field(label: String, value: String, onChange: (String) -> Unit, secret: Boolean = false, keyboard: KeyboardType = KeyboardType.Text, error: String? = null) {
    OutlinedTextField(
        value = value, onValueChange = onChange, label = { Text(label, fontSize = 11.sp) }, singleLine = true, isError = error != null, supportingText = error?.let { { Text(it, fontSize = 10.sp) } },
        visualTransformation = if (secret) PasswordVisualTransformation() else androidx.compose.ui.text.input.VisualTransformation.None, keyboardOptions = KeyboardOptions(keyboardType = if (secret) KeyboardType.Password else keyboard),
        colors = OutlinedTextFieldDefaults.colors(focusedTextColor = Color.White, unfocusedTextColor = Color.White, focusedBorderColor = TradingColors.accent, unfocusedBorderColor = Color(0xFF3A4656), focusedLabelColor = TradingColors.accent, unfocusedLabelColor = TradingColors.muted),
        modifier = Modifier.fillMaxWidth(),
    )
}

@Composable
private fun Action(text: String, enabled: Boolean, solid: Boolean = false, onClick: () -> Unit) {
    Button(onClick = onClick, enabled = enabled, colors = ButtonDefaults.buttonColors(containerColor = if (solid) Color(VanGlassTokens.ACCENT_AMBER) else TradingColors.accent.copy(alpha = 0.18f), contentColor = if (solid) Color(0xFF10151F) else Color(VanGlassTokens.EDGE_CYAN)),
           shape = RoundedCornerShape(VanGlassTokens.CORNER_RADIUS_DP.dp), modifier = Modifier.fillMaxWidth()) { Text(text, fontWeight = if (solid) FontWeight.Bold else FontWeight.SemiBold) }
}

private fun openBrowser(ctx: Context, url: String) = ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
private fun copy(ctx: Context, label: String, text: String) = (ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText(label, text))

/** Browser sign-in shared by Deriv and cTrader: start → open → poll pending → pick account → link. */
@Composable
private fun OAuthLink(ctx: Context, busy: Boolean, startArgs: JsonObject, linkAction: String, linkArgs: (AccountOnboarding.DiscoveredAccount, String) -> JsonObject, submit: (String, JsonObject, (AccountOnboarding.ActionOutcome) -> Unit) -> Unit) {
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
    if (polling) Text("Finish the sign-in in the browser, then return here. Checking…", color = TradingColors.muted, fontSize = 11.sp)
    if (found.isNotEmpty()) {
        Field("Label (optional)", label, { label = it })
        found.forEach { acc ->
            Row(modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(Color.White.copy(alpha = 0.05f)).clickable(enabled = !busy) {
                val s = state ?: return@clickable
                submit(linkAction, JsonObject(linkArgs(acc, label).toMutableMap().apply { put("state", JsonPrimitive(s)) })) { if (it.ok) found = emptyList() }
            }.padding(10.dp)) {
                Text(acc.label, color = Color.White, fontSize = 12.sp, modifier = Modifier.weight(1f)); Chip(if (acc.demo) "DEMO" else "LIVE → READ ONLY", if (acc.demo) 0xFFFFB300L else 0xFFFF5252L)
            }
        }
    }
}

@Composable
private fun DerivForm(env: ScreenEnv, ctx: Context, busy: Boolean, submit: (String, JsonObject, (AccountOnboarding.ActionOutcome) -> Unit) -> Unit) {
    var appId by remember { mutableStateOf("1089") }
    var alias by remember { mutableStateOf("deriv_demo") }
    var token by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var code by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var residence by remember { mutableStateOf("zw") }
    var codeSent by remember { mutableStateOf(false) }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        SectionPanel("Link an existing Deriv account", env.glass) {
            Field("Deriv app id", appId, { appId = it }, keyboard = KeyboardType.Number)
            OAuthLink(ctx, busy, buildJsonObject { put("broker", "deriv"); put("app_id", appId) }, "deriv_oauth_link", { acc, lbl -> buildJsonObject { put("loginid", acc.id); put("alias", AccountOnboarding.aliasFrom(lbl.ifBlank { "deriv_${acc.id}" })); put("label", lbl) } }, submit)
            Spacer(Modifier.height(6.dp))
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
        SectionPanel("Create a new Deriv demo account", env.glass) {
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

@Composable
private fun CtraderForm(env: ScreenEnv, ctx: Context, busy: Boolean, submit: (String, JsonObject, (AccountOnboarding.ActionOutcome) -> Unit) -> Unit) {
    var clientId by remember { mutableStateOf("") }
    var clientSecret by remember { mutableStateOf("") }
    var accessToken by remember { mutableStateOf("") }
    var refreshToken by remember { mutableStateOf("") }
    var ctid by remember { mutableStateOf("") }
    var alias by remember { mutableStateOf("ctrader_demo") }
    var live by remember { mutableStateOf(false) }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        SectionPanel("cTrader application (once)", env.glass) {
            Text("Register an application at openapi.ctrader.com and paste its credentials. Its redirect URI must be the gateway callback shown after the first sign-in.", color = TradingColors.muted, fontSize = 10.sp)
            Field("Client id", clientId, { clientId = it.trim() }); Field("Client secret", clientSecret, { clientSecret = it.trim() }, secret = true)
        }
        SectionPanel("Link with cTrader ID (browser)", env.glass) {
            OAuthLink(ctx, busy, buildJsonObject { put("broker", "ctrader"); put("client_id", clientId); put("client_secret", clientSecret) }, "ctrader_link",
                { acc, lbl -> buildJsonObject { put("ctid_trader_account_id", acc.id.toLongOrNull() ?: 0L); put("is_live", !acc.demo); put("alias", AccountOnboarding.aliasFrom(lbl.ifBlank { "ctrader_${acc.id}" })); put("label", lbl); put("currency", acc.currency) } }, submit)
            Text("No cTrader account yet? Open one with the broker's cTrader app (FP Markets, IC Markets, Pepperstone…), then sign in here.", color = TradingColors.muted, fontSize = 10.sp)
        }
        SectionPanel("Or paste tokens (cTrader Open API playground)", env.glass) {
            Field("Access token", accessToken, { accessToken = it.trim() }, secret = true); Field("Refresh token", refreshToken, { refreshToken = it.trim() }, secret = true)
            Field("ctidTraderAccountId", ctid, { ctid = it.trim() }, keyboard = KeyboardType.Number); Field("Alias", alias, { alias = it.lowercase() }, error = AccountOnboarding.validateAlias(alias))
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) { TabRowChips(listOf("Demo", "Live"), if (live) "Live" else "Demo") { live = it == "Live" } }
            Action("Link and verify", !busy && clientId.isNotBlank() && clientSecret.isNotBlank() && accessToken.isNotBlank() && ctid.isNotBlank()) {
                submit("ctrader_link", buildJsonObject { put("alias", alias); put("client_id", clientId); put("client_secret", clientSecret); put("access_token", accessToken); put("refresh_token", refreshToken); put("ctid_trader_account_id", ctid.toLongOrNull() ?: 0L); put("is_live", live); put("label", "cTrader $alias") }) { out ->
                    accessToken = ""; refreshToken = ""; clientSecret = ""
                    if (out.ok) submit("account_verify", buildJsonObject { put("alias", alias) }) {}
                }
            }
        }
    }
}

@Composable
private fun Mt5EaForm(env: ScreenEnv, ctx: Context, busy: Boolean, submit: (String, JsonObject, (AccountOnboarding.ActionOutcome) -> Unit) -> Unit) {
    var login by remember { mutableStateOf("") }
    var server by remember { mutableStateOf("") }
    var label by remember { mutableStateOf("") }
    var alias by remember { mutableStateOf("mt5_ea") }
    var issued by remember { mutableStateOf<AccountOnboarding.ActionOutcome?>(null) }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        SectionPanel("MT5 account served by VanBridgeEA", env.glass) {
            Text("The MT5 login and password stay in the terminal (desktop or MetaQuotes VPS). Van issues a signing key you paste into the EA; the EA pulls commands from van-trading-core. No Windows machine is needed on Van's side.", color = TradingColors.muted, fontSize = 10.sp)
            Field("MT5 login", login, { login = it.trim() }, keyboard = KeyboardType.Number, error = if (login.isBlank()) null else AccountOnboarding.validateMt5Login(login))
            Field("Broker server (as shown in MT5)", server, { server = it.trim() }); Field("Label", label, { label = it; alias = AccountOnboarding.aliasFrom(it.ifBlank { "mt5_ea" }) })
            Field("Alias", alias, { alias = it.lowercase() }, error = AccountOnboarding.validateAlias(alias))
            Action("Register and issue EA signing key", !busy && AccountOnboarding.validateMt5Login(login) == null && server.isNotBlank(), solid = true) {
                submit("mt5_ea_issue_key", buildJsonObject { put("alias", alias); put("login", login); put("server", server); put("label", label) }) { issued = it }
            }
            issued?.signingKey?.let { key ->
                Spacer(Modifier.height(6.dp))
                Text("EA inputs (shown once)", color = TradingColors.warning, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                (issued?.eaInputs ?: emptyMap()).forEach { (k, v) -> Text("$k = $v", color = TradingColors.text, fontSize = 10.sp, fontFamily = FontFamily.Monospace) }
                Action("Copy signing key", true) { copy(ctx, "VanBridgeEA SigningKey", key) }
                Text("Next: attach VanBridgeEA.mq5 to a chart, allow WebRequest for the bridge URL, paste these inputs, then tap Verify below once the EA is polling.", color = TradingColors.muted, fontSize = 10.sp)
                Action("Verify EA is polling", !busy) { submit("account_verify", buildJsonObject { put("alias", alias) }) {} }
            }
        }
    }
}

@Composable
private fun PaperForm(env: ScreenEnv, busy: Boolean, submit: (String, JsonObject, (AccountOnboarding.ActionOutcome) -> Unit) -> Unit) {
    var alias by remember { mutableStateOf("paper_lab") }
    var currency by remember { mutableStateOf("USD") }
    SectionPanel("Paper account", env.glass) {
        Field("Alias", alias, { alias = it.lowercase() }, error = AccountOnboarding.validateAlias(alias)); Field("Currency", currency, { currency = it.uppercase() })
        Action("Create paper account", !busy && AccountOnboarding.validateAlias(alias) == null) { submit("account_upsert", buildJsonObject { put("alias", alias); put("broker", "PAPER"); put("currency", currency); put("label", "Paper $alias") }) {} }
    }
}
