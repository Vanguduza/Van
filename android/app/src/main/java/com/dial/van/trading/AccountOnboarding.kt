package com.dial.van.trading

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.security.MessageDigest
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * In-app account onboarding (Rev 5 Part B): the owner types account details and credentials
 * in the Van app; the app signs each action with the enrolled device secret and the gateway
 * forwards it to the trading VM. Credentials transit once and are never kept on the phone.
 *
 * The canonical form must equal the gateway's: sorted keys, no spaces, UTF-8 unescaped
 * (Python json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=False)), then
 * "trading-account|device|issued|action|sha256hex(args)" under HMAC-SHA256 with the device secret.
 */
object AccountOnboarding {
    val ACTIONS = listOf("account_upsert", "account_credentials", "account_remove", "account_verify", "deriv_verify_email", "deriv_create_demo", "deriv_oauth_link", "ctrader_discover", "ctrader_link", "mt5_ea_issue_key", "oauth_start", "oauth_pending")

    fun canonicalJson(el: JsonElement): String = when (el) {
        is JsonNull -> "null"
        is JsonPrimitive -> if (el.isString) quote(el.content) else el.content
        is JsonArray -> el.joinToString(",", "[", "]") { canonicalJson(it) }
        is JsonObject -> el.entries.sortedBy { it.key }.joinToString(",", "{", "}") { quote(it.key) + ":" + canonicalJson(it.value) }
    }

    /** Python json.dumps escaping with ensure_ascii=False: only the quote, backslash and control characters are escaped. */
    private fun quote(s: String): String {
        val sb = StringBuilder("\"")
        for (ch in s) {
            when {
                ch == '"' -> sb.append("\\\"")
                ch == '\\' -> sb.append("\\\\")
                ch == '\n' -> sb.append("\\n")
                ch == '\r' -> sb.append("\\r")
                ch == '\t' -> sb.append("\\t")
                ch.code < 0x20 -> sb.append("\\u").append(String.format("%04x", ch.code))
                else -> sb.append(ch)
            }
        }
        return sb.append("\"").toString()
    }

    fun sha256Hex(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    fun canonicalAction(deviceId: String, issuedAtUnix: Long, action: String, args: JsonObject): String =
        listOf("trading-account", deviceId, issuedAtUnix.toString(), action, sha256Hex(canonicalJson(args).toByteArray(Charsets.UTF_8))).joinToString("|")

    fun sign(deviceSecret: String, deviceId: String, issuedAtUnix: Long, action: String, args: JsonObject): String {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(deviceSecret.toByteArray(Charsets.UTF_8), "HmacSHA256"))
        return mac.doFinal(canonicalAction(deviceId, issuedAtUnix, action, args).toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
    }

    /** Request body for POST /v1/trading/accounts/action. */
    /**
     * Actions that only read state. Everything else changes an account or a credential and
     * needs a gateway-issued challenge signed inside the biometric (P1-SEC-004).
     *
     * Stated as the read-only set rather than the guarded set, so an action added to
     * ACTIONS is guarded by default instead of by somebody remembering. The gateway keeps
     * the same list and refuses independently; this is here so the app does not send a
     * request it knows will be refused.
     */
    val READ_ONLY_ACTIONS = setOf("account_verify", "oauth_pending", "ctrader_discover")

    fun requiresOwnerApproval(action: String): Boolean =
        action in ACTIONS && action !in READ_ONLY_ACTIONS

    /** What the owner is actually approving, so the prompt is not a generic "confirm". */
    fun approvalSubtitle(action: String): String = when (action) {
        "account_upsert" -> "Add or change a trading account"
        "account_credentials" -> "Store broker credentials for this account"
        "account_remove" -> "Remove a trading account"
        "deriv_verify_email" -> "Send a Deriv verification email"
        "deriv_create_demo" -> "Create a Deriv demo account"
        "deriv_oauth_link" -> "Link a Deriv account"
        "ctrader_link" -> "Link a cTrader account"
        "mt5_ea_issue_key" -> "Issue a new MT5 bridge signing key"
        "oauth_start" -> "Begin linking a broker account"
        else -> "Confirm trading account change"
    }

    fun requestBody(
        deviceSecret: String,
        deviceId: String,
        issuedAtUnix: Long,
        action: String,
        args: JsonObject,
        approvalProof: JsonObject? = null,
    ): JsonObject {
        require(action in ACTIONS) { "unknown account action $action" }
        return buildJsonObject {
            put("device_id", deviceId)
            put("issued_at_unix", issuedAtUnix)
            put("signature", sign(deviceSecret, deviceId, issuedAtUnix, action, args))
            put("action", action)
            put("args", args)
            if (approvalProof != null) put("approval_proof", approvalProof)
        }
    }

    // ------------------------------------------------------------ forms
    enum class Broker(val code: String, val label: String, val blurb: String) {
        DERIV("DERIV", "Deriv", "Sign in with Deriv, paste an API token, or create a new demo account"),
        CTRADER("CTRADER", "cTrader", "Link a cTrader ID account (FP Markets, IC Markets, Pepperstone and others) through cTrader Open API"),
        MT5_EA("MT5_EA", "MT5 via Expert Advisor", "Any MT5 account; VanBridgeEA runs in the terminal or on a MetaQuotes VPS, no Windows needed here"),
        PAPER("PAPER", "Paper", "Simulated account for strategy lab work"),
    }

    private val aliasRe = Regex("^[a-z0-9_]{3,32}$")

    fun aliasFrom(label: String): String = label.lowercase().replace(Regex("[^a-z0-9]+"), "_").trim('_').take(32).let { if (it.length < 3) "acct_$it" else it }

    fun validateAlias(alias: String): String? = if (aliasRe.matches(alias)) null else "Alias must be 3 to 32 characters: a-z, 0-9, _"

    fun validateEmail(email: String): String? = if (Regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$").matches(email)) null else "Enter a valid email"

    fun validatePassword(pw: String): String? = when {
        pw.length < 8 -> "At least 8 characters"
        !pw.any { it.isDigit() } || !pw.any { it.isLetter() } -> "Use letters and numbers"
        else -> null
    }

    fun validateMt5Login(login: String): String? = if (login.all { it.isDigit() } && login.length in 4..12) null else "MT5 login is a number"

    /** Secret keys the VM accepts per broker (mirrors commander.accounts.BROKER_SECRET_KEYS). */
    fun secretKeys(broker: Broker): List<String> = when (broker) {
        Broker.DERIV -> listOf("DERIV_API_TOKEN", "DERIV_APP_ID")
        Broker.CTRADER -> listOf("CTRADER_CLIENT_ID", "CTRADER_CLIENT_SECRET", "CTRADER_ACCESS_TOKEN", "CTRADER_REFRESH_TOKEN")
        Broker.MT5_EA -> listOf("BRIDGE_SIGNING_KEY")
        Broker.PAPER -> emptyList()
    }

    // ------------------------------------------------------------ responses
    data class ActionOutcome(val ok: Boolean, val message: String, val account: AccountCard? = null, val signingKey: String? = null, val eaInputs: Map<String, String> = emptyMap(), val state: String? = null, val url: String? = null, val raw: JsonObject? = null)

    fun parseOutcome(action: String, body: String, httpCode: Int): ActionOutcome {
        val o = parseObject(body) ?: return ActionOutcome(false, if (httpCode in 200..299) "Unreadable gateway reply" else "Gateway error $httpCode")
        if (httpCode !in 200..299) return ActionOutcome(false, o.str("detail") ?: "Gateway error $httpCode", raw = o)
        val acct = o.obj("account")?.let(AccountCard::from)
        return when (action) {
            "account_verify" -> ActionOutcome(o.bool("ok") == true, if (o.bool("ok") == true) "Connected. Equity ${o.str("equity") ?: "?"} ${o.str("currency") ?: ""}" else (o.str("detail") ?: "Verification failed"), raw = o)
            "mt5_ea_issue_key" -> ActionOutcome(true, "Account registered. Copy the signing key into VanBridgeEA now: it is shown once.", acct, o.str("signing_key"), o.obj("ea_inputs")?.entries?.mapNotNull { e -> (e.value as? JsonPrimitive)?.content?.let { e.key to it } }?.toMap() ?: emptyMap(), raw = o)
            "oauth_start" -> ActionOutcome(true, o.str("note") ?: "Continue in the browser", state = o.str("state"), url = o.str("url"), raw = o)
            "oauth_pending" -> ActionOutcome(o.bool("ready") == true, if (o.bool("expired") == true) "Link expired; start again" else if (o.bool("ready") == true) "Accounts found" else "Waiting for the browser sign-in", raw = o)
            "deriv_verify_email" -> ActionOutcome(o.bool("sent") == true, if (o.bool("sent") == true) "Verification code sent to ${o.str("email")}" else "Could not send the code", raw = o)
            "account_remove" -> ActionOutcome(o.bool("removed") == true, "Account removed", raw = o)
            "account_credentials" -> ActionOutcome(true, "Stored: ${o.strList("stored_keys").joinToString()}", raw = o)
            else -> ActionOutcome(true, if (acct != null) "${acct.label} ${acct.safety.label}" else "Done", acct, raw = o)
        }
    }

    data class DiscoveredAccount(val id: String, val label: String, val demo: Boolean, val currency: String)

    fun parseDiscovered(o: JsonObject?): List<DiscoveredAccount> {
        if (o == null) return emptyList()
        return o.arr("accounts").map { a ->
            val ct = a.str("ctid_trader_account_id")
            if (ct != null) DiscoveredAccount(ct, "${a.str("broker") ?: "cTrader"} ${a.str("trader_login") ?: ct} (${a.str("environment") ?: if (a.bool("is_live") == true) "live" else "demo"})", a.bool("is_live") != true, "USD")
            else DiscoveredAccount(a.str("loginid") ?: "?", "Deriv ${a.str("loginid")} ${a.str("currency") ?: ""}", a.bool("demo") == true, a.str("currency") ?: "USD")
        }
    }
}
