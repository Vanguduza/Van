package com.dial.van.trading

import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

class RuntimeRecoveryProtocolTest {
    private fun fixtures(): JsonArray = Json.parseToJsonElement(javaClass.classLoader!!
        .getResourceAsStream("runtime_recovery_contract.json")!!.bufferedReader().use { it.readText() }) as JsonArray

    private fun response(row: JsonObject): JsonObject {
        val intent = row.getValue("intent").jsonObject
        return buildJsonObject {
            put("intent", intent); put("approval_challenge_id", row.getValue("operation_id"))
            put("approval_challenge", row.getValue("canonical"))
            put("approval_expires_at_unix", row.getValue("expires_at_unix"))
            put("resolved_action_id", "trading.runtime." + intent.getValue("action").jsonPrimitive.content)
            put("resolved_review", buildJsonObject {
                put("state_ref", intent.getValue("state_ref"))
                put("state", buildJsonObject {
                    put("account_alias", intent.getValue("account_alias"))
                    put("session_id", intent.getValue("session_id"))
                })
            })
        }
    }

    @Test fun allActionsAndUnicodeSessionsMatchTheActualPythonCanonicalStatements() {
        assertEquals(6, fixtures().size)
        for (value in fixtures()) {
            val row = value.jsonObject
            val intent = RuntimeRecoveryProtocol.parseIntent(row.getValue("intent").jsonObject)
            assertEquals(row.getValue("digest").jsonPrimitive.content, intent.digest)
            assertEquals(row.getValue("intent_digest").jsonPrimitive.content, intent.intentDigest)
            val challenge = RuntimeRecoveryProtocol.challenge(intent, response(row).toString())
            assertEquals(row.getValue("canonical").jsonPrimitive.content, challenge.canonical)
            val body = challenge.requestBody("c2lnbmF0dXJl")
            assertEquals(intent.body(), body["intent"])
            assertEquals(row["operation_id"], body["approval_proof"]!!.jsonObject["challenge_id"])
            assertEquals(row["expires_at_unix"], body["approval_proof"]!!.jsonObject["expires_at_unix"])
        }
    }

    @Test fun callerMapMutationCannotChangeTheApprovedTargetOrTimestamp() {
        val args = mutableMapOf("scope" to "*ACCOUNT*")
        val intent = RuntimeRecoveryIntent("owner-device", "paper_lab", "original", "reset_loss_streak", "a".repeat(64), 1700000000, args)
        val before = intent.body(); val digest = intent.digest
        args["scope"] = "OTHER"
        assertEquals(before, intent.body()); assertEquals(digest, intent.digest)
        assertEquals("*ACCOUNT*", intent.arguments["scope"])
        assertThrows(UnsupportedOperationException::class.java) {
            (intent.arguments as MutableMap<String, String>)["scope"] = "OTHER"
        }
    }

    @Test fun foreignOrChangedChallengeCannotReachBiometricSigning() {
        val row = fixtures()[0].jsonObject
        val intent = RuntimeRecoveryProtocol.parseIntent(row.getValue("intent").jsonObject)
        val good = response(row)
        for (changed in listOf(
            JsonObject(good + ("approval_challenge" to JsonPrimitive("different statement"))),
            JsonObject(good + ("resolved_action_id" to JsonPrimitive("trading.runtime.resume_drawdown"))),
            JsonObject(good + ("approval_expires_at_unix" to JsonPrimitive(1700000121))),
            JsonObject(good + ("approval_challenge_id" to JsonPrimitive("different_recovery_id_123456"))),
            JsonObject(good + ("intent" to JsonObject(intent.body() + ("state_ref" to JsonPrimitive("b".repeat(64)))))),
        )) assertThrows(Exception::class.java) { RuntimeRecoveryProtocol.challenge(intent, changed.toString()) }
    }

    @Test fun targetShapeAndStrictIntegerFieldsAreNotCoerced() {
        val body = fixtures()[1].jsonObject.getValue("intent").jsonObject
        for (changed in listOf(
            JsonObject(body + ("extra" to JsonPrimitive("unapproved"))),
            JsonObject(body + ("issued_at_unix" to JsonPrimitive("1700000000"))),
            JsonObject(body + ("issued_at_unix" to JsonPrimitive(1700000000.5))),
            JsonObject(body + ("issued_at_unix" to JsonPrimitive(true))),
            JsonObject(body + ("session_id" to JsonPrimitive("session|other"))),
            JsonObject(body + ("args" to buildJsonObject { put("scope", "*ACCOUNT*") })),
        )) assertThrows(Exception::class.java) { RuntimeRecoveryProtocol.parseIntent(changed) }
    }
    @Test fun malformedSignatureEncodingIsRefusedBeforeAnyDispatchIdentityIsStored() {
        val row = fixtures()[0].jsonObject
        val intent = RuntimeRecoveryProtocol.parseIntent(row.getValue("intent").jsonObject)
        val challenge = RuntimeRecoveryProtocol.challenge(intent,response(row).toString())
        for (signature in listOf("malformed? signature","YQ"))
            assertThrows(Exception::class.java) { challenge.requestBody(signature) }
    }

}
