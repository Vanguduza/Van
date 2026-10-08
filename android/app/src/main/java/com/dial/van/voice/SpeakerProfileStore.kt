package com.dial.van.voice

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import org.json.JSONObject

/** The sole persistent owner-embedding source. Authentication failure has no plaintext fallback. */
class SpeakerProfileStore(context: Context) {
    private val preferences = EncryptedSharedPreferences.create(
        context.applicationContext, "van-owner-speaker-profile",
        MasterKey.Builder(context.applicationContext).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )
    data class Record(val json: JSONObject, val revision: String)

    @Synchronized fun read(): Record? {
        val text = preferences.getString("profile", null) ?: return null
        require(text.length <= 128 * 1024) { "speaker_profile_size_invalid" }
        return Record(JSONObject(text), EmbeddedVoiceAssetInstaller.sha256(text.toByteArray(Charsets.UTF_8)))
    }

    @Synchronized fun write(profile: JSONObject, expectedRevision: String?) {
        check(read()?.revision == expectedRevision) { "speaker_profile_changed" }
        val text = profile.toString()
        require(text.length <= 128 * 1024) { "speaker_profile_size_invalid" }
        check(preferences.edit().putString("profile", text).commit()) { "speaker_profile_commit_failed" }
        check(preferences.getString("profile", null) == text) { "speaker_profile_readback_failed" }
    }

    @Synchronized fun remove(expectedRevision: String) {
        check(read()?.revision == expectedRevision) { "speaker_profile_changed" }
        check(preferences.edit().remove("profile").commit()) { "speaker_profile_remove_failed" }
        check(!preferences.contains("profile")) { "speaker_profile_remove_readback_failed" }
    }
}
