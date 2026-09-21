package com.dial.van.voice

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import org.json.JSONObject

/**
 * Rev 1.5 §21 — the offline voice edge, driven by the cases nobody can stage on a phone.
 *
 * A bundle that ships a voice and no ears. An answer that finishes at three in the morning.
 * A reconnect halfway through a sentence. VAN hearing itself through the speaker and
 * interrupting itself. Each of those is a real failure and none of them can be produced on
 * demand, which is why the decisions are pure and live here.
 *
 * What these do not test: that any model exists. `VAN-ADOPT-OFFLINE-VOICE-RUNTIME-001` is
 * explicit that the repository builds the loader, the manifest and the classification and
 * cannot author a model, so the expected state of a real bundle today is that every
 * capability is absent — and the tests assert that VAN says so rather than looking broken.
 */
class VoiceAssetManifestTest {

    private fun manifest(vararg files: Triple<String, String, String>): String {
        val json = JSONObject()
            .put("schema", VoiceAssetManifest.SCHEMA)
            .put("bundle_version", "2026.09.1")
            .put("vocabulary_revision", "vocab-7")
        val array = org.json.JSONArray()
        files.forEach { (capability, path, sha) ->
            array.put(
                JSONObject().put("capability", capability).put("path", path)
                    .put("sha256", sha).put("size", 1_048_576),
            )
        }
        return json.put("files", array).toString()
    }

    private val digest = "a".repeat(64)

    @Test
    fun `a well formed bundle parses`() {
        val verdict = VoiceAssetManifest.parse(manifest(Triple("tts", "voice/tts.onnx", digest)))
        val bundle = (verdict as VoiceManifestVerdict.Accepted).bundle
        assertEquals("2026.09.1", bundle.bundleVersion)
        assertEquals(1, bundle.entriesFor(VoiceCapability.LOCAL_TTS).size)
    }

    @Test
    fun `an unversioned bundle is refused`() {
        // Without a version there is no way to tell an upgrade from a replacement.
        val json = JSONObject().put("schema", VoiceAssetManifest.SCHEMA).toString()
        assertEquals(
            "voice_manifest_unversioned",
            (VoiceAssetManifest.parse(json) as VoiceManifestVerdict.Refused).reason,
        )
    }

    @Test
    fun `a file with no usable digest is refused rather than trusted`() {
        // An unverifiable model decides what VAN hears.
        val verdict = VoiceAssetManifest.parse(manifest(Triple("asr", "voice/asr.onnx", "short")))
        assertTrue((verdict as VoiceManifestVerdict.Refused).reason.startsWith("voice_manifest_bad_digest"))
    }

    @Test
    fun `an unknown capability is refused rather than ignored`() {
        val verdict = VoiceAssetManifest.parse(manifest(Triple("telepathy", "x", digest)))
        assertTrue((verdict as VoiceManifestVerdict.Refused).reason.startsWith("voice_manifest_unknown_capability"))
    }

    @Test
    fun `malformed json is refused rather than throwing at the caller`() {
        assertEquals(
            "voice_manifest_malformed",
            (VoiceAssetManifest.parse("{not json") as VoiceManifestVerdict.Refused).reason,
        )
    }

    @Test
    fun `capabilities fail independently`() {
        // The case this whole file is for: a bundle that can speak and cannot hear. Saying
        // "voice is unavailable" for that is a different and wrong sentence.
        val bundle = (VoiceAssetManifest.parse(
            manifest(
                Triple("tts", "voice/tts.onnx", digest),
                Triple("asr", "voice/asr.onnx", "b".repeat(64)),
            ),
        ) as VoiceManifestVerdict.Accepted).bundle

        val observed = mapOf("voice/tts.onnx" to (digest to 1_048_576L))
        val statuses = VoiceAssetManifest.classifyAll(bundle, observed)

        assertTrue(statuses.getValue(VoiceCapability.LOCAL_TTS).ready)
        assertEquals(VoiceAssetState.MISSING, statuses.getValue(VoiceCapability.LOCAL_ASR).state)
        assertTrue(statuses.getValue(VoiceCapability.LOCAL_ASR).sentence.contains("network"))
    }

    @Test
    fun `a substituted model is refused`() {
        val bundle = (VoiceAssetManifest.parse(
            manifest(Triple("asr", "voice/asr.onnx", digest)),
        ) as VoiceManifestVerdict.Accepted).bundle
        val observed = mapOf("voice/asr.onnx" to ("b".repeat(64) to 1_048_576L))
        assertEquals(
            VoiceAssetState.DIGEST_MISMATCH,
            VoiceAssetManifest.classify(bundle, VoiceCapability.LOCAL_ASR, observed).state,
        )
    }

    @Test
    fun `a placeholder sized file is unusable rather than ready`() {
        val bundle = (VoiceAssetManifest.parse(
            manifest(Triple("vad", "voice/vad.onnx", digest)),
        ) as VoiceManifestVerdict.Accepted).bundle
        val observed = mapOf("voice/vad.onnx" to (digest to 12L))
        assertEquals(
            VoiceAssetState.UNUSABLE,
            VoiceAssetManifest.classify(bundle, VoiceCapability.LOCAL_VAD, observed).state,
        )
    }

    @Test
    fun `no bundle at all reports not declared for everything`() {
        // Today's honest state. It must read as "not installed", not as an error.
        val statuses = VoiceAssetManifest.classifyAll(null, emptyMap())
        assertEquals(VoiceCapability.entries.size, statuses.size)
        assertTrue(statuses.values.all { it.state == VoiceAssetState.NOT_DECLARED })
        assertEquals(VoiceCapability.entries.size, VoiceAssetManifest.releaseBlockers(statuses).size)
    }

    @Test
    fun `every state has a sentence and none of them names an enum or a path`() {
        for (capability in VoiceCapability.entries) {
            for (state in VoiceAssetState.entries) {
                val sentence = VoiceAssetStatus(capability, state).sentence
                assertTrue(sentence.isNotBlank(), "$capability/$state")
                assertFalse(sentence.contains("_"), sentence)
                assertFalse(sentence.contains("/"), sentence)
            }
        }
    }
}

class OfflineCommandClassifierTest {

    @Test
    fun `irreversible work is never ordinary work`() {
        for (phrase in listOf("send that email", "delete the file", "pay the invoice", "transfer 400")) {
            assertEquals(
                CommandRouting.OWNER_APPROVAL_REQUIRED,
                OfflineCommandClassifier.classify(phrase),
                phrase,
            )
        }
    }

    @Test
    fun `the gateway's action class outranks the phrasing`() {
        // The Gateway knows what the command does; a phrase match is a guess about that.
        assertEquals(
            CommandRouting.OWNER_APPROVAL_REQUIRED,
            OfflineCommandClassifier.classify("show me the thing", actionClass = "A5"),
        )
    }

    @Test
    fun `approval-bearing work is never queued offline`() {
        assertFalse(OfflineCommandClassifier.mayQueueOffline(CommandRouting.OWNER_APPROVAL_REQUIRED))
        assertFalse(OfflineCommandClassifier.mayQueueOffline(CommandRouting.LOCAL_EXECUTABLE))
        assertTrue(OfflineCommandClassifier.mayQueueOffline(CommandRouting.REMOTE_REQUIRED))
    }

    @Test
    fun `things VAN can do on the phone are local`() {
        assertEquals(CommandRouting.LOCAL_EXECUTABLE, OfflineCommandClassifier.classify("repeat that"))
        assertEquals(CommandRouting.LOCAL_EXECUTABLE, OfflineCommandClassifier.classify("open VAN Browser"))
    }

    @Test
    fun `things that need the world are remote`() {
        assertEquals(CommandRouting.REMOTE_REQUIRED, OfflineCommandClassifier.classify("search the web for tides"))
        assertEquals(CommandRouting.REMOTE_REQUIRED, OfflineCommandClassifier.classify("what is the weather"))
    }

    @Test
    fun `an unrecognised request is not assumed to be local`() {
        // Guessing "I can do that here" produces a confident wrong answer with no network
        // to correct it.
        assertEquals(
            CommandRouting.REMOTE_OPTIONAL,
            OfflineCommandClassifier.classify("what did Kepler actually prove"),
        )
    }

    @Test
    fun `VAN says something true when it cannot reach Hermes`() {
        val sentence = OfflineCommandClassifier.offlineSentence(CommandRouting.REMOTE_REQUIRED)
        assertTrue(sentence.contains("can't reach"))
        // And says nothing at all for work it can just do.
        assertEquals("", OfflineCommandClassifier.offlineSentence(CommandRouting.LOCAL_EXECUTABLE))
    }
}

class VoiceTurnTest {

    @Test
    fun `a failover keeps the turn and the command`() {
        // §21.12. Minting new ids on reconnect turns one spoken instruction into two
        // executions, and the owner never sees the second one coming.
        val turn = VoiceTurn("turn_196", "wake_9").submittedAs("cmd_12")
        val revised = turn.withRevisedTranscript()
        assertEquals("turn_196", revised.turnId)
        assertEquals("cmd_12", revised.commandId)
        assertEquals(1, revised.transcriptRevision)
    }

    @Test
    fun `speaking survives a transport failover`() {
        // The segments are already local. Cutting the owner off mid-sentence to report a
        // network event is worse than the event.
        assertTrue(VoiceState.SPEAKING.survivesTransportFailover)
        assertFalse(VoiceState.REMOTE_SUBMITTING.survivesTransportFailover)
    }

    @Test
    fun `only a completed answer counts as heard`() {
        assertTrue(VoiceOutputOutcome.TTS_COMPLETED.ownerHeardTheWholeAnswer)
        assertFalse(VoiceOutputOutcome.RESPONSE_RECEIVED.ownerHeardTheWholeAnswer)
        // A barge-in is not a delivered answer: they heard some of it and stopped it.
        assertFalse(VoiceOutputOutcome.OWNER_INTERRUPTED.ownerHeardTheWholeAnswer)
    }
}

class SpeechQueueTest {

    private fun segment(index: Int, final: Boolean = false, interruptible: Boolean = true) =
        SpeechSegment(
            responseId = "rsp_58",
            speechStreamId = "sp_58",
            segmentId = "sp_58_%04d".format(index),
            segmentIndex = index,
            text = "segment $index",
            final = final,
            interruptible = interruptible,
        )

    @Test
    fun `a reconnect does not replay what the owner already heard`() {
        // §21.16, the failure this whole file exists for: "Here is your answer..." starting
        // again from the beginning after a path switch.
        val queue = SpeechQueue()
        (0..4).forEach { queue.offer(segment(it)) }
        (0..2).forEach { queue.mark("sp_58_%04d".format(it), SpeechSegmentState.SPOKEN) }

        assertFalse(queue.offer(segment(1)), "a segment already spoken must not be re-queued")
        assertEquals(3, queue.cursors().resumeFromSegment)
    }

    @Test
    fun `a renumbered stream cannot replay text the owner already heard`() {
        // The isolating case for the index check, which a mutation survived because the id
        // check covered the same scenario in every other test. Here the id is *new* — a
        // Gateway that re-segmented the same answer — so only the index can refuse it.
        val queue = SpeechQueue()
        (0..2).forEach { queue.offer(segment(it)) }
        (0..2).forEach { queue.mark("sp_58_%04d".format(it), SpeechSegmentState.SPOKEN) }

        val renumbered = segment(1).copy(segmentId = "sp_58_0001_v2", text = "spoken already")
        assertFalse(
            queue.offer(renumbered),
            "a new id for text at an index the owner has heard is still a replay",
        )
    }

    @Test
    fun `a segment from another answer is not queued behind this one`() {
        val queue = SpeechQueue()
        queue.offer(segment(0))
        val otherAnswer = segment(1).copy(speechStreamId = "sp_99", segmentId = "sp_99_0001")
        assertFalse(queue.offer(otherAnswer), "two answers in one queue interleave")
    }

    @Test
    fun `a duplicate after a failover is discarded silently`() {
        val queue = SpeechQueue()
        assertTrue(queue.offer(segment(4)))
        assertFalse(queue.offer(segment(4)), "the Gateway resends from a cursor; overlap is expected")
    }

    @Test
    fun `the two cursors are different numbers`() {
        // Received is not spoken. A resume that reported only one of them cannot be right.
        val queue = SpeechQueue()
        (0..4).forEach { queue.offer(segment(it)) }
        queue.mark("sp_58_0000", SpeechSegmentState.SPOKEN)
        queue.mark("sp_58_0001", SpeechSegmentState.SPOKEN)

        val cursors = queue.cursors()
        assertEquals(4, cursors.lastReceivedSegment)
        assertEquals(1, cursors.lastSpokenSegment)
        assertEquals(2, cursors.resumeFromSegment, "resuming from received would skip 2, 3 and 4")
    }

    @Test
    fun `barge-in interrupts rather than deletes`() {
        // "VAN was cut off" and "VAN had nothing to say" are different facts and the turn's
        // record needs both.
        val queue = SpeechQueue()
        (0..3).forEach { queue.offer(segment(it)) }
        queue.mark("sp_58_0000", SpeechSegmentState.SPOKEN)
        queue.mark("sp_58_0001", SpeechSegmentState.SPEAKING)

        assertEquals(3, queue.bargeIn())
        val states = queue.snapshot().map { it.state }
        assertEquals(SpeechSegmentState.SPOKEN, states[0])
        assertTrue(states.drop(1).all { it == SpeechSegmentState.INTERRUPTED })
    }

    @Test
    fun `speech is complete only when the final segment was spoken`() {
        val queue = SpeechQueue()
        queue.offer(segment(0))
        queue.offer(segment(1, final = true))
        queue.mark("sp_58_0001", SpeechSegmentState.READY)
        assertFalse(queue.completed(), "delivered is not heard")
        queue.mark("sp_58_0001", SpeechSegmentState.SPOKEN)
        assertTrue(queue.completed())
    }

    @Test
    fun `the synthesis queue stays shallow`() {
        // §21.17 — a deep queue makes a barge-in discard audio the owner waited through.
        val queue = SpeechQueue()
        (0..5).forEach { queue.offer(segment(it)) }
        assertTrue(queue.shouldSynthesiseMore())
        queue.mark("sp_58_0000", SpeechSegmentState.READY)
        queue.mark("sp_58_0001", SpeechSegmentState.READY)
        assertFalse(queue.shouldSynthesiseMore())
        assertEquals(2, queue.synthesisTarget())
    }

    @Test
    fun `the next segment to speak is the lowest ready one`() {
        val queue = SpeechQueue()
        (0..3).forEach { queue.offer(segment(it)) }
        queue.mark("sp_58_0002", SpeechSegmentState.READY)
        queue.mark("sp_58_0001", SpeechSegmentState.READY)
        assertEquals(1, queue.nextToSpeak()?.segmentIndex)
    }

    @Test
    fun `nothing ready means nothing to speak rather than an arbitrary segment`() {
        val queue = SpeechQueue()
        queue.offer(segment(0))
        assertNull(queue.nextToSpeak())
    }
}

class DelayedAnswerPolicyTest {

    @Test
    fun `an answer that arrives at three in the morning does not speak`() {
        // §21.25, stated as the failure it is: the owner asked hours ago, put the phone
        // down, and VAN starts talking.
        assertEquals(
            DelayedAnswerAction.NOTIFY_ONLY,
            DelayedAnswerPolicy.decide(
                askedAtMs = 0,
                completedAtMs = 6 * 60 * 60 * 1000,
                ownerStillInVoiceContext = false,
                screenInteractive = false,
            ),
        )
    }

    @Test
    fun `an answer that arrives while the owner is still here speaks normally`() {
        assertEquals(
            DelayedAnswerAction.SPEAK_NOW,
            DelayedAnswerPolicy.decide(
                askedAtMs = 0, completedAtMs = 30_000,
                ownerStillInVoiceContext = true, screenInteractive = true,
            ),
        )
    }

    @Test
    fun `still in context but long past the window does not speak unprompted`() {
        assertEquals(
            DelayedAnswerAction.SHOW_WITHOUT_SPEAKING,
            DelayedAnswerPolicy.decide(
                askedAtMs = 0,
                completedAtMs = DelayedAnswerPolicy.SAME_CONTEXT_WINDOW_MS + 1,
                ownerStillInVoiceContext = true, screenInteractive = true,
            ),
        )
    }

    @Test
    fun `holding the phone gets it on screen without taking the audio`() {
        assertEquals(
            DelayedAnswerAction.SHOW_WITHOUT_SPEAKING,
            DelayedAnswerPolicy.decide(
                askedAtMs = 0, completedAtMs = 10 * 60_000,
                ownerStillInVoiceContext = false, screenInteractive = true,
            ),
        )
    }
}
