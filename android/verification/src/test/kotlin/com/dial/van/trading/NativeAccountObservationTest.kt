package com.dial.van.trading

import kotlinx.serialization.json.*
import kotlin.test.*

class NativeAccountObservationTest {
    private fun original() = buildJsonObject {
        put("state", "OBSERVED"); put("schema", "vati.mt5-account-observation/1"); put("provider", "MT5")
        put("account_alias", "native"); put("login", 9007199254740993L); put("server", "Broker-Demo")
        put("currency", "USD"); put("demo", true); put("execution_authority", false)
        put("source_kind", "MT5_SIGNED_MTLS_READ"); put("source_nonce", "original-query")
        put("source_received_at_ms", 9007199254740993L); put("observed_at_ms", 9007199254740994L)
        put("received_at_ms", 9007199254740995L); put("scope_hash", "a".repeat(64))
        put("source_ref", "b".repeat(64)); put("snapshot_ref", "c".repeat(64))
        put("reported_equity", "10250.5000000001"); put("balance", "10000.0000000000")
        put("credit", "250.5000000000"); put("risk_equity", "10000.0000000001")
        put("valuation_state", "CREDIT_EXCLUDED"); put("money_basis", "NATIVE_DOUBLE_TEXT_NOT_SETTLED_MINOR_UNITS")
    }
    private fun changed(key: String, value: JsonElement) = JsonObject(original().toMutableMap().apply { put(key, value) })

    @Test fun existingAccountModelRetainsExactOriginalIdentityMoneyAndClocks() {
        val card = AccountCard.from(buildJsonObject { put("alias", "native"); put("native_account_observation", original()) })
        val value = card.nativeObservation
        assertEquals("OBSERVED", value.state); assertEquals("9007199254740993", value.nativeLogin)
        assertEquals(9007199254740994L, value.observedAtMs); assertEquals("10000.0000000001", value.riskEquity)
        assertEquals("250.5000000000", value.credit); assertFalse(value.executionAuthority)
    }

    @Test fun unavailableCreditKeepsOriginalMoneyWithoutInventingRiskEquity() {
        val o = JsonObject(original().toMutableMap().apply {
            put("credit", JsonNull); put("risk_equity", JsonNull); put("valuation_state", JsonPrimitive("CREDIT_UNAVAILABLE"))
        })
        val value = NativeAccountObservation.from(o)
        assertEquals("OBSERVED", value.state); assertNull(value.riskEquity); assertNull(value.credit)
        assertEquals("10250.5000000001", value.reportedEquity); assertFalse(value.executionAuthority)
    }

    @Test fun negativeCreditRemainsAnUnqualifiedLiability() {
        val o = JsonObject(original().toMutableMap().apply {
            put("credit", JsonPrimitive("-10.0001")); put("risk_equity", JsonNull)
            put("valuation_state", JsonPrimitive("CREDIT_LIABILITY_UNQUALIFIED"))
        })
        val value = NativeAccountObservation.from(o)
        assertEquals("OBSERVED", value.state); assertEquals("-10.0001", value.credit); assertNull(value.riskEquity)
    }

    @Test fun badAuthorityAmountsSourcesAndClocksCannotBecomeQualifiedFacts() {
        for ((key, value) in listOf(
            "execution_authority" to JsonPrimitive(true), "execution_authority" to JsonPrimitive(0),
            "reported_equity" to JsonPrimitive("NaN"), "credit" to JsonPrimitive(0),
            "risk_equity" to JsonPrimitive("999999"), "risk_equity" to JsonPrimitive("1e2147483647"),
            "observed_at_ms" to JsonPrimitive(true), "observed_at_ms" to JsonPrimitive("9007199254740994"),
            "received_at_ms" to JsonPrimitive(1), "login" to JsonPrimitive(1.5),
            "source_kind" to JsonPrimitive("LOG_IMPORT"), "snapshot_ref" to JsonPrimitive("missing"))) {
            assertEquals("UNAVAILABLE", NativeAccountObservation.from(changed(key, value)).state, key)
        }
    }

    @Test fun legacyAndExplicitUnavailableStatesRemainDistinct() {
        assertEquals("UNMEASURED", AccountCard.from(buildJsonObject {}).nativeObservation.state)
        val value = NativeAccountObservation.from(buildJsonObject { put("state", "UNAVAILABLE"); put("reason", "CURRENT_PROFILE_NATIVE_SCOPE_MISMATCH") })
        assertEquals("UNAVAILABLE", value.state); assertEquals("CURRENT_PROFILE_NATIVE_SCOPE_MISMATCH", value.reason)
        assertFalse(value.executionAuthority)
    }
}
