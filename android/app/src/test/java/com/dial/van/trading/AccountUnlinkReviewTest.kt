package com.dial.van.trading

import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

class AccountUnlinkReviewTest {
    private fun review(paper: Boolean = false): JsonObject = buildJsonObject {
        put("schema", "vati.account-review/1"); put("action", "account_remove"); put("after", JsonNull)
        put("before", buildJsonObject {
            put("alias", "fx_primary"); put("broker", if (paper) "PAPER" else "MT5"); put("currency", "USD")
            put("credential_ref", buildJsonObject { put("kind", "file") })
        })
        put("retirement", buildJsonObject {
            put("schema", "vati.local-unlink-review/1"); put("remote_account_closed", false); put("historical_data_retained", true)
            put("credential_cleanup",if (paper) "NONE" else "DELETE_MANAGED")
            put("retained_remote_funds", if (paper) JsonNull else buildJsonObject {
                put("balance", "100.25000001"); put("equity", "100.25000001"); put("currency", "USD")
            })
        })
    }

    @Test fun exactKnownFundsAndLocalScopeReachExistingConfirmation() {
        val text = AccountOnboarding.resolvedReviewText(review())!!
        assertTrue(text.contains("100.25000001 USD")); assertTrue(text.contains("does not close the broker account"))
        assertTrue(text.contains("history is retained")); assertTrue(text.contains("Unlink fx_primary"))
    }

    @Test fun paperHasNoInventedRemoteBalance() {
        val text = AccountOnboarding.resolvedReviewText(review(true))!!
        assertTrue(text.contains("no broker funds")); assertFalse(text.contains("balance 0"))
    }

    @Test fun incompleteOrContradictoryReviewCannotAuthorizeRemoval() {
        val source = review(); val facts = source["retirement"]!!.jsonObject
        for ((key, bad) in listOf("remote_account_closed" to JsonPrimitive(true),
            "remote_account_closed" to JsonPrimitive("false"), "historical_data_retained" to JsonPrimitive(false),
            "retained_remote_funds" to JsonNull)) {
            val altered = JsonObject(source + ("retirement" to JsonObject(facts + (key to bad))))
            assertNull(AccountOnboarding.resolvedReviewText(altered))
        }
    }

    @Test fun nonFiniteOrForeignCurrencyFundsCannotAuthorizeRemoval() {
        val source = review(); val facts = source["retirement"]!!.jsonObject
        val funds = facts["retained_remote_funds"]!!.jsonObject
        for ((key, bad) in listOf("balance" to "NaN", "equity" to "Infinity", "currency" to "EUR")) {
            val altered = JsonObject(source + ("retirement" to JsonObject(facts +
                ("retained_remote_funds" to JsonObject(funds + (key to JsonPrimitive(bad)))))))
            assertNull(AccountOnboarding.resolvedReviewText(altered))
        }
    }

    @Test fun successfulOutcomeClearlyDistinguishesLocalUnlink() {
        val result = AccountOnboarding.parseOutcome("account_remove",
            """{"removed":true,"remote_account_closed":false,"historical_data_retained":true}""",200)
        assertTrue(result.ok); assertTrue(result.message.contains("unlinked locally"))
        assertTrue(result.message.contains("funds remain"))
    }

    @Test fun sharedAndExternalCredentialsAreExplicitlyRetained() {
        val source=review();val facts=source["retirement"]!!.jsonObject
        for ((kind,expected) in listOf("KEEP_SHARED" to "Shared credentials are kept", "KEEP_EXTERNAL" to "Externally managed credentials are retained")) {
            val changed=JsonObject(source+("retirement" to JsonObject(facts+("credential_cleanup" to JsonPrimitive(kind)))))
            val text=AccountOnboarding.resolvedReviewText(changed)!!
            assertTrue(text.contains(expected));assertFalse(text.contains("credentials will be removed"))
        }
        assertNull(AccountOnboarding.resolvedReviewText(JsonObject(source+("retirement" to JsonObject(facts-"credential_cleanup")))))
    }
}
