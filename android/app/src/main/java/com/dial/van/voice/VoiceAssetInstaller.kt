package com.dial.van.voice

import android.content.Context
import android.os.Looper
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/** No remote URL, new signing identity, or private-storage ADB access is needed. */
object VoiceAssetInstaller {
    data class Installed(val root: File, val bundle: VoiceAssetBundle)
    @Volatile private var installed: Installed? = null
    @Volatile var failure: String? = null
        private set

    fun installedOrNull(): Installed? = installed

    fun ensureInstalled(context: Context): Installed? {
        installed?.let { return it }
        if (Looper.myLooper() == Looper.getMainLooper()) return null
        return installOnIo(context)
    }

    suspend fun prepare(context: Context): Installed? = withContext(Dispatchers.IO) {
        installOnIo(context)
    }

    @Synchronized
    private fun installOnIo(context: Context): Installed? {
        installed?.let { return it }
        return runCatching {
            val app = context.applicationContext
            val manifest = app.assets.open("voice/voice_asset_manifest.json").use {
                EmbeddedVoiceAssetInstaller.readManifest(it)
            }
            val bundle = EmbeddedVoiceAssetInstaller.admit(manifest, VoiceBundlePin.SHA256)
            val root = EmbeddedVoiceAssetInstaller.install(
                File(app.filesDir, "voice/embedded"), bundle, VoiceBundlePin.SHA256,
            ) { path -> app.assets.open("voice/bundle/$path") }
            Installed(root, bundle).also { installed = it; failure = null }
        }.getOrElse {
            failure = it.message ?: "voice_bundle_unavailable"
            null
        }
    }
}
