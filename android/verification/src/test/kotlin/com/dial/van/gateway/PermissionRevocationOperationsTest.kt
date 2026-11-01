package com.dial.van.gateway

import org.json.JSONObject
import java.io.IOException
import java.util.UUID
import kotlin.test.*

class PermissionRevocationOperationsTest {
    private class Store : PermissionRevocationStore {
        var value: String? = null
        var writable = true
        override fun load() = value
        override fun save(value: String): Boolean { if (!writable) return false; this.value = value; return true }
    }
    private fun detail(source: String = "b".repeat(64), issuer: String? = "historic-issuer"): JSONObject {
        val request = JSONObject().put("operation_id", "permission-revoke-${UUID.randomUUID()}")
            .put("caller_device_id", "owner-one").put("grant_device_id", issuer ?: JSONObject.NULL)
            .put("expected_revision", "a".repeat(64)).put("expected_source_digest", source).put("request_token", "opaque-server-sealed-request-fixture")
        return JSONObject().put("grant_id", "grant-one").put("caller_device_id", "owner-one")
            .put("grant_device_id", issuer ?: JSONObject.NULL).put("source_revision", "a".repeat(64)).put("source_digest", source)
            .put("revoked_at_ms", JSONObject.NULL).put("effective_remaining_uses", 3).put("revocation_request", request)
    }
    private fun receipt(p: PendingPermissionRevocation, applied: Boolean = true): JSONObject = JSONObject()
        .put("operation_id", p.operationId).put("grant_id", p.grantId).put("caller_device_id", p.deviceId)
        .put("grant_device_id", JSONObject(p.requestBody).opt("grant_device_id"))
        .put("expected_revision", JSONObject(p.requestBody).getString("expected_revision")).put("source_digest", p.sourceDigest)
        .put("state", if (applied) "APPLIED" else "REFUSED").put("revoked", applied)
        .put("revoked_at_ms", if (applied) 12345 else JSONObject.NULL).put("native_authority_issued", false)
        .put("reason_code", if (applied) JSONObject.NULL else "permission_revocation_request_expired")
    @Test fun `original body deadline and distinct historic issuer survive process restart`() {
        val store = Store(); val operations = PermissionRevocationOperations(store)
        val original = operations.prepare("profile-one", "owner-one", "grant-one", detail())
        val restarted = PermissionRevocationOperations(store)
        assertEquals(original, restarted.pending("profile-one", "owner-one", "grant-one", original.sourceDigest))
        assertEquals(original, restarted.prepare("profile-one", "owner-one", "grant-one", detail()))
        assertNull(restarted.pending("other-profile", "owner-one", "grant-one", original.sourceDigest))
        assertNull(restarted.pending("profile-one", "other-owner", "grant-one", original.sourceDigest))
        assertTrue(restarted.observe(original, receipt(original)))
        assertTrue(restarted.observe(original, receipt(original)))
    }
    @Test fun `only explicit different reviewed generation creates fresh intent and old unknown is retained`() {
        val store = Store(); val operations = PermissionRevocationOperations(store)
        val old = operations.prepare("profile-one", "owner-one", "grant-one", detail())
        val fresh = operations.prepare("profile-one", "owner-one", "grant-one", detail(source = "c".repeat(64)))
        assertNotEquals(old.operationId, fresh.operationId)
        assertEquals(old, operations.pending("profile-one", "owner-one", "grant-one", old.sourceDigest))
        assertTrue(operations.observe(fresh, receipt(fresh)))
        assertEquals(old, operations.pending("profile-one", "owner-one", "grant-one", old.sourceDigest))
    }
    @Test fun `wrong scope unknown and malformed receipt cannot discard original`() {
        val store = Store(); val operations = PermissionRevocationOperations(store)
        val original = operations.prepare("profile-one", "owner-one", "grant-one", detail())
        for (changed in listOf(receipt(original).put("caller_device_id", "other-owner"),receipt(original).put("grant_device_id", "other-issuer"),
            receipt(original).put("grant_id", "other-grant"),receipt(original).put("operation_id", "other-operation-123456"),
            receipt(original).put("source_digest", "c".repeat(64)),receipt(original).put("state", "UNKNOWN"),
            receipt(original).put("revoked_at_ms", "12345"),receipt(original).put("revoked_at_ms", 12345.0))) {
            assertFails { operations.observe(original, changed) }
            assertEquals(original, operations.pending("profile-one", "owner-one", "grant-one", original.sourceDigest))
        }
    }
    @Test fun `save failure precedes network and failed cleanup retains known original`() {
        val store = Store(); val operations = PermissionRevocationOperations(store)
        store.writable = false
        assertFailsWith<IllegalStateException> { operations.prepare("profile-one", "owner-one", "grant-one", detail()) }
        assertNull(store.value)
        store.writable = true
        val original = operations.prepare("profile-one", "owner-one", "grant-one", detail())
        store.writable = false
        assertFails { operations.observe(original, receipt(original)) }
        assertEquals(original, operations.pending("profile-one", "owner-one", "grant-one", original.sourceDigest))
    }
    @Test fun `terminal refusal does not clear later explicit operation`() {
        val store = Store(); val operations = PermissionRevocationOperations(store)
        val old = operations.prepare("profile-one", "owner-one", "grant-one", detail())
        assertFalse(operations.observe(old, receipt(old, false)))
        val fresh = operations.prepare("profile-one", "owner-one", "grant-one", detail())
        assertNotEquals(old.operationId, fresh.operationId)
        assertFalse(operations.observe(old, receipt(old, false)))
        assertEquals(fresh, operations.pending("profile-one", "owner-one", "grant-one", fresh.sourceDigest))
    }
    @Test fun `actual caller exchange recovers lost commit response with one effect and independent detail`() {
        val store = Store(); val operations = PermissionRevocationOperations(store)
        val review = detail(); var current = review; var completed: JSONObject? = null; var submits = 0
        val result = operations.revoke("profile-one", "owner-one", "grant-one", review,
            currentProfile = { "profile-one" }, currentDevice = { "owner-one" }, detail = { current },
            originalResult = { completed }, submit = { original ->
                submits++; completed = receipt(original)
                current = detail().put("revoked_at_ms", 12345).put("effective_remaining_uses", 0)
                throw IOException("lost response after actual modeled commit")
            })
        assertEquals(1, submits); assertEquals("APPLIED", result.getString("state"))
        assertNull(operations.pending("profile-one", "owner-one", "grant-one", review.getString("source_digest")))
    }
    @Test fun `unavailable readback keeps original and restart never resubmits applied effect`() {
        val store = Store(); val review = detail(); var completed: JSONObject? = null; var reads = 0; var submits = 0
        assertFailsWith<IOException> {
            PermissionRevocationOperations(store).revoke("profile-one", "owner-one", "grant-one", review,
                currentProfile = { "profile-one" },currentDevice = { "owner-one" },detail = { error("unavailable") },
                originalResult = { if (++reads == 1) null else throw IOException("readback unavailable") },submit = { original ->
                    submits++; completed = receipt(original); throw IOException("reply lost")
                })
        }
        val restarted = PermissionRevocationOperations(store)
        assertNotNull(restarted.pending("profile-one", "owner-one", "grant-one", review.getString("source_digest")))
        val result = restarted.revoke("profile-one", "owner-one", "grant-one", detail(),
            currentProfile = { "profile-one" },currentDevice = { "owner-one" },
            detail = { detail().put("revoked_at_ms", 12345).put("effective_remaining_uses", 0) },
            originalResult = { completed },submit = { error("applied effect must not be resubmitted") })
        assertEquals(1, submits); assertEquals("APPLIED", result.getString("state"))
    }
    @Test fun `profile or caller switch prevents any original lookup or mutation`() {
        for (switched in listOf("profile", "caller")) {
            val operations = PermissionRevocationOperations(Store())
            assertFails {
                operations.revoke("profile-one", "owner-one", "grant-one", detail(),
                    currentProfile = { if (switched == "profile") "other-profile" else "profile-one" },
                    currentDevice = { if (switched == "caller") "other-owner" else "owner-one" },
                    detail = { error("no read") },originalResult = { error("no original lookup") },submit = { error("no mutation") })
            }
        }
    }
    @Test fun `unverified local target can be withdrawn without claiming a historic issuer`() {
        val operations = PermissionRevocationOperations(Store())
        val original = operations.prepare("profile-one", "owner-one", "grant-one", detail(issuer = null))
        assertTrue(operations.observe(original, receipt(original)))
    }
    @Test fun `corrupt history never starts a replacement operation`() {
        val store = Store(); store.value = "[{broken]"
        assertFails { PermissionRevocationOperations(store).prepare("profile-one", "owner-one", "grant-one", detail()) }
        assertEquals("[{broken]", store.value)
    }
}
