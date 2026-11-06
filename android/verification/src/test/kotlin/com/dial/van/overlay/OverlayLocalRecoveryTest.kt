package com.dial.van.overlay

import com.dial.van.visual.VanDoubleTapAction
import com.dial.van.visual.VanExpressionLevel
import com.dial.van.visual.VanPresentationPreferences
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.test.assertFailsWith

class OverlayLocalRecoveryTest {
    private val scope = "a".repeat(64)
    private val now = 1_800_000_000_000L
    private fun original() = OverlayLocalSession(scope, 9, "Please review the result", now, "CHAT",
        VanPresentationPreferences(VanExpressionLevel.BALANCED, true, 80, true, VanDoubleTapAction.CHAT))
    private fun decode(raw: String?) = OverlayLocalSessionCodec.decode(raw, scope, now)
    private fun altered(field: String, value: Any) = JSONObject(OverlayLocalSessionCodec.encode(original())).put(field,value).toString()

    @Test fun exactLocalSnapshotRoundTripsWithoutAnExecutionFlag() {
        val result = decode(OverlayLocalSessionCodec.encode(original()))
        assertEquals(OverlayRecoveryStatus.AVAILABLE,result.status);assertEquals(original(),result.session)
        val encoded=OverlayLocalSessionCodec.encode(original())
        for (forbidden in listOf("microphone","approval","bearer","send_now","command_id","speech_audio")) assertFalse(encoded.contains(forbidden))
    }
    @Test fun absentStateUsesSafeDefaults() {
        val restored=decode(null);assertEquals(OverlayRecoveryStatus.EMPTY,restored.status)
        assertEquals("",restored.session.draft);assertEquals("CONTEXT",restored.session.mode)
    }
    @Test fun recoveredVoiceOrSettingsNeverStartsThatSurfaceAutomatically() {
        for (mode in listOf("VOICE","SETTINGS")) {
            val value=original().copy(mode=mode)
            assertEquals("CONTEXT",decode(OverlayLocalSessionCodec.encode(value)).session.mode)
        }
    }
    @Test fun ownerMismatchDoesNotExposeAnotherOwnersDraftOrSettings() {
        val result=OverlayLocalSessionCodec.decode(OverlayLocalSessionCodec.encode(original()),"b".repeat(64),now)
        assertEquals(OverlayRecoveryStatus.WRONG_OWNER,result.status);assertEquals("",result.session.draft)
        assertEquals(VanPresentationPreferences(),result.session.preferences)
    }
    @Test fun unboundOrMalformedOwnerIsRejectedWithoutReadingDraft() {
        for (identity in listOf("","owner-name","A".repeat(64),"a".repeat(63))) {
            assertEquals(OverlayRecoveryStatus.INVALID,OverlayLocalSessionCodec.decode(OverlayLocalSessionCodec.encode(original()),identity,now).status)
        }
    }
    @Test fun sevenDayDraftRetentionExpiresTextButKeepsPreferences() {
        val s=original().copy(savedAtMs=now-OverlayLocalSessionCodec.DRAFT_RETENTION_MS-1)
        val r=decode(OverlayLocalSessionCodec.encode(s));assertEquals(OverlayRecoveryStatus.EXPIRED,r.status)
        assertEquals("",r.session.draft);assertEquals(s.preferences,r.session.preferences)
    }
    @Test fun exactRetentionBoundaryIsStillRecoverable() {
        assertEquals(OverlayRecoveryStatus.AVAILABLE,decode(OverlayLocalSessionCodec.encode(original().copy(savedAtMs=now-OverlayLocalSessionCodec.DRAFT_RETENTION_MS))).status)
    }
    @Test fun futureWallClockRollbackDoesNotRestoreUnexpectedOldText() {
        assertEquals(OverlayRecoveryStatus.EXPIRED,decode(OverlayLocalSessionCodec.encode(original().copy(savedAtMs=now+300_001))).status)
    }
    @Test fun smallClockCorrectionIsToleratedWithoutExtendingTheRecord() {
        val result=decode(OverlayLocalSessionCodec.encode(original().copy(savedAtMs=now+5_000)))
        assertEquals(OverlayRecoveryStatus.AVAILABLE,result.status);assertEquals(now+5_000,result.session.savedAtMs)
    }
    @Test fun disabledRecoveryNeverSerializesTheCurrentText() {
        val s=original().copy(preferences=original().preferences.copy(rememberDraft=false))
        val raw=OverlayLocalSessionCodec.encode(s);assertFalse(raw.contains(s.draft));assertEquals("",decode(raw).session.draft)
    }
    @Test fun corruptedJsonAndWrongRootAreNotRestored() {
        for (raw in listOf("", "{", "[]", "null", "false", "{\"schema\":1}")) assertEquals(OverlayRecoveryStatus.INVALID,decode(raw).status)
    }
    @Test fun unknownSchemaDoesNotTreatFutureDataAsAnOldRecord() {
        assertEquals(OverlayRecoveryStatus.FUTURE_VERSION,decode(altered("schema",2)).status)
    }
    @Test fun scalarTypesAreStrictNotCoercedFromUnexpectedStrings() {
        for ((name,value) in listOf("schema" to "1", "saved_at_ms" to "$now", "revision" to "9", "draft" to 1, "mode" to false)) {
            assertEquals(OverlayRecoveryStatus.INVALID,decode(altered(name,value)).status,"field $name")
        }
    }
    @Test fun nonintegralOrOverflowingRevisionIsRejected() {
        for (v in listOf(-1L,1.25,Long.MAX_VALUE)) assertEquals(OverlayRecoveryStatus.INVALID,decode(altered("revision",v)).status)
    }
    @Test fun negativeAndFractionalTimestampsAreRejected() {
        for (v in listOf(-1L,0.5)) assertEquals(OverlayRecoveryStatus.INVALID,decode(altered("saved_at_ms",v)).status)
    }
    @Test fun overlongDraftAndRecordAreRejectedWithoutTruncating() {
        assertFailsWith<IllegalArgumentException>{OverlayLocalSessionCodec.encode(original().copy(draft="a".repeat(16_385)))}
        assertEquals(OverlayRecoveryStatus.INVALID,decode(altered("draft","a".repeat(16_385))).status)
        assertEquals(OverlayRecoveryStatus.INVALID,decode("x".repeat(100_001)).status)
    }
    @Test fun unicodeDraftIsPreservedExactly() {
        val text="VAN 👋🏽\n自動化 — café — chishona\t\"quoted\""
        assertEquals(text,decode(OverlayLocalSessionCodec.encode(original().copy(draft=text))).session.draft)
    }
    @Test fun opacityCannotOverflowIntoTheAllowedRange() {
        for (value in listOf(0L,101L,4_294_967_351L)) {
            val o=JSONObject(OverlayLocalSessionCodec.encode(original()));o.getJSONObject("preferences").put("idle_opacity",value)
            assertEquals(OverlayRecoveryStatus.INVALID,decode(o.toString()).status)
        }
    }
    @Test fun unknownPreferencesAreSafelyRefused() {
        for ((key,value) in listOf("expression" to "PARTY", "double_tap" to "APPROVE", "reduced_motion" to "false", "remember_draft" to 1)) {
            val o=JSONObject(OverlayLocalSessionCodec.encode(original()));o.getJSONObject("preferences").put(key,value)
            assertEquals(OverlayRecoveryStatus.INVALID,decode(o.toString()).status)
        }
    }
    @Test fun everyRestoredWorkboardReturnsToPassivePresence() {
        for (state in VanOverlayPresentation.entries) {
            val result=OverlayRestartPresentation.safe(state)
            assertTrue(result in setOf(VanOverlayPresentation.FULL_FLOATING,VanOverlayPresentation.MINIMIZED,VanOverlayPresentation.DOCKED))
        }
    }
    @Test fun writingSessionDoesNotMutateItsInputs() {
        val s=original();OverlayLocalSessionCodec.encode(s);assertEquals(original(),s)
    }
}

class OverlaySessionWriterTest {
    @Test fun rapidTypingConflatesToOneLastAcknowledgedSnapshot() {
        val jobs=mutableListOf<()->Unit>();val stored=mutableListOf<String>();val replies=mutableListOf<Pair<Long,Boolean>>()
        val w=OverlaySessionWriter(jobs::add,{stored.add(it);true}){a,b->replies.add(a to b)}
        repeat(10_000){assertTrue(w.offer(it.toLong(),"snapshot-$it"))};assertEquals(1,jobs.size);jobs.single()()
        assertEquals(listOf("snapshot-9999"),stored);assertEquals(listOf(9999L to true),replies)
    }
    @Test fun olderOrDuplicateRevisionCannotOverwriteCurrent() {
        val jobs=mutableListOf<()->Unit>();val stored=mutableListOf<String>()
        val w=OverlaySessionWriter(jobs::add,{stored.add(it);true}){_,_->}
        assertTrue(w.offer(10,"current"));assertFalse(w.offer(9,"old"));assertFalse(w.offer(10,"duplicate"));jobs.single()()
        assertEquals(listOf("current"),stored)
    }
    @Test fun newerWriteArrivingDuringPersistenceIsDrainedInOrder() {
        val jobs=mutableListOf<()->Unit>();val stored=mutableListOf<String>();lateinit var writer:OverlaySessionWriter
        writer=OverlaySessionWriter(jobs::add,{value->stored.add(value);if(value=="one")writer.offer(2,"two");true}){_,_->}
        writer.offer(1,"one");jobs.single()();assertEquals(listOf("one","two"),stored);assertEquals(1,jobs.size)
    }
    @Test fun orderlyCloseStillCommitsRequestedLastStateButRejectsNewWork() {
        val jobs=mutableListOf<()->Unit>();val stored=mutableListOf<String>()
        val w=OverlaySessionWriter(jobs::add,{stored.add(it);true}){_,_->};w.offer(1,"last");w.close();assertFalse(w.offer(2,"too late"));jobs.single()()
        assertEquals(listOf("last"),stored)
    }
    @Test fun persistenceFailureIsReportedAndNextExplicitRevisionCanRecover() {
        val jobs=mutableListOf<()->Unit>();val results=mutableListOf<Pair<Long,Boolean>>();var fail=true
        val w=OverlaySessionWriter(jobs::add,{if(fail)throw IllegalStateException("disk error") else true}){a,b->results.add(a to b)}
        w.offer(1,"one");jobs.removeAt(0)();fail=false;w.offer(2,"two");jobs.removeAt(0)()
        assertEquals(listOf(1L to false,2L to true),results)
    }
    @Test fun rejectedExecutorDoesNotClaimASavedDraft() {
        val result=mutableListOf<Boolean>();val w=OverlaySessionWriter({throw IllegalStateException("closed")},{true}){_,b->result.add(b)}
        assertFalse(w.offer(1,"draft"));assertEquals(listOf(false),result)
    }
    @Test fun backendReturningFalseIsNotConfusedWithAnAcknowledgedSave() {
        val result=mutableListOf<Boolean>();val w=OverlaySessionWriter({it()},{false}){_,b->result.add(b)}
        assertTrue(w.offer(1,"text"));assertEquals(listOf(false),result)
    }
    @Test fun oversizedOrNegativeRevisionIsRejectedBeforeScheduling() {
        val w=OverlaySessionWriter({error("must not run")},{true}){_,_->}
        assertFailsWith<IllegalArgumentException>{w.offer(-1,"x")}
        assertFailsWith<IllegalArgumentException>{w.offer(1,"x".repeat(100_001))}
    }
    @Test fun brokenUiObserverCannotStallNextDurableSnapshot() {
        val jobs=mutableListOf<()->Unit>();val saved=mutableListOf<String>()
        val writer=OverlaySessionWriter(jobs::add,{saved.add(it);true}){_,_->throw IllegalStateException("disposed UI")}
        writer.offer(1,"one");jobs.removeAt(0)();writer.offer(2,"two");jobs.removeAt(0)()
        assertEquals(listOf("one","two"),saved)
    }

    @Test fun discardedDraftCannotBeResurrectedByQueuedOldWrites() {
        val jobs=mutableListOf<()->Unit>();val values=mutableListOf<String>();val w=OverlaySessionWriter(jobs::add,{values.add(it);true}){_,_->}
        w.offer(1,"private draft");w.offer(2,"discarded empty");assertFalse(w.offer(1,"private draft"));jobs.single()()
        assertEquals(listOf("discarded empty"),values)
    }
}
