package com.dial.van.trading

import org.junit.Assert.*
import org.junit.Test
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.Job
import kotlinx.coroutines.CancellationException

class AccountOperationRecoveryTest {
    private fun preparedLink() = original.copy(operationId = "original_link_operation_123456", action = "deriv_oauth_link", alias = "linked_once",
        oauthState = "original_oauth_state_123456789", dispatchStage = "PREPARED", originalApprovalExpiresAt = 123456L, originalResourceVersion = "c".repeat(64), originalIssuedAt = 123000L,
        oauthArguments = parseObject("""{"state":"original_oauth_state_123456789","alias":"linked_once","loginid":"VRTC900"}""")!!)

    @Test fun preparedReadinessIsNotCompletionAndResumeIsExplicitUnderFreshOwnerFlow() = runBlocking {
        val disk = Disk(); val value = preparedLink(); val history = AccountOperationRecovery(disk)
        val oldActor = AccountOperationActor(scope, value.deviceId, "old-token")
        var current = oldActor; var links = 0
        disk.afterSave = { current = oldActor.copy(credentialContext = "renewed-current-token") }
        try { history.dispatch(value, oldActor, { current }) { links += 1; 200 to "{}" }; fail("changed actor must stop before exchange") }
        catch (expected: IllegalStateException) { }
        assertEquals(0, links); assertEquals("PREPARED", history.pending(value.deviceId).single().dispatchStage)
        disk.afterSave = null
        val ready = """{"ready":true,"broker":"deriv","accounts":[{"loginid":"VRTC900","currency":"USD"}]}"""
        val recovered = history.recover(value, current, { current }) { 200 to ready }
        assertEquals("NOT_DISPATCHED", parseObject(recovered.second)!!.str("effect_state"))
        assertFalse(AccountOnboarding.parseOutcome(value.action, recovered.second, recovered.first, requireOriginalReceipt = true).ok)
        assertEquals(listOf(value), history.pending(value.deviceId)); assertEquals(0, links)
        val args = history.resumeArguments(value, scope)
        assertEquals(value.oauthState, args.str("state")); assertEquals(value.operationId, args.str("original_operation_id"))
        assertEquals(123456L, args.str("original_approval_expires_at_unix")!!.toLong())
        assertEquals(value.originalResourceVersion, args.str("original_resource_version"))
        assertEquals(value.originalIssuedAt, args.str("original_issued_at_unix")!!.toLong())
        assertEquals(scope.nativeOwnerDomain, args.str("original_account_control_domain"))
        // Actual client separately checks the new A4 selection; this state
        // machine never obtains a grant from readiness or a missing ACK.
        history.resume(value, current, { current }) { guard ->
            guard(); history.markPossibleSend(value); guard(); links += 1
            409 to """{"effect_state":"UNKNOWN","reconciliation_required":true}"""
        }
        assertEquals(1, links)
        val sent = history.pending(value.deviceId).single()
        assertEquals(value.operationId, sent.operationId); assertEquals("MAY_HAVE_SENT", sent.dispatchStage)
        assertFalse(history.canResume(sent, scope))
        val held = history.recover(sent, current, { current }) { 200 to ready }
        assertEquals("UNKNOWN", parseObject(held.second)!!.str("effect_state"))
        assertEquals(1, links); assertEquals(listOf(sent), history.pending(value.deviceId))
    }

    @Test fun durablePossibleSendMarkerPrecedesConnectionAndItsUncertainAckCannotAuthorizeResume(): Unit = runBlocking {
        var text: String? = null; var writes = 0
        val store = object : AccountOperationStore {
            override fun load() = text
            override fun save(value: String): Boolean { text = value; writes += 1; return writes == 1 }
        }
        val value = preparedLink(); val actor = AccountOperationActor(scope, value.deviceId, "current-token")
        val history = AccountOperationRecovery(store); var connections = 0
        try {
            history.dispatch(value, actor, { actor }) { guard ->
                guard(); history.markPossibleSend(value); guard(); connections += 1; 200 to "{}"
            }
            fail("uncertain durable marker must prevent connection")
        } catch (expected: IllegalStateException) { }
        assertEquals(0, connections)
        val cold = AccountOperationRecovery(store); val original = cold.pending(value.deviceId).single()
        assertEquals("MAY_HAVE_SENT", original.dispatchStage); assertFalse(cold.canResume(original, scope))
        assertThrows(IllegalStateException::class.java) { cold.markPossibleSend(original) }
        assertThrows(IllegalStateException::class.java) { cold.resumeArguments(original, scope) }
    }

    @Test fun legacyV4PreparedHasNoOriginalVersionProofAndCannotAdoptCurrentGeneration() {
        val disk = Disk(); val value = preparedLink()
        AccountOperationRecovery(disk).remember(value)
        disk.text = disk.text!!.replace("van.android.account-operations/5", "van.android.account-operations/4")
            .replace(",\"original_resource_version\":\"${value.originalResourceVersion}\"", "")
            .replace(",\"original_issued_at_unix\":${value.originalIssuedAt}", "")
        val cold = AccountOperationRecovery(disk); val old = cold.pending(value.deviceId).single()
        assertEquals("PREPARED", old.dispatchStage); assertEquals(value.operationId, old.operationId)
        assertNull(old.originalResourceVersion); assertNull(old.originalIssuedAt)
        assertFalse(cold.canResume(old, scope))
        assertThrows(IllegalStateException::class.java) { cold.resumeArguments(old, scope) }
        assertEquals(listOf(old), cold.pending(value.deviceId))
    }

    @Test fun legacyV3LinkHasNoNeverSentProofAndReadinessCannotCompleteIt() = runBlocking {
        val disk = Disk(); val value = preparedLink()
        disk.text = """{"schema":"van.android.account-operations/3","operations":[{
            "operation_id":"${value.operationId}","action":"${value.action}","device_id":"${value.deviceId}","alias":"${value.alias}",
            "request_identity":"${value.requestIdentity}","oauth_state":"${value.oauthState}","scope":{
            "root":"${scope.root}","profile_id":"${scope.profileId}","provisioning_id":"${scope.provisioningId}","native_owner_domain":"${scope.nativeOwnerDomain}"}}]}"""
        val cold = AccountOperationRecovery(disk); val original = cold.pending(value.deviceId).single()
        assertEquals("UNKNOWN", original.dispatchStage); assertNull(original.oauthArguments)
        val actor = AccountOperationActor(scope, original.deviceId, "current-token")
        val read = cold.recover(original, actor, { actor }) { 200 to """{"ready":true,"accounts":[]}""" }
        assertEquals("UNKNOWN", parseObject(read.second)!!.str("effect_state"))
        assertFalse(cold.canResume(original, scope)); assertEquals(listOf(original), cold.pending(value.deviceId))
    }

    @Test fun scopedV2HistoryRetainsOriginalBindingDuringOAuthStateMigration() {
        val disk = Disk()
        disk.text = """{"schema":"van.android.account-operations/2","operations":[{
            "operation_id":"${original.operationId}","action":"${original.action}","device_id":"${original.deviceId}",
            "alias":"${original.alias}","request_identity":"${original.requestIdentity}","scope":{
            "root":"${scope.root}","profile_id":"${scope.profileId}","provisioning_id":"${scope.provisioningId}",
            "native_owner_domain":"${scope.nativeOwnerDomain}"}}]}"""
        val history = AccountOperationRecovery(disk)
        assertEquals(listOf(original), history.pending(original.deviceId))
        val link = original.copy(operationId = "original_link_operation_123456", action = "deriv_oauth_link", alias = "linked_once",
            oauthState = "original_oauth_state_123456789")
        history.remember(link)
        assertEquals(listOf(original, link), AccountOperationRecovery(disk).pending(original.deviceId))
        assertTrue(disk.text!!.contains("van.android.account-operations/5"))
        assertEquals(scope, AccountOperationRecovery(disk).pending(original.deviceId).first().scope)
    }

    @Test fun oauthLinkPersistsOriginalStateBeforeSendAndReadsOnlyThatStateAfterRestart() = runBlocking {
        val disk = Disk()
        val original = PendingAccountOperation("original_link_operation_123456", "deriv_oauth_link", "owner-device", "linked_once",
            scope, "b".repeat(64), "original_oauth_state_123456789")
        val actor = AccountOperationActor(scope, original.deviceId, "current-token-context")
        var sends = 0
        AccountOperationRecovery(disk).dispatch(original, actor, { actor }) { guard ->
            guard(); assertEquals(listOf(original), AccountOperationRecovery(disk).pending(original.deviceId))
            sends += 1
            409 to """{"effect_state":"UNKNOWN","reconciliation_required":true}"""
        }
        val cold = AccountOperationRecovery(disk)
        assertEquals(original.oauthState, cold.pending(original.deviceId).single().oauthState)
        assertThrows(IllegalStateException::class.java) { cold.remember(original.copy(operationId = "another_link_operation_123456")) }
        val receipt = """{"operation_id":"${original.operationId}","device_id":"${original.deviceId}","action":"${original.action}",
            "oauth_state":"${original.oauthState}","account_control_domain":"${scope.nativeOwnerDomain}",
            "native_resource_version":"${"c".repeat(64)}","effect_state":"APPLIED","reconciliation_required":false,
            "account":{"alias":"linked_once","broker":"DERIV"}}"""
        assertFalse(cold.observe(original, receipt.replace(original.oauthState!!, "replacement_oauth_state_123456"), 200, scope))
        assertFalse(cold.observe(original, receipt, 200, scope.copy(nativeOwnerDomain = "d".repeat(64))))
        var reads = 0
        cold.recover(original, actor, { actor }) { guard -> guard(); reads += 1; 200 to receipt }
        assertEquals(1, sends); assertEquals(1, reads)
        assertTrue(cold.pending(original.deviceId).isEmpty())
        assertFalse(disk.text!!.contains("token")); assertFalse(disk.text!!.contains("verification_code"))
        assertFalse(disk.text!!.contains("password")); assertFalse(disk.text!!.contains("signature"))
    }

    @Test fun oauthLinkFailedPersistenceAndChangedActorCannotDispatchOrClearOriginal() = runBlocking {
        val disk = Disk()
        val value = PendingAccountOperation("original_link_operation_123456", "ctrader_link", "owner-device", "linked_once",
            scope, "b".repeat(64), "original_oauth_state_123456789")
        val actor = AccountOperationActor(scope, value.deviceId, "current-token")
        disk.writable = false; var sends = 0
        try { AccountOperationRecovery(disk).dispatch(value, actor, { actor }) { sends += 1; 200 to "{}" }; fail("durable write must fail") }
        catch (expected: IllegalStateException) { }
        assertEquals(0, sends)
        disk.writable = true
        var current = actor
        disk.afterSave = { current = actor.copy(credentialContext = "replacement-token") }
        try { AccountOperationRecovery(disk).dispatch(value, actor, { current }) { sends += 1; 200 to "{}" }; fail("changed actor must refuse") }
        catch (expected: IllegalStateException) { }
        assertEquals(0, sends)
        assertEquals(listOf(value), AccountOperationRecovery(disk).pending(value.deviceId))
        assertFalse(AccountOperationRecovery(disk).observe(value,
            """{"status":"RECORDED_APPLIED_UNBOUND","scope_status":"UNBOUND","native_reconciliation_required":true}""", 200, scope))
    }

    private class Disk : AccountOperationStore {
        var text: String? = null
        var writable = true
        var afterSave: (() -> Unit)? = null
        override fun load() = text
        override fun save(value: String): Boolean {
            if (!writable) return false
            text = value; afterSave?.invoke(); return true
        }
    }
    private val scope = AccountOperationScope("https://gateway.fixture", "profile-fixture", "provision-fixture", "a".repeat(64))
    private val original = PendingAccountOperation("original_operation_id_12345", "mt5_ea_issue_key", "owner-device", "owner_mt5", scope, "b".repeat(64))

    @Test fun demoCreationPersistsBeforeDispatchAndColdRecoveryNeverAuthorizesResend() {
        val disk = Disk()
        val demo = original.copy(action = "deriv_create_demo", alias = "owner_demo")
        assertTrue(AccountOperationRecovery.JOURNALED_ACTIONS.contains(demo.action))
        AccountOperationRecovery(disk).remember(demo)
        val cold = AccountOperationRecovery(disk)
        assertEquals(listOf(demo), cold.pending(demo.deviceId))
        assertThrows(IllegalStateException::class.java) { cold.remember(demo) }
        assertThrows(IllegalStateException::class.java) { cold.remember(demo.copy(operationId = "another_operation_id_12345")) }
        assertThrows(IllegalStateException::class.java) { cold.remember(demo.copy(operationId = "another_operation_id_12345", alias = "changed_alias")) }
        val unknown = """{"operation_id":"${demo.operationId}","action":"deriv_create_demo","effect_state":"UNKNOWN","reconciliation_required":true}"""
        assertFalse(cold.observe(demo, unknown, 200, scope))
        assertEquals(listOf(demo), AccountOperationRecovery(disk).pending(demo.deviceId))
        val outcome = AccountOnboarding.parseOutcome(demo.action, unknown, 409)
        assertFalse(outcome.ok); assertTrue(outcome.message.contains("Hold creation"))
        assertTrue(outcome.message.contains("do not create another account"))
        assertFalse(disk.text!!.contains("password")); assertFalse(disk.text!!.contains("email"))
        assertFalse(disk.text!!.contains("verification_code")); assertFalse(disk.text!!.contains("args"))
        disk.writable = false
        assertThrows(IllegalStateException::class.java) { cold.remember(demo.copy(operationId = "unrelated_operation_id_12345", alias = "independent")) }
    }

    @Test fun demoOriginalClearsOnlyFromItsBoundNativeDemoReceipt() {
        val disk = Disk()
        val demo = original.copy(action = "deriv_create_demo", alias = "owner_demo")
        val history = AccountOperationRecovery(disk); history.remember(demo)
        val receipt = """{"operation_id":"${demo.operationId}","action":"deriv_create_demo","effect_state":"APPLIED","reconciliation_required":false,"account_control_domain":"${scope.nativeOwnerDomain}","result":{"account":{"alias":"owner_demo","broker":"DERIV","mode":"DEMO_TRADER","demo":true,"safety_identity":"DEMO","login":"VRTC900","currency":"USD"},"client_id":"VRTC900","currency":"USD"}}"""
        for (invalid in listOf(receipt.replace("owner_demo", "foreign_alias"), receipt.replace("\"demo\":true", "\"demo\":false"),
            receipt.replace("\"client_id\":\"VRTC900\"", "\"client_id\":\"OTHER\""), receipt.replace("DEMO_TRADER", "AUTONOMOUS_LIVE"))) {
            assertFalse(history.observe(demo, invalid, 200, scope))
            assertEquals(listOf(demo), history.pending(demo.deviceId))
        }
        assertTrue(history.observe(demo, receipt, 200, scope))
        assertTrue(history.pending(demo.deviceId).isEmpty())
    }
    @Test fun newObserveDemoReceiptPreservesNativeIdentityAndClearsOnlyItsOriginal() {
        val disk = Disk()
        val demo = original.copy(action = "deriv_create_demo", alias = "owner_demo")
        val history = AccountOperationRecovery(disk); history.remember(demo)
        val receipt = """{"operation_id":"${demo.operationId}","action":"deriv_create_demo","effect_state":"APPLIED","reconciliation_required":false,"account_control_domain":"${scope.nativeOwnerDomain}","result":{"account":{"alias":"owner_demo","broker":"DERIV","mode":"OBSERVE","demo":true,"safety_identity":"READ ONLY","login":"VRTC900","currency":"USD"},"client_id":"VRTC900","currency":"USD"}}"""
        for (invalid in listOf(receipt.replace("READ ONLY", "DEMO"), receipt.replace("OBSERVE", "AUTONOMOUS_LIVE"),
            receipt.replace("owner_demo", "foreign_alias"), receipt.replace("\"demo\":true", "\"demo\":false"),
            receipt.replace("\"client_id\":\"VRTC900\"", "\"client_id\":\"OTHER\""))) {
            assertFalse(history.observe(demo, invalid, 200, scope))
            assertEquals(listOf(demo), history.pending(demo.deviceId))
        }
        assertTrue(history.observe(demo, receipt, 200, scope))
        assertTrue(history.pending(demo.deviceId).isEmpty())
    }

    private fun response(state: String = "APPLIED", id: String = original.operationId,
                         action: String = original.action, reconcile: Boolean = false) =
        """{"operation_id":"$id","action":"$action","effect_state":"$state","reconciliation_required":$reconcile,"account_control_domain":"${scope.nativeOwnerDomain}","result":{"account":{"alias":"owner_mt5"},"credential_export_available":false}}"""

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
            assertFalse(history.observe(original, body, 200, scope))
            assertEquals(listOf(original), history.pending(original.deviceId))
        }
        assertFalse(history.observe(original, response(), 502, scope))
        assertTrue(history.observe(original, response(), 200, scope))
        assertTrue(AccountOperationRecovery(disk).pending(original.deviceId).isEmpty())
    }

    @Test fun refusalCanClearButAnUnreadableOrMissingHistoryCannotBeReplaced() {
        val disk = Disk(); val history = AccountOperationRecovery(disk); history.remember(original)
        assertTrue(history.observe(original, response("REFUSED"), 200, scope))
        disk.text = "corrupt original state"
        assertThrows(Exception::class.java) { history.remember(original) }
        assertEquals("corrupt original state", disk.text)
    }

    @Test fun failureToSaveAConfirmedReadbackStillKeepsTheOriginalIdentity() {
        val disk = Disk(); val history = AccountOperationRecovery(disk); history.remember(original)
        disk.writable = false
        assertThrows(IllegalStateException::class.java) { history.observe(original, response(), 200, scope) }
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

    @Test fun actualDispatchStateMachineFencesActorChangesAtEveryEffectBoundary() = runBlocking {
        val start = AccountOperationActor(scope,original.deviceId,"current-token-context")
        val changes = listOf(start.copy(scope=scope.copy(root="https://replacement.fixture")),
            start.copy(scope=scope.copy(profileId="replacement-profile")),
            start.copy(scope=scope.copy(provisioningId="replacement-provision")),
            start.copy(scope=scope.copy(nativeOwnerDomain="c".repeat(64))),
            start.copy(deviceId="replacement-device"),start.copy(credentialContext="rotated-token-context"))
        for (changed in changes) for (stage in listOf("before","persist","request","response")) {
            val disk=Disk();val history=AccountOperationRecovery(disk)
            var current=if(stage=="before") changed else start
            var effects=0
            if(stage=="persist") disk.afterSave={current=changed}
            try {
                history.dispatch(original,start,{current}) { guard ->
                    if(stage=="request") current=changed
                    guard(); effects++
                    if(stage=="response") current=changed
                    200 to response()
                }
                fail("Changed original scope must refuse")
            } catch (_: IllegalStateException) { }
            assertEquals(if(stage=="response") 1 else 0,effects)
            assertEquals(if(stage=="before") emptyList() else listOf(original),history.pending(original.deviceId))
        }
    }

    @Test fun cancelledJobNeverSendsAfterPersistenceOrClearsAfterAnEffect() = runBlocking {
        val actor=AccountOperationActor(scope,original.deviceId,"live-token-context")
        for (stage in listOf("persist","request","response")) {
            val disk=Disk();val history=AccountOperationRecovery(disk);val job=Job();var effects=0
            if(stage=="persist") disk.afterSave={job.cancel()}
            try {
                withContext(job) {
                    history.dispatch(original,actor,{actor}) { guard ->
                        if(stage=="request") job.cancel()
                        guard();effects++
                        if(stage=="response") job.cancel()
                        200 to response()
                    }
                }
                fail("Cancelled caller must stop")
            } catch (_: CancellationException) { }
            assertEquals(if(stage=="response") 1 else 0,effects)
            assertEquals(listOf(original),history.pending(original.deviceId))
        }
    }

    @Test fun originalReadRequiresLawfulOriginalScopeAndRechecksAfterReply() = runBlocking {
        val actor=AccountOperationActor(scope,original.deviceId,"current-token-context")
        val changes=listOf(actor.copy(scope=scope.copy(root="https://replacement.fixture")),
            actor.copy(scope=scope.copy(nativeOwnerDomain="c".repeat(64))),actor.copy(deviceId="other-device"),
            actor.copy(credentialContext="new-token"))
        for(changed in changes) {
            val disk=Disk();val history=AccountOperationRecovery(disk);history.remember(original)
            var current=actor;var requests=0
            try {
                history.recover(original,actor,{current}) { guard ->
                    guard();requests++;current=changed
                    200 to response()
                }
                fail("Reply from changed context cannot complete original")
            } catch (_: IllegalStateException) { }
            assertEquals(1,requests);assertEquals(listOf(original),history.pending(original.deviceId))
        }
        val disk=Disk();val history=AccountOperationRecovery(disk);history.remember(original)
        val wrong=actor.copy(scope=scope.copy(root="https://replacement.fixture"));var requests=0
        try { history.recover(original,wrong,{wrong}) {requests++;200 to response()};fail("Wrong original root") }
        catch (_: IllegalStateException) { }
        assertEquals(0,requests)
        // Current lawful credential renewal can read the SAME original domain;
        // no old token is persisted or reused as an execution grant.
        val renewed=actor.copy(credentialContext="lawful-renewed-token")
        history.recover(original,renewed,{renewed}) {guard->guard();200 to response()}
        assertTrue(history.pending(original.deviceId).isEmpty())
    }

    @Test fun legacyUnboundRecordsAreRetainedAndNeverGuessedIntoCurrentProfile() = runBlocking {
        val disk=Disk()
        disk.text="""{"schema":"van.android.account-operations/1","operations":[{"operation_id":"${original.operationId}","action":"deriv_create_demo","device_id":"${original.deviceId}","alias":"${original.alias}"}]}"""
        val history=AccountOperationRecovery(disk);val legacy=history.pending(original.deviceId).single()
        assertNull(legacy.scope);assertNull(legacy.requestIdentity)
        assertFalse(history.observe(legacy,response(action="deriv_create_demo"),200,scope))
        var requests=0;val actor=AccountOperationActor(scope,original.deviceId,"current")
        try { history.recover(legacy,actor,{actor}) {requests++;200 to response()};fail("Unbound original") }
        catch (_: IllegalStateException) { }
        assertEquals(0,requests)
        assertThrows(IllegalStateException::class.java) {history.remember(original.copy(action="deriv_create_demo"))}
        assertTrue(history.blocks("deriv_create_demo","other_alias",scope.copy(nativeOwnerDomain="c".repeat(64))))
        // An unrelated original can be written without deleting or rebinding
        // the legacy row during the existing-store v1→v2 migration.
        history.remember(original.copy(operationId="unrelated_operation_id_12345",alias="independent"))
        val cold=AccountOperationRecovery(disk).pending(original.deviceId)
        assertEquals(2,cold.size);assertEquals(legacy,cold.first());assertNull(cold.first().scope)
    }

    @Test fun authenticatedIndependentDomainsCoexistButProfileLabelsDoNotEstablishIndependence() {
        // Descriptor fixtures represent data from the authenticated native
        // producer contract, never domain identities derived from these URLs.
        val disk=Disk();val history=AccountOperationRecovery(disk)
        val a=original.copy(action="deriv_create_demo")
        val b=a.copy(scope=scope.copy(root="https://other.fixture",profileId="other-local-profile",nativeOwnerDomain="c".repeat(64)))
        history.remember(a);history.remember(b)
        assertEquals(listOf(a,b),AccountOperationRecovery(disk).pending(original.deviceId))
        assertFalse(history.observe(a,response(action="deriv_create_demo"),200,b.scope))
        assertEquals(2,history.pending(original.deviceId).size)
        val sameNativeDifferentRoot=a.copy(operationId="another_operation_id_12345",scope=scope.copy(root="https://alias.fixture"))
        assertThrows(IllegalStateException::class.java) {history.remember(sameNativeDifferentRoot)}
        assertTrue(history.blocks("deriv_create_demo","other_alias",sameNativeDifferentRoot.scope!!))
        val trulyOther=scope.copy(nativeOwnerDomain="d".repeat(64))
        assertFalse(history.blocks("deriv_create_demo","other_alias",trulyOther))
    }

    @Test fun completedOriginalFromIndependentDomainCannotClearOrRetargetAnotherOriginal() = runBlocking {
        val disk=Disk();val history=AccountOperationRecovery(disk)
        val a=original.copy(action="deriv_create_demo")
        val b=a.copy(scope=scope.copy(root="https://other.fixture",nativeOwnerDomain="c".repeat(64)))
        history.remember(a);history.remember(b)
        val body="""{"operation_id":"${b.operationId}","action":"deriv_create_demo","effect_state":"APPLIED","reconciliation_required":false,"account_control_domain":"${b.scope!!.nativeOwnerDomain}","result":{"account":{"alias":"${b.alias}","broker":"DERIV","mode":"DEMO_TRADER","demo":true,"safety_identity":"DEMO","login":"VRTC900","currency":"USD"},"client_id":"VRTC900","currency":"USD"}}"""
        val actorA=AccountOperationActor(scope,original.deviceId,"current-a")
        try {history.recover(a,actorA,{actorA}) {200 to body};fail("Foreign domain receipt must remain unconfirmed")}
        catch (_: IllegalStateException) { }
        assertEquals(listOf(a,b),history.pending(original.deviceId))
        val actorB=AccountOperationActor(b.scope!!,b.deviceId,"current-b")
        history.recover(b,actorB,{actorB}) {guard->guard();200 to body}
        assertEquals(listOf(a),AccountOperationRecovery(disk).pending(original.deviceId))
    }
}
