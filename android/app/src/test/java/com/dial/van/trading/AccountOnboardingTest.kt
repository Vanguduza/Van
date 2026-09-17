package com.dial.van.trading

import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AccountOnboardingTest {
    private val args = buildJsonObject {
        put("alias", "deriv_demo"); put("broker", "DERIV"); put("label", "D\u00e9j\u00e0 vu")
        put("nested", buildJsonObject { put("z", 1); put("a", buildJsonArray { add(JsonPrimitive(1)); add(JsonPrimitive("two")); add(JsonPrimitive(true)); add(JsonNull) }) })
    }

    @Test
    fun canonicalJsonAndSignatureMatchTheGatewayVector() {
        // vector produced by the gateway's own canonical_action + HMAC (backend/van_gateway/trading/accounts.py)
        assertEquals("{\"alias\":\"deriv_demo\",\"broker\":\"DERIV\",\"label\":\"Déjà vu\",\"nested\":{\"a\":[1,\"two\",true,null],\"z\":1}}", AccountOnboarding.canonicalJson(args))
        assertEquals("79cd8f3276f4ed282f8f3ec904f6d3e50ffd4df6061d52c2b9539dc4edce662a", AccountOnboarding.sign("s3cret-device", "dev1", 1758000000L, "account_upsert", args))
        val body = AccountOnboarding.requestBody("s3cret-device", "dev1", 1758000000L, "account_upsert", args)
        assertEquals("\"account_upsert\"", body["action"].toString())
        assertEquals("\"79cd8f3276f4ed282f8f3ec904f6d3e50ffd4df6061d52c2b9539dc4edce662a\"", body["signature"].toString())
    }

    @Test
    fun escapesLikePythonJsonDumps() {
        assertEquals("{\"a\":\"q\\\"b\\\\c\\n\"}", AccountOnboarding.canonicalJson(buildJsonObject { put("a", "q\"b\\c\n") }))
        assertEquals("{\"k\":\"\\t\"}", AccountOnboarding.canonicalJson(buildJsonObject { put("k", "\t") }))
        assertEquals("{\"a\":[],\"b\":2}", AccountOnboarding.canonicalJson(buildJsonObject { put("b", 2); put("a", buildJsonArray { }) }))
    }

    @Test
    fun formsValidateAndOutcomesParse() {
        assertEquals("fp_markets_demo", AccountOnboarding.aliasFrom("FP Markets Demo!"))
        assertNull(AccountOnboarding.validateAlias("mt5_ea")); assertNotNull(AccountOnboarding.validateAlias("Bad Alias"))
        assertNull(AccountOnboarding.validateEmail("owner@example.com")); assertNotNull(AccountOnboarding.validateEmail("nope"))
        assertNotNull(AccountOnboarding.validatePassword("short")); assertNotNull(AccountOnboarding.validatePassword("lettersonly")); assertNull(AccountOnboarding.validatePassword("Pa55word"))
        assertNull(AccountOnboarding.validateMt5Login("12345678")); assertNotNull(AccountOnboarding.validateMt5Login("abc"))
        assertEquals(listOf("BRIDGE_SIGNING_KEY"), AccountOnboarding.secretKeys(AccountOnboarding.Broker.MT5_EA))
        val key = AccountOnboarding.parseOutcome("mt5_ea_issue_key", "{\"account\":{\"alias\":\"mt5_ea\",\"broker\":\"MT5_EA\",\"safety_identity\":\"DEMO\",\"currency\":\"USD\",\"mode\":\"DEMO_TRADER\"},\"signing_key\":\"abc\",\"ea_inputs\":{\"Alias\":\"mt5_ea\",\"SigningKey\":\"abc\",\"BridgeUrl\":\"https://t\"}}", 200)
        assertTrue(key.ok); assertEquals("abc", key.signingKey); assertEquals("https://t", key.eaInputs["BridgeUrl"]); assertEquals(SafetyIdentity.DEMO, key.account!!.safety)
        val bad = AccountOnboarding.parseOutcome("account_upsert", "{\"detail\":\"alias must match [a-z0-9_]{3,32}\"}", 422)
        assertFalse(bad.ok); assertTrue(bad.message.startsWith("alias must match"))
        val start = AccountOnboarding.parseOutcome("oauth_start", "{\"state\":\"s1\",\"url\":\"https://oauth.deriv.com/x\",\"note\":\"n\"}", 200)
        assertEquals("s1", start.state); assertEquals("https://oauth.deriv.com/x", start.url)
        val pend = AccountOnboarding.parseOutcome("oauth_pending", "{\"ready\":true,\"broker\":\"deriv\",\"accounts\":[{\"loginid\":\"VRTC1\",\"currency\":\"USD\",\"demo\":true},{\"loginid\":\"CR2\",\"currency\":\"USD\",\"demo\":false}]}", 200)
        val disc = AccountOnboarding.parseDiscovered(pend.raw)
        assertEquals(listOf("VRTC1", "CR2"), disc.map { it.id }); assertTrue(disc[0].demo); assertFalse(disc[1].demo)
        val ct = AccountOnboarding.parseDiscovered(parseObject("{\"accounts\":[{\"ctid_trader_account_id\":12345,\"is_live\":false,\"trader_login\":5551234,\"broker\":\"FP Markets\",\"environment\":\"demo\"}]}"))
        assertEquals("12345", ct[0].id); assertEquals("FP Markets 5551234 (demo)", ct[0].label)
        assertFalse(AccountOnboarding.parseOutcome("oauth_pending", "{\"ready\":false,\"expired\":true}", 200).ok)
        assertTrue(AccountOnboarding.parseOutcome("account_verify", "{\"ok\":true,\"equity\":\"10000.00\",\"currency\":\"USD\"}", 200).message.contains("10000.00"))
    }
}
