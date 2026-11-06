package com.dial.van.voice

import java.io.ByteArrayInputStream
import java.io.File
import java.nio.file.Files
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import org.json.JSONArray
import org.json.JSONObject

class AcousticDeliveryTest {
    private val keyword = "▁HE Y ▁VA N @HEY_VAN\n".toByteArray()
    private fun manifest(path: String = "wake/keywords.txt", kind: String = "keywords", bytes: ByteArray = keyword): ByteArray = JSONObject()
        .put("schema", VoiceAssetManifest.SCHEMA).put("bundle_version", "test-v1")
        .put("files", JSONArray().put(JSONObject().put("capability", "wake").put("path", path)
            .put("kind", kind).put("size", bytes.size).put("sha256", EmbeddedVoiceAssetInstaller.sha256(bytes))))
        .toString().toByteArray()

    @Test fun smallRealKeywordIsAdmittedButSmallModelIsRefused() {
        val bytes = manifest()
        val bundle = EmbeddedVoiceAssetInstaller.admit(bytes, EmbeddedVoiceAssetInstaller.sha256(bytes))
        assertEquals(VoiceAssetKind.KEYWORDS, bundle.entries.single().kind)
        assertEquals(VoiceAssetState.READY, VoiceAssetManifest.classify(bundle, VoiceCapability.LOCAL_WAKE,
            mapOf("wake/keywords.txt" to (EmbeddedVoiceAssetInstaller.sha256(keyword) to keyword.size.toLong()))).state)
        val wrongRole = manifest(kind = "model")
        assertFailsWith<IllegalStateException> { EmbeddedVoiceAssetInstaller.admit(wrongRole, EmbeddedVoiceAssetInstaller.sha256(wrongRole)) }
    }
    @Test fun manifestPinAndBoundedReadRefuseBeforeInstalling() {
        val bytes = manifest()
        assertFailsWith<IllegalArgumentException> { EmbeddedVoiceAssetInstaller.admit(bytes, "0".repeat(64)) }
        assertFailsWith<IllegalArgumentException> { EmbeddedVoiceAssetInstaller.readManifest(ByteArrayInputStream(ByteArray(256 * 1024 + 1))) }
        assertEquals(bytes.toList(), EmbeddedVoiceAssetInstaller.readManifest(ByteArrayInputStream(bytes)).toList())
    }
    @Test fun failedCopyPublishesNothingAndRetryInstallsExactBytes() {
        val root = Files.createTempDirectory("van-acoustic-install").toFile()
        try {
            val bytes = manifest(); val pin = EmbeddedVoiceAssetInstaller.sha256(bytes)
            val bundle = EmbeddedVoiceAssetInstaller.admit(bytes, pin)
            assertFailsWith<IllegalStateException> { EmbeddedVoiceAssetInstaller.install(root, bundle, pin) { ByteArrayInputStream(keyword + 1.toByte()) } }
            assertFalse(File(root, pin).exists())
            assertTrue(root.listFiles().orEmpty().isEmpty())
            val ready = EmbeddedVoiceAssetInstaller.install(root, bundle, pin) { ByteArrayInputStream(keyword) }
            assertTrue(EmbeddedVoiceAssetInstaller.verified(ready, bundle))
            assertEquals(keyword.toList(), File(ready, "wake/keywords.txt").readBytes().toList())
            // A valid installation is reused without reading asset streams again.
            assertEquals(ready, EmbeddedVoiceAssetInstaller.install(root, bundle, pin) { error("unexpected_copy") })
            File(ready, "wake/keywords.txt").writeText("corrupt")
            assertFalse(EmbeddedVoiceAssetInstaller.verified(ready, bundle))
            assertEquals(ready, EmbeddedVoiceAssetInstaller.install(root, bundle, pin) { ByteArrayInputStream(keyword) })
            assertTrue(EmbeddedVoiceAssetInstaller.verified(ready, bundle))
        } finally { root.deleteRecursively() }
    }
    @Test fun traversalAndDuplicatePathsRefuseManifest() {
        for (path in listOf("../escape", "/absolute", "wake//keyword", "wake/./keyword", "wake\\keyword")) {
            assertTrue(VoiceAssetManifest.parse(manifest(path).toString(Charsets.UTF_8)) is VoiceManifestVerdict.Refused)
        }
        val json = JSONObject(manifest().toString(Charsets.UTF_8)); json.getJSONArray("files").put(json.getJSONArray("files").getJSONObject(0))
        assertTrue(VoiceAssetManifest.parse(json.toString()) is VoiceManifestVerdict.Refused)
    }
    @Test fun byteCountAndDigestMustBothMatch() {
        val bytes = manifest(); val bundle = EmbeddedVoiceAssetInstaller.admit(bytes, EmbeddedVoiceAssetInstaller.sha256(bytes))
        assertEquals(VoiceAssetState.UNUSABLE, VoiceAssetManifest.classify(bundle, VoiceCapability.LOCAL_WAKE,
            mapOf("wake/keywords.txt" to (EmbeddedVoiceAssetInstaller.sha256(keyword) to keyword.size.toLong() + 1))).state)
        assertEquals(VoiceAssetState.DIGEST_MISMATCH, VoiceAssetManifest.classify(bundle, VoiceCapability.LOCAL_WAKE,
            mapOf("wake/keywords.txt" to ("0".repeat(64) to keyword.size.toLong()))).state)
    }
    @Test fun genericSpeakerAssetDoesNotClaimOwnerEnrollment() {
        val status = VoiceAssetStatus(VoiceCapability.LOCAL_SPEAKER, VoiceAssetState.READY)
        assertTrue(status.sentence.contains("generic"))
        assertTrue(status.sentence.contains("separate enrollment"))
    }
}

class OfflineVoiceEndpointTest {
    @Test fun silenceNeverBecomesAsrFinalAndTerminalCannotRevive() {
        val turn = OfflineVoiceTurn()
        repeat(79) { assertEquals(OfflineVoiceTurn.State.CAPTURING, turn.accept(3200, false)) }
        assertEquals(OfflineVoiceTurn.State.NO_SPEECH, turn.accept(3200, false))
        assertEquals(OfflineVoiceTurn.State.NO_SPEECH, turn.accept(3200, true))
        assertFalse(turn.heardSpeech())
    }
    @Test fun briefImpulseDoesNotQualifyAndGenuineEnergyNeedsEndSilence() {
        val turn = OfflineVoiceTurn()
        assertEquals(OfflineVoiceTurn.State.CAPTURING, turn.accept(3200, true))
        repeat(6) { assertEquals(OfflineVoiceTurn.State.CAPTURING, turn.accept(3200, false)) }
        assertFalse(turn.heardSpeech())
        assertEquals(OfflineVoiceTurn.State.CAPTURING, turn.accept(3200, true))
        repeat(5) { assertEquals(OfflineVoiceTurn.State.CAPTURING, turn.accept(3200, false)) }
        assertEquals(OfflineVoiceTurn.State.FINALIZE, turn.accept(3200, false))
        assertTrue(turn.heardSpeech())
    }
    @Test fun overlongSpeechIsRefusedInsteadOfSubmittingClippedCommand() {
        val turn = OfflineVoiceTurn()
        repeat(299) { assertEquals(OfflineVoiceTurn.State.CAPTURING, turn.accept(3200, true)) }
        assertEquals(OfflineVoiceTurn.State.TOO_LONG, turn.accept(3200, true))
    }
    @Test fun realSherpaFallbackRequiresActualEngineReadiness() {
        assertEquals(VoiceRecognitionBackend.UNAVAILABLE, VoiceRecognitionPolicy.decide(34, false, false).backend)
        val sherpa = VoiceRecognitionPolicy.decide(34, false, true)
        assertEquals(VoiceRecognitionBackend.SHERPA_PRIMARY, sherpa.backend)
        assertTrue(sherpa.callerAudioSupported)
        assertFalse(sherpa.wordEvidenceSupported)
        assertFalse(sherpa.onDeviceRecognizerRequired)
        assertTrue(VoiceRecognitionPolicy.decide(34, true, true).backend != VoiceRecognitionBackend.SHERPA_PRIMARY)
    }
}

class OfflineSpeechCoverageTest {
    private fun coverage() = VitsLexiconCoverage.parse(sequenceOf("h 0", "a 1", "v 2", "n 3", "4"),
        sequenceOf("hie h a", "van v a n", "can't h a n", "invalid h missing"))
    @Test fun wholeUtteranceFallsBackWhenAnyWordWouldBeDropped() {
        val coverage = coverage()
        assertTrue(coverage.canSpeak("Hie, VAN!"))
        assertTrue(coverage.canSpeak("can't van"))
        assertFalse(coverage.canSpeak("hie unknown van"))
        assertFalse(coverage.canSpeak("hie invalid"))
    }
    @Test fun unsupportedUnicodeNumbersAndPunctuationDoNotClaimCoverage() {
        val coverage = coverage()
        for (text in listOf("", "   ", "hie café", "hie 123", "hie/van", "hie🙂")) assertFalse(coverage.canSpeak(text), text)
    }
    @Test fun cancellationCannotBeUndoneByAnotherQueuedSpeechSegment() {
        val epoch = SpeechPlaybackEpoch()
        val old = epoch.snapshot()
        assertTrue(epoch.isCurrent(old))
        epoch.cancel()
        val next = epoch.snapshot()
        assertFalse(epoch.isCurrent(old))
        assertTrue(epoch.isCurrent(next))
        epoch.cancel()
        assertFalse(epoch.isCurrent(next))
    }
}

class SpeakerEvidenceRemovalTest {
    @Test fun aComputedScoreCannotPublishAfterRemovalOrReplacement() {
        val gate = SpeakerEvidenceRevision()
        val old = gate.snapshot()
        assertEquals(.9f, gate.admit(old, .9f))
        gate.changed()
        assertEquals(null, gate.admit(old, .9f))
        val replacement = gate.snapshot()
        assertEquals(.7f, gate.admit(replacement, .7f))
        gate.changed()
        assertEquals(null, gate.admit(replacement, .7f))
    }
}
