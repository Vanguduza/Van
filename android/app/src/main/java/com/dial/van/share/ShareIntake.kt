package com.dial.van.share

/**
 * What a shared thing becomes when the owner sends it to VAN.
 *
 * P1-AND-001's companion. The receiver's classification and payload shaping were written
 * against `android.content.Intent`, which meant the one security-relevant rule on this path
 * — that a share carrying a secret is dropped rather than queued — could not be tested
 * without an Android runtime. It is the rule most worth testing: the owner sharing a
 * password reset email to VAN must not put that password in VAN's queue.
 *
 * Pure Kotlin. The Activity reads the Intent; this decides what it means.
 */
enum class ShareSensitivity {
    /** Ordinary shared content. Queued as untrusted context. */
    NORMAL,

    /** Carries credential material. Dropped, never queued, never sent. */
    SECRET,
}

enum class ShareKind { TEXT, IMAGE, FILE, MULTIPLE }

data class SharePayload(
    val kind: ShareKind,
    val mime: String,
    val text: String?,
    val subject: String?,
    val uris: List<String>,
)

object ShareIntake {

    /**
     * Markers that mean the shared text contains a credential.
     *
     * Deliberately crude and deliberately over-eager: dropping a share that was not really
     * a secret costs the owner one re-share, and queuing one that was costs them a
     * credential sitting in an encrypted queue and then crossing the network.
     */
    val SECRET_MARKERS = listOf(
        "otp", "api key", "apikey", "bearer ", "token:", "secret:",
        "password", "passcode", "private key", "verification code", "one-time code",
        "security code", "2fa code", "recovery code",
    )

    fun classify(text: String?, subject: String?): ShareSensitivity {
        val blob = "${text.orEmpty()} ${subject.orEmpty()}".lowercase()
        return if (SECRET_MARKERS.any { blob.contains(it) }) {
            ShareSensitivity.SECRET
        } else {
            ShareSensitivity.NORMAL
        }
    }

    fun kindFor(mime: String?, uriCount: Int): ShareKind = when {
        uriCount > 1 -> ShareKind.MULTIPLE
        mime?.startsWith("image") == true -> ShareKind.IMAGE
        mime?.startsWith("text") == true -> ShareKind.TEXT
        uriCount == 1 -> ShareKind.FILE
        else -> ShareKind.TEXT
    }

    /**
     * The payload VAN queues.
     *
     * `untrusted_content` is always true and is not a parameter. Shared content is authored
     * by whatever app the owner shared from, which is to say by anyone; the one thing this
     * payload must never be able to say is that it is trusted.
     */
    fun payload(
        mime: String?,
        text: String?,
        subject: String?,
        uris: List<String> = emptyList(),
    ): SharePayload = SharePayload(
        kind = kindFor(mime, uris.size),
        mime = mime ?: "text/plain",
        text = text?.takeIf { it.isNotBlank() },
        subject = subject?.takeIf { it.isNotBlank() },
        uris = uris.filter { it.isNotBlank() },
    )

    /** One line the owner sees after sharing, so the share is not silent. */
    fun acknowledgement(payload: SharePayload, sensitivity: ShareSensitivity): String =
        when {
            sensitivity == ShareSensitivity.SECRET ->
                "That looked like it contained a password or a code, so I have not kept it."
            payload.kind == ShareKind.MULTIPLE -> "Kept ${payload.uris.size} items to work from."
            payload.kind == ShareKind.IMAGE -> "Kept the image to work from."
            payload.kind == ShareKind.FILE -> "Kept the file to work from."
            payload.subject != null -> "Kept \"${payload.subject}\" to work from."
            else -> "Kept what you shared to work from."
        }
}
