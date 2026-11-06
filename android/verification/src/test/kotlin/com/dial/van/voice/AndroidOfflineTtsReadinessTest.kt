package com.dial.van.voice

import java.util.Locale
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue

class AndroidOfflineTtsReadinessTest {
    private val locale = Locale.UK
    private fun voice(
        name: String = "offline",
        network: Boolean = false,
        installed: Boolean = true,
        language: Locale = locale,
        quality: Int = 100,
        latency: Int = 100,
    ) = AndroidTtsVoiceEvidence(name, language, network, installed, quality, latency)

    private class Platform(
        var selected: AndroidTtsVoiceEvidence?,
        var available: List<AndroidTtsVoiceEvidence> = emptyList(),
        var languageSupported: Boolean = true,
        var acceptSelection: Boolean = true,
        var honestReadback: Boolean = true,
        var failRead: Boolean = false,
    ) : AndroidTtsVoicePlatform {
        var languageRequests = 0
        val selections = mutableListOf<String>()
        override fun setLanguage(locale: Locale): Boolean {
            languageRequests++
            return languageSupported
        }
        override fun selectedVoice(): AndroidTtsVoiceEvidence? {
            check(!failRead) { "platform unavailable" }
            return selected
        }
        override fun voices() = available
        override fun selectVoice(name: String): Boolean {
            selections += name
            if (acceptSelection && honestReadback) selected = available.single { it.name == name }
            return acceptSelection
        }
    }

    private fun route(readiness: AndroidOfflineTtsReadiness, sherpa: Boolean = false): TtsSelection =
        LocalTtsRouter.select(
            SpeechKind.ASSISTANT_ANSWER,
            mapOf(
                TtsEngineKind.ANDROID_OFFLINE to readiness.engineReadiness(),
                TtsEngineKind.SHERPA_ONNX to TtsEngineReadiness(TtsEngineKind.SHERPA_ONNX, sherpa),
            ),
        )

    @Test fun `installed offline platform voice actually enables Android fallback`() {
        val platform = Platform(voice())
        val readiness = AndroidOfflineTtsProbe.initialize(true, platform, locale)
        assertTrue(readiness.usableOffline)
        assertEquals(1, platform.languageRequests)
        assertEquals(TtsEngineKind.ANDROID_OFFLINE, assertIs<TtsSelection.Engine>(route(readiness)).kind)
        assertEquals(TtsEngineKind.SHERPA_ONNX, assertIs<TtsSelection.Engine>(route(readiness, true)).kind)
    }

    @Test fun `initialization failure never probes or dispatches a platform voice`() {
        val platform = Platform(voice(), failRead = true)
        val readiness = AndroidOfflineTtsProbe.initialize(false, platform, locale)
        assertEquals(AndroidOfflineTtsStatus.INITIALIZATION_FAILED, readiness.status)
        assertEquals(0, platform.languageRequests)
        assertFalse(readiness.engineReadiness().installed)
        assertIs<TtsSelection.Silent>(route(readiness))
    }

    @Test fun `network only engine stays silent without selecting a network voice`() {
        val remote = voice("remote", network = true)
        val platform = Platform(remote, listOf(remote))
        val readiness = AndroidOfflineTtsProbe.prepare(platform, locale)
        assertEquals(AndroidOfflineTtsStatus.NETWORK_REQUIRED, readiness.status)
        assertTrue(platform.selections.isEmpty())
        assertIs<TtsSelection.Silent>(route(readiness))
    }

    @Test fun `network default automatically switches to an installed offline voice`() {
        val platform = Platform(voice("remote", network = true), listOf(voice()))
        val readiness = AndroidOfflineTtsProbe.prepare(platform, locale)
        assertEquals(listOf("offline"), platform.selections)
        assertEquals("offline", readiness.voiceName)
        assertIs<TtsSelection.Engine>(route(readiness))
    }

    @Test fun `advertised voice with missing data cannot be selected or spoken`() {
        val missing = voice(installed = false)
        val platform = Platform(missing, listOf(missing))
        val readiness = AndroidOfflineTtsProbe.prepare(platform, locale)
        assertEquals(AndroidOfflineTtsStatus.VOICE_DATA_MISSING, readiness.status)
        assertTrue(platform.selections.isEmpty())
        assertIs<TtsSelection.Silent>(route(readiness))
    }

    @Test fun `later loss of offline data revokes a previous usable result`() {
        val platform = Platform(voice())
        assertTrue(AndroidOfflineTtsProbe.prepare(platform, locale).usableOffline)
        platform.selected = voice(installed = false)
        val fresh = AndroidOfflineTtsProbe.read(platform, locale)
        assertFalse(fresh.usableOffline)
        assertIs<TtsSelection.Silent>(route(fresh))
    }

    @Test fun `unsupported language cannot silently speak another language`() {
        val platform = Platform(voice(language = Locale.FRENCH), languageSupported = false)
        val readiness = AndroidOfflineTtsProbe.prepare(platform, locale)
        assertEquals(AndroidOfflineTtsStatus.LANGUAGE_UNSUPPORTED, readiness.status)
        assertIs<TtsSelection.Silent>(route(readiness))
    }

    @Test fun `missing selected voice and empty catalogue remain unavailable`() {
        val readiness = AndroidOfflineTtsProbe.prepare(Platform(null), locale)
        assertEquals(AndroidOfflineTtsStatus.VOICE_UNAVAILABLE, readiness.status)
        assertIs<TtsSelection.Silent>(route(readiness))
    }

    @Test fun `probe faults are explicit and keep the text fallback`() {
        val readiness = AndroidOfflineTtsProbe.prepare(Platform(voice(), failRead = true), locale)
        assertEquals(AndroidOfflineTtsStatus.PROBE_FAILED, readiness.status)
        assertIs<TtsSelection.Silent>(route(readiness))
    }

    @Test fun `setter success requires an independent selected voice readback`() {
        val remote = voice("remote", network = true)
        val platform = Platform(remote, listOf(voice()), honestReadback = false)
        val readiness = AndroidOfflineTtsProbe.prepare(platform, locale)
        assertEquals(listOf("offline"), platform.selections)
        assertEquals(AndroidOfflineTtsStatus.NETWORK_REQUIRED, readiness.status)
        assertIs<TtsSelection.Silent>(route(readiness))
    }

    @Test fun `failed offline selection never enables the remote default`() {
        val platform = Platform(voice("remote", network = true), listOf(voice()), acceptSelection = false)
        val readiness = AndroidOfflineTtsProbe.prepare(platform, locale)
        assertFalse(readiness.usableOffline)
        assertIs<TtsSelection.Silent>(route(readiness))
    }

    @Test fun `offline replacement selection is deterministic and respects locale`() {
        val alternatives = listOf(
            voice("higher-quality-foreign", language = Locale.US, quality = 500),
            voice("z", quality = 300),
            voice("a", quality = 300),
            voice("slower", quality = 300, latency = 400),
            voice("french", language = Locale.FRENCH, quality = 500),
        )
        for (catalogue in listOf(alternatives, alternatives.reversed())) {
            val platform = Platform(voice(network = true), catalogue)
            assertEquals("a", AndroidOfflineTtsProbe.prepare(platform, locale).voiceName)
        }
    }
}
