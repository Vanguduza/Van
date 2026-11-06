package com.dial.van.voice

import java.io.File
import java.io.InputStream
import java.io.ByteArrayOutputStream
import java.security.MessageDigest
import java.util.UUID

/** Installs only bytes named by the immutable manifest shipped in the application's APK. */
object EmbeddedVoiceAssetInstaller {
    fun readManifest(input: InputStream): ByteArray {
        val output = ByteArrayOutputStream()
        val buffer = ByteArray(4096)
        while (true) {
            val count = input.read(buffer)
            if (count < 0) break
            if (count == 0) continue
            require(output.size() + count <= 256 * 1024) { "voice_manifest_size_invalid" }
            output.write(buffer, 0, count)
        }
        return output.toByteArray()
    }

    fun sha256(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    fun admit(manifest: ByteArray, expectedSha256: String): VoiceAssetBundle {
        require(expectedSha256.matches(Regex("[0-9a-f]{64}"))) { "voice_bundle_pin_unbound" }
        require(manifest.size in 1..256 * 1024) { "voice_manifest_size_invalid" }
        require(sha256(manifest) == expectedSha256) { "voice_manifest_pin_mismatch" }
        return (VoiceAssetManifest.parse(manifest.toString(Charsets.UTF_8)) as? VoiceManifestVerdict.Accepted)
            ?.bundle ?: error("voice_manifest_refused")
    }

    fun install(
        parent: File,
        bundle: VoiceAssetBundle,
        manifestSha256: String,
        readAsset: (String) -> InputStream,
    ): File {
        require(manifestSha256.matches(Regex("[0-9a-f]{64}")))
        require(bundle.entries.isNotEmpty()) { "voice_bundle_empty" }
        require(parent.mkdirs() || parent.isDirectory) { "voice_bundle_directory_unavailable" }
        val target = File(parent, manifestSha256)
        if (verified(target, bundle)) return target
        // A failed copy never publishes a partly installed acoustic model.
        val staging = File(parent, ".install-${UUID.randomUUID()}")
        check(staging.mkdir()) { "voice_bundle_staging_unavailable" }
        try {
            for (entry in bundle.entries) {
                val file = confined(staging, entry.path)
                check(file.parentFile!!.mkdirs() || file.parentFile!!.isDirectory)
                val digest = MessageDigest.getInstance("SHA-256")
                var size = 0L
                readAsset(entry.path).use { input ->
                    file.outputStream().use { output ->
                        val buffer = ByteArray(64 * 1024)
                        while (true) {
                            val count = input.read(buffer)
                            if (count < 0) break
                            if (count == 0) continue
                            size += count
                            check(size <= entry.sizeBytes) { "voice_asset_size_exceeded" }
                            digest.update(buffer, 0, count)
                            output.write(buffer, 0, count)
                        }
                        output.fd.sync()
                    }
                }
                check(size == entry.sizeBytes && hex(digest.digest()) == entry.sha256) {
                    "voice_asset_integrity_failed"
                }
            }
            check(verified(staging, bundle)) { "voice_bundle_verification_failed" }
            if (target.exists()) check(target.deleteRecursively()) { "voice_bundle_repair_refused" }
            check(staging.renameTo(target)) { "voice_bundle_publish_failed" }
            return target
        } finally {
            staging.deleteRecursively()
        }
    }

    fun verified(root: File, bundle: VoiceAssetBundle): Boolean = runCatching {
        root.isDirectory && bundle.entries.all { entry ->
            val file = confined(root, entry.path)
            file.isFile && file.length() == entry.sizeBytes &&
                file.inputStream().use { input ->
                    val digest = MessageDigest.getInstance("SHA-256")
                    val buffer = ByteArray(64 * 1024)
                    while (true) {
                        val count = input.read(buffer)
                        if (count < 0) break
                        if (count > 0) digest.update(buffer, 0, count)
                    }
                    hex(digest.digest()) == entry.sha256
                }
        }
    }.getOrDefault(false)

    fun confined(root: File, path: String): File {
        require(VoiceAssetManifest.safeRelativePath(path)) { "voice_asset_path_invalid" }
        val canonicalRoot = root.canonicalFile
        val file = File(canonicalRoot, path).canonicalFile
        require(file.path.startsWith(canonicalRoot.path + File.separator)) { "voice_asset_path_escape" }
        return file
    }

    private fun hex(bytes: ByteArray): String = bytes.joinToString("") { "%02x".format(it) }
}
