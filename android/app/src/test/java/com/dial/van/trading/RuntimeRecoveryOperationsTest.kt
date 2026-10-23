package com.dial.van.trading

import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

class RuntimeRecoveryOperationsTest {
    private open class Disk : AccountOperationStore {
        @Volatile var text: String? = null
        @Volatile var writable = true
        override fun load() = text
        override fun save(value: String): Boolean {
            if (!writable) return false
            text = value; return true
        }
    }
    private val intent = RuntimeRecoveryIntent("owner-device","paper_lab","native-session","reset_loss_streak",
        "a".repeat(64),1700000000,mapOf("scope" to "*ACCOUNT*"))
    private val id = "original_recovery_id_123456"
    private val challenge = RuntimeRecoveryChallenge(intent,id,intent.approvalStatement(id,1700000120),1700000120)
    private val original = PendingRuntimeRecovery.from(challenge)
    private fun result(phase: String = "APPLIED", request: JsonObject = intent.body(), permission: JsonElement = JsonPrimitive(false)): JsonObject =
        buildJsonObject {
            put("operation_id",id); put("phase",phase); put("intent",request); put("native_event_ref","b".repeat(64))
            put("result",buildJsonObject {
                put("reason_code",if (phase == "REFUSED") "STATE_CHANGED" else "APPLIED")
                put("entry_authority_granted",permission)
                put("effect_refs",JsonArray(if (phase == "REFUSED") emptyList() else listOf(JsonPrimitive("c".repeat(64)))))
            })
        }

    @Test fun coldReadKeepsOnlyTheOriginalPublicIdentityAndAllowsOnlyItsExactRetry() {
        val disk = Disk(); val history = RuntimeRecoveryOperations(disk); history.remember(original)
        val saved = disk.text
        history.remember(original); assertEquals(saved,disk.text)
        assertEquals(listOf(original),RuntimeRecoveryOperations(disk).pending(original.deviceId))
        assertTrue(history.pending("other-device").isEmpty())
        for (key in listOf("args","signature","credentials","*ACCOUNT*")) assertFalse(disk.text!!.contains(key))
        assertThrows(Exception::class.java) { history.remember(original.copy(bodyDigest = "d".repeat(64))) }
        assertThrows(Exception::class.java) { history.remember(original.copy(operationId = "newer_recovery_id_12345678")) }
    }

    @Test fun aFailedIdentityWritePreventsDispatchAndDoesNotOverwriteThePreviousOperation() {
        val disk = Disk(); val history = RuntimeRecoveryOperations(disk); history.remember(original)
        val saved = disk.text; disk.writable = false
        assertThrows(Exception::class.java) {
            history.remember(original.copy(operationId = "other_recovery_id_12345678",accountAlias = "other_lab"))
        }
        assertEquals(saved,disk.text)
    }

    @Test fun uncertaintyAndForeignOrWeakenedNativeReceiptsNeverClearTheOriginal() {
        val disk = Disk(); val history = RuntimeRecoveryOperations(disk); history.remember(original)
        val changedTime = JsonObject(intent.body() + ("issued_at_unix" to JsonPrimitive(1700000001)))
        val changedState = JsonObject(intent.body() + ("state_ref" to JsonPrimitive("d".repeat(64))))
        val applied = result()
        val damaged = listOf(result("UNKNOWN"),result("REQUESTED"),result("PENDING_DISPATCH"),
            result(request = changedTime),result(request = changedState),result(permission = JsonPrimitive(true)),
            result(permission = JsonPrimitive("false")),
            JsonObject(applied + ("operation_id" to JsonPrimitive("different_recovery_id_12345"))),
            JsonObject(applied + ("native_event_ref" to JsonPrimitive("unverified"))),
            JsonObject(applied + ("result" to JsonObject(applied["result"]!!.jsonObject + ("effect_refs" to JsonArray(emptyList()))))))
        for (row in damaged) {
            assertFalse(history.observe(original,row.toString(),200))
            assertEquals(listOf(original),history.pending(original.deviceId))
        }
        assertFalse(history.observe(original,applied.toString(),503))
        assertFalse(history.observe(original,"bad json",200))
        assertTrue(history.observe(original,applied.toString(),200))
        assertTrue(history.pending(original.deviceId).isEmpty())
    }

    @Test fun genuineRefusalCanFinishButCorruptHistoryAndSaveFailureKeepTheIdentity() {
        val disk = Disk(); val history = RuntimeRecoveryOperations(disk); history.remember(original)
        disk.writable = false
        assertThrows(Exception::class.java) { history.observe(original,result().toString(),200) }
        assertEquals(listOf(original),history.pending(original.deviceId))
        disk.writable = true
        assertTrue(history.observe(original,result("REFUSED").toString(),200))
        disk.text = "corrupt original history"
        assertThrows(Exception::class.java) { history.remember(original) }
        assertEquals("corrupt original history",disk.text)
    }

    @Test fun twoClientInstancesCannotLoseAnOriginalIdentityThroughConcurrentPreferenceUpdates() {
        val firstRead = CountDownLatch(1); val secondRead = CountDownLatch(1); val armed = AtomicBoolean()
        val disk = object : Disk() {
            override fun load(): String? {
                val snapshot = text
                if (armed.compareAndSet(false,true)) { firstRead.countDown(); secondRead.await(300,TimeUnit.MILLISECONDS) }
                else secondRead.countDown()
                return snapshot
            }
        }
        val one = RuntimeRecoveryOperations(disk); val two = RuntimeRecoveryOperations(disk)
        val other = original.copy(operationId = "parallel_recovery_id_12345",accountAlias = "other_lab",bodyDigest = "d".repeat(64))
        val pool = Executors.newFixedThreadPool(2)
        try {
            val first = pool.submit { one.remember(original) }
            assertTrue(firstRead.await(2,TimeUnit.SECONDS))
            val second = pool.submit { two.remember(other) }
            first.get(3,TimeUnit.SECONDS); second.get(3,TimeUnit.SECONDS)
            assertEquals(setOf(original,other),RuntimeRecoveryOperations(disk).pending(original.deviceId).toSet())
        } finally { pool.shutdownNow() }
    }
    @Test fun anExpiredNewApprovalCannotPersistAnIdentityOrDispatchButItsOriginalRetryStaysOriginal() {
        val disk = Disk(); val history = RuntimeRecoveryOperations(disk)
        assertThrows(Exception::class.java) { history.prepareDispatch(challenge,1700000120) }
        assertNull(disk.text)
        assertEquals(original,history.prepareDispatch(challenge,1700000000))
        val saved = disk.text
        assertEquals(original,history.prepareDispatch(challenge,1700000200))
        assertEquals(saved,disk.text)
    }

    @Test fun aStaleOrFutureNewIntentCannotReachDurableDispatch() {
        for (time in listOf(1699999939L,1700000300L)) {
            val disk = Disk(); val history = RuntimeRecoveryOperations(disk)
            val freshChallenge = RuntimeRecoveryChallenge(intent,id,intent.approvalStatement(id,time+120),time+120)
            assertThrows(Exception::class.java) { history.prepareDispatch(freshChallenge,time) }
            assertNull(disk.text)
        }
    }

}
