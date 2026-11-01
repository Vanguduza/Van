package com.dial.van.gateway

import org.json.JSONObject
import kotlin.test.*
import java.io.IOException
import java.util.UUID

class GoogleWithdrawalOperationsTest {
    private class Store : GoogleWithdrawalStore {
        var value: String? = null
        var writable = true
        override fun load() = value
        override fun save(value: String): Boolean { if (!writable) return false; this.value = value; return true }
    }
    private fun detail(generation: String = "a".repeat(32), connected: Boolean = true): JSONObject {
        val request = JSONObject().put("operation_id", "workspace-withdraw-${UUID.randomUUID().toString().replace("-", "")}")
            .put("caller_device_id", "device-one").put("owner_id", "owner").put("connection_generation", generation)
            .put("expected_revision", "b".repeat(64)).put("request_token", "SOURCE-server-sealed-inert-proposal")
        return JSONObject().put("owner_id", "owner").put("connection_generation", generation)
            .put("source_revision", "b".repeat(64)).put("connected", connected).put("withdrawal_request", request)
    }
    private fun receipt(p: PendingGoogleWithdrawal, state: String = "APPLIED"): JSONObject {
        val body = JSONObject(p.requestBody)
        body.remove("request_token")
        return body.put("state", state).put("withdrawn", state == "APPLIED").put("changed", state == "APPLIED")
            .put("reason_code", if (state == "APPLIED") JSONObject.NULL else "workspace_withdrawal_request_expired")
            .put("request_deadline_ms", 600001L).put("completed_at_ms", 100L)
            .put("effect_scope", "gateway_held_workspace_credential_only").put("provider_token_revoked", false)
    }
    @Test fun `original operation is persisted before POST and lost reply recovers via original read`() {
        val store = Store(); val journal = GoogleWithdrawalOperations(store); var calls = 0
        val result = journal.revoke("profile-one", "device-one", detail(), { "profile-one" }, { "device-one" },
            originalResult = { if (calls == 0) null else receipt(it) },
            submit = { assertTrue(store.value!!.contains(it.operationId)); calls++; throw IOException("SOURCE-lost-reply") },
            detail = { detail(connected = false) })
        assertEquals("APPLIED", result.getJSONObject("withdrawal_receipt").getString("state"))
        assertEquals(1, calls); assertTrue(journal.pending("profile-one", "device-one").isEmpty())
    }
    @Test fun `restart reads original without POST and replacement remains independently visible`() {
        val store = Store(); val journal = GoogleWithdrawalOperations(store)
        val original = journal.prepare("profile-one", "device-one", detail())
        val restarted = GoogleWithdrawalOperations(store)
        assertEquals(original, restarted.pending("profile-one", "device-one").single())
        var reads = 0
        assertEquals(1, restarted.recover("profile-one", "device-one", { "profile-one" }, { "device-one" },
            originalResult = { reads++; receipt(it) }, detail = { detail("c".repeat(32)) }))
        assertEquals(1, reads); assertTrue(restarted.pending("profile-one", "device-one").isEmpty())
    }
    @Test fun `unknown original remains stable across new proposal and explicit replacement selection`() {
        val store = Store(); val journal = GoogleWithdrawalOperations(store)
        val first = journal.prepare("profile-one", "device-one", detail())
        assertEquals(first, journal.prepare("profile-one", "device-one", detail()))
        val second = journal.prepare("profile-one", "device-one", detail("c".repeat(32)))
        assertNotEquals(first.operationId, second.operationId)
        assertEquals(2, journal.pending("profile-one", "device-one").size)
        assertEquals(0, journal.recover("profile-one", "device-one", { "profile-one" }, { "device-one" }, { null }, { error("no current read") }))
        assertEquals(2, GoogleWithdrawalOperations(store).pending("profile-one", "device-one").size)
    }
    @Test fun `profile or caller switch cannot post or clear another original`() {
        val store = Store(); val journal = GoogleWithdrawalOperations(store)
        journal.prepare("profile-one", "device-one", detail())
        for (profile in listOf("profile-one", "profile-two")) {
            assertFailsWith<IllegalStateException> {
                journal.revoke("profile-one", "device-one", detail(), { profile }, { "device-two" },
                    { error("no original read") }, { error("no post") }, { error("no detail") })
            }
        }
        assertEquals(1, journal.pending("profile-one", "device-one").size)
        assertTrue(journal.pending("profile-two", "device-two").isEmpty())
    }
    @Test fun `changed receipt or unconfirmed current original cannot clear history`() {
        for (tamper in listOf("operation_id", "owner_id", "connection_generation", "expected_revision", "caller_device_id", "effect_scope")) {
            val store = Store(); val journal = GoogleWithdrawalOperations(store)
            journal.prepare("profile-one", "device-one", detail())
            assertFailsWith<IllegalStateException> {
                journal.revoke("profile-one", "device-one", detail(), { "profile-one" }, { "device-one" },
                    { receipt(it).put(tamper, "SOURCE-wrong") }, { error("no post") }, { detail(connected = false) })
            }
            assertEquals(1, journal.pending("profile-one", "device-one").size)
        }
        val store = Store(); val journal = GoogleWithdrawalOperations(store)
        journal.prepare("profile-one", "device-one", detail())
        assertFailsWith<IllegalStateException> {
            journal.revoke("profile-one", "device-one", detail(), { "profile-one" }, { "device-one" },
                { receipt(it) }, { error("no post") }, { detail(connected = true) })
        }
        assertEquals(1, journal.pending("profile-one", "device-one").size)
    }
    @Test fun `durable refusal clears only original and requires new explicit confirmation`() {
        val store = Store(); val journal = GoogleWithdrawalOperations(store)
        val first = journal.prepare("profile-one", "device-one", detail())
        journal.prepare("profile-one", "device-one", detail("c".repeat(32)))
        assertFailsWith<IllegalStateException> {
            journal.revoke("profile-one", "device-one", detail(), { "profile-one" }, { "device-one" },
                { receipt(it, "REFUSED") }, { error("no post") }, { error("no use on refusal") })
        }
        assertFalse(journal.pending("profile-one", "device-one").any { it.operationId == first.operationId })
        assertEquals(1, journal.pending("profile-one", "device-one").size)
    }
    @Test fun `failed protected persistence blocks POST`() {
        val store = Store(); store.writable = false
        assertFailsWith<IllegalStateException> {
            GoogleWithdrawalOperations(store).revoke("profile-one", "device-one", detail(), { "profile-one" }, { "device-one" },
                { error("no read") }, { error("no post") }, { error("no detail") })
        }
    }
    @Test fun `cancellation propagates and original remains recoverable without a replacement POST`() {
        val store = Store(); val journal = GoogleWithdrawalOperations(store); var reads = 0
        assertFailsWith<java.util.concurrent.CancellationException> {
            journal.revoke("profile-one", "device-one", detail(), { "profile-one" }, { "device-one" },
                { reads++; null }, { throw java.util.concurrent.CancellationException("SOURCE-cancelled") }, { error("no detail") })
        }
        assertEquals(1, reads)
        assertEquals(1, GoogleWithdrawalOperations(store).pending("profile-one", "device-one").size)
    }

}
