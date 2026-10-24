package com.dial.van.trading

import org.junit.Assert.*
import org.junit.Test

class AccountOperationRecoveryTest {
    private class Disk : AccountOperationStore {
        var text: String? = null
        var writable = true
        override fun load() = text
        override fun save(value: String): Boolean {
            if (!writable) return false
            text = value; return true
        }
    }
    private val original = PendingAccountOperation("original_operation_id_12345", "mt5_ea_issue_key", "owner-device", "owner_mt5")
    private fun response(state: String = "APPLIED", id: String = original.operationId,
                         action: String = original.action, reconcile: Boolean = false) =
        """{"operation_id":"$id","action":"$action","effect_state":"$state","reconciliation_required":$reconcile,"result":{"account":{"alias":"owner_mt5"},"credential_export_available":false}}"""

    @Test fun coldReaderRetainsOriginalIdentityAndNeverStoresArgumentsProofOrCredentials() {
        val disk = Disk(); AccountOperationRecovery(disk).remember(original)
        assertEquals(listOf(original), AccountOperationRecovery(disk).pending("owner-device"))
        assertTrue(AccountOperationRecovery(disk).pending("other-owner").isEmpty())
        assertFalse(disk.text!!.contains("password")); assertFalse(disk.text!!.contains("signing_key"))
        assertFalse(disk.text!!.contains("signature")); assertFalse(disk.text!!.contains("args"))
    }

    @Test fun failedDurableWritePreventsDispatchAndPreservesEarlierIdentities() {
        val disk = Disk(); val history = AccountOperationRecovery(disk); history.remember(original)
        val before = disk.text; disk.writable = false
        assertThrows(IllegalStateException::class.java) {
            history.remember(original.copy(operationId = "another_operation_id_12345", alias = "other_mt5"))
        }
        assertEquals(before, disk.text)
    }

    @Test fun rememberingAnOriginalOrNewApprovalForItsAliasCannotBecomeASendRetry() {
        val disk = Disk(); val history = AccountOperationRecovery(disk); history.remember(original)
        assertThrows(IllegalStateException::class.java) { history.remember(original) }
        assertThrows(IllegalStateException::class.java) {
            history.remember(original.copy(operationId = "another_operation_id_12345"))
        }
        assertEquals(listOf(original), history.pending(original.deviceId))
    }

    @Test fun onlyBoundConfirmedOutcomeClearsTheOriginal() {
        val disk = Disk(); val history = AccountOperationRecovery(disk); history.remember(original)
        for (body in listOf("bad json", "{}", response("UNKNOWN", reconcile = true), response(id="different_operation_id_12345"),
            response(action="account_remove"), response(reconcile=true))) {
            assertFalse(history.observe(original, body, 200))
            assertEquals(listOf(original), history.pending(original.deviceId))
        }
        assertFalse(history.observe(original, response(), 502))
        assertTrue(history.observe(original, response(), 200))
        assertTrue(AccountOperationRecovery(disk).pending(original.deviceId).isEmpty())
    }

    @Test fun refusalCanClearButAnUnreadableOrMissingHistoryCannotBeReplaced() {
        val disk = Disk(); val history = AccountOperationRecovery(disk); history.remember(original)
        assertTrue(history.observe(original, response("REFUSED"), 200))
        disk.text = "corrupt original state"
        assertThrows(Exception::class.java) { history.remember(original) }
        assertEquals("corrupt original state", disk.text)
    }

    @Test fun failureToSaveAConfirmedReadbackStillKeepsTheOriginalIdentity() {
        val disk = Disk(); val history = AccountOperationRecovery(disk); history.remember(original)
        disk.writable = false
        assertThrows(IllegalStateException::class.java) { history.observe(original, response(), 200) }
        assertEquals(listOf(original), history.pending(original.deviceId))
    }

    @Test fun recoveryDoesNotInventAnotherCredentialExportOrTreatUnknownAsAnOrdinaryFailure() {
        val confirmed = AccountOnboarding.parseOutcome(original.action, response(), 200)
        assertTrue(confirmed.ok); assertNull(confirmed.signingKey)
        assertTrue(confirmed.message.contains("not retained"))
        val knownWithoutExport = AccountOnboarding.parseOutcome(original.action,
            """{"credential_export_available":false,"account":{"alias":"owner_mt5"}}""", 200)
        assertTrue(knownWithoutExport.ok); assertNull(knownWithoutExport.signingKey)
        assertTrue(knownWithoutExport.message.contains("not retained"))
        val uncertain = AccountOnboarding.parseOutcome(original.action, response("UNKNOWN", reconcile=true), 409)
        assertFalse(uncertain.ok); assertTrue(uncertain.message.contains("original result"))
    }
}
