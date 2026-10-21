package com.dial.van.voice

import java.util.Locale

/** Platform evidence about a voice, rather than an assumption that Android has one. */
data class AndroidTtsVoiceEvidence(
    val name: String,
    val locale: Locale,
    val networkRequired: Boolean,
    val dataInstalled: Boolean,
    val quality: Int = 0,
    val latency: Int = 0,
)

enum class AndroidOfflineTtsStatus {
    INITIALIZING, INITIALIZATION_FAILED, LANGUAGE_UNSUPPORTED, VOICE_UNAVAILABLE,
    NETWORK_REQUIRED, VOICE_DATA_MISSING, PROBE_FAILED, SHUT_DOWN, READY,
}

data class AndroidOfflineTtsReadiness(
    val status: AndroidOfflineTtsStatus,
    val initialized: Boolean = false,
    val voiceName: String? = null,
) {
    val usableOffline: Boolean get() = status == AndroidOfflineTtsStatus.READY

    fun engineReadiness() = TtsEngineReadiness(
        TtsEngineKind.ANDROID_OFFLINE,
        installed = initialized,
        offlineDataVerified = usableOffline,
    )
}

/** Narrow adapter so the actual selection/probe can also be exercised without Android. */
interface AndroidTtsVoicePlatform {
    fun setLanguage(locale: Locale): Boolean
    fun selectedVoice(): AndroidTtsVoiceEvidence?
    fun voices(): List<AndroidTtsVoiceEvidence>
    fun selectVoice(name: String): Boolean
}

object AndroidOfflineTtsProbe {
    fun initialize(
        succeeded: Boolean,
        platform: AndroidTtsVoicePlatform,
        locale: Locale,
    ): AndroidOfflineTtsReadiness = if (succeeded) {
        prepare(platform, locale)
    } else {
        AndroidOfflineTtsReadiness(AndroidOfflineTtsStatus.INITIALIZATION_FAILED)
    }

    fun prepare(platform: AndroidTtsVoicePlatform, locale: Locale): AndroidOfflineTtsReadiness =
        safely {
            if (!platform.setLanguage(locale)) {
                AndroidOfflineTtsReadiness(AndroidOfflineTtsStatus.LANGUAGE_UNSUPPORTED, true)
            } else {
                read(platform, locale)
            }
        }

    /** Re-read the selected voice/data on every use; an OS update can invalidate them. */
    fun read(platform: AndroidTtsVoicePlatform, locale: Locale): AndroidOfflineTtsReadiness =
        safely {
            val selected = platform.selectedVoice()
            val current = inspect(selected, locale)
            if (current.usableOffline) return@safely current

            val replacement = platform.voices()
                .filter { matchesLanguage(it, locale) && !it.networkRequired && it.dataInstalled }
                .sortedWith(
                    compareByDescending<AndroidTtsVoiceEvidence> { it.locale == locale }
                        .thenByDescending { locale.country.isNotEmpty() && it.locale.country == locale.country }
                        .thenByDescending { it.quality }
                        .thenBy { it.latency }
                        .thenBy { it.name },
                ).firstOrNull()
            if (replacement == null || !platform.selectVoice(replacement.name)) {
                current
            } else {
                // A successful setter alone is insufficient: verify the actual readback.
                inspect(platform.selectedVoice(), locale)
            }
        }

    private fun inspect(voice: AndroidTtsVoiceEvidence?, locale: Locale): AndroidOfflineTtsReadiness {
        val status = when {
            voice == null -> AndroidOfflineTtsStatus.VOICE_UNAVAILABLE
            !matchesLanguage(voice, locale) -> AndroidOfflineTtsStatus.LANGUAGE_UNSUPPORTED
            voice.networkRequired -> AndroidOfflineTtsStatus.NETWORK_REQUIRED
            !voice.dataInstalled -> AndroidOfflineTtsStatus.VOICE_DATA_MISSING
            else -> AndroidOfflineTtsStatus.READY
        }
        return AndroidOfflineTtsReadiness(status, initialized = true, voiceName = voice?.name)
    }

    private fun matchesLanguage(voice: AndroidTtsVoiceEvidence, locale: Locale): Boolean =
        locale.language.isNotEmpty() && voice.locale.language == locale.language

    private inline fun safely(probe: () -> AndroidOfflineTtsReadiness): AndroidOfflineTtsReadiness =
        try {
            probe()
        } catch (_: Exception) {
            AndroidOfflineTtsReadiness(AndroidOfflineTtsStatus.PROBE_FAILED, initialized = true)
        }
}
