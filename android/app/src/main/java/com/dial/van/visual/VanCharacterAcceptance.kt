package com.dial.van.visual

import android.os.Build
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.lifecycleScope
import com.dial.van.gateway.VanGatewayClient
import com.dial.van.security.BiometricGate
import com.dial.van.security.OwnerApprovalKeyManager
import java.io.File
import java.io.InputStream
import java.security.MessageDigest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class VanCharacterAcceptance(
    private val activity: FragmentActivity,
    private val gateway: VanGatewayClient,
) {
    private val keys = OwnerApprovalKeyManager()
    private val biometric = BiometricGate(activity)

    fun accept(onStatus: (String) -> Unit) {
        val riveSha = runCatching {
            activity.assets.open(RiveBindingContract.ASSET_FILE).use(::sha256)
        }.getOrElse {
            onStatus("No production van.riv is installed. Character acceptance is blocked.")
            return
        }
        val apkSha = runCatching {
            File(activity.applicationInfo.sourceDir).inputStream().use(::sha256)
        }.getOrElse {
            onStatus("Could not hash this APK. Character acceptance is blocked.")
            return
        }
        val prepared = runCatching {
            keys.prepareOwnerAuthority(
                act = "visual-accept",
                subject = "sha256:$riveSha",
            )
        }.getOrElse {
            onStatus(it.message ?: "Owner authority key unavailable.")
            return
        }
        val signature = runCatching { keys.newSigningSignature() }.getOrElse {
            onStatus(it.message ?: "Owner signing key unavailable.")
            return
        }
        biometric.requestA4CommandApproval(
            signature = signature,
            challenge = prepared.canonical,
            title = "Accept VAN character",
            subtitle = "Bind your approval to this exact character asset",
            onApproved = { signatureBase64 ->
                val token = runCatching {
                    prepared.assembleFromSignatureBase64(signatureBase64)
                }.getOrElse {
                    onStatus(it.message ?: "Could not assemble owner acceptance.")
                    return@requestA4CommandApproval
                }
                onStatus("Recording signed character acceptance…")
                activity.lifecycleScope.launch {
                    runCatching {
                        withContext(Dispatchers.IO) {
                            gateway.recordVisualAcceptance(
                                token = token,
                                riveSha256 = riveSha,
                                apkSha256 = apkSha,
                                deviceModel = Build.MODEL,
                                androidBuild = Build.FINGERPRINT,
                            )
                        }
                    }.onSuccess {
                        onStatus("Owner acceptance recorded for ${riveSha.take(12)}…")
                    }.onFailure {
                        onStatus(it.message ?: "Gateway rejected character acceptance.")
                    }
                }
            },
            onDenied = { onStatus(it) },
        )
    }

    private fun sha256(stream: InputStream): String {
        val digest = MessageDigest.getInstance("SHA-256")
        val buffer = ByteArray(1024 * 128)
        while (true) {
            val read = stream.read(buffer)
            if (read <= 0) break
            digest.update(buffer, 0, read)
        }
        return digest.digest().joinToString("") { "%02x".format(it.toInt() and 0xff) }
    }
}
