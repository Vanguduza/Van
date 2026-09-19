package com.dial.van.share

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.widget.Toast
import com.dial.van.VanApplication
import com.dial.van.queue.CommandKind
import com.dial.van.queue.CommandSensitivity
import com.dial.van.queue.QueueEnqueueRequest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.util.UUID

/**
 * Share-to-VAN ingress.
 *
 * P1-AND-001 — this was a `BroadcastReceiver` with an `ACTION_SEND` intent filter. The
 * Android share sheet resolves *activities*; a receiver declaring those filters never
 * appears in it and can only be reached by an explicit broadcast, which nothing sent. The
 * whole share path was unreachable and had been since it was written, and because a receiver
 * is a legitimate component with a legitimate filter, nothing failed: VAN simply was not in
 * the share sheet and no code said why.
 *
 * Transparent and finishing: this is a component the owner passes through, not a screen.
 * `Theme.Van.Transparent` has no window background and no animation, so the owner's share
 * sheet dismisses straight back to the app they were in.
 *
 * Shared content is DATA, never authority: it is queued as `CONTEXT_INGEST` with
 * `untrusted_content` set, and a share that looks like it carries a credential is dropped
 * rather than queued. [ShareIntake] holds both rules and is executed in
 * `android/verification`.
 */
class ShareIntakeActivity : Activity() {

    private val json = Json { encodeDefaults = true }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val acknowledgement = intake(intent)
        // Said out loud, always. A share that vanishes silently is indistinguishable from
        // the defect this replaces — and the SECRET case especially must be visible, or the
        // owner assumes VAN has their password when it deliberately does not.
        Toast.makeText(this, acknowledgement, Toast.LENGTH_LONG).show()
        finish()
        overridePendingTransition(0, 0)
    }

    private fun intake(intent: Intent?): String {
        if (intent == null) return NOTHING_SHARED
        if (intent.action != Intent.ACTION_SEND && intent.action != Intent.ACTION_SEND_MULTIPLE) {
            return NOTHING_SHARED
        }

        val text = intent.getStringExtra(Intent.EXTRA_TEXT)
        val subject = intent.getStringExtra(Intent.EXTRA_SUBJECT)
        val uris = streamUris(intent).map(Uri::toString)
        val payload = ShareIntake.payload(intent.type, text, subject, uris)
        val sensitivity = ShareIntake.classify(text, subject)
        val acknowledgement = ShareIntake.acknowledgement(payload, sensitivity)

        if (sensitivity == ShareSensitivity.SECRET) return acknowledgement

        val app = application as? VanApplication ?: return UNAVAILABLE
        val shareId = UUID.randomUUID().toString()
        app.commandQueue.enqueue(
            QueueEnqueueRequest(
                kind = CommandKind.CONTEXT_INGEST,
                payloadJson = json.encodeToString(
                    kotlinx.serialization.json.JsonObject.serializer(),
                    buildJsonObject {
                        put("source", "share")
                        put("share_id", shareId)
                        put("mime", payload.mime)
                        put("kind", payload.kind.name.lowercase())
                        // Not a parameter anywhere: whatever app the owner shared from
                        // authored this, which is to say anyone did.
                        put("untrusted_content", true)
                        payload.text?.let { put("text", it) }
                        payload.subject?.let { put("subject", it) }
                        if (payload.uris.isNotEmpty()) {
                            put("uris", JsonArray(payload.uris.map(::JsonPrimitive)))
                            put("count", payload.uris.size)
                        }
                    },
                ),
                sensitivity = CommandSensitivity.NORMAL,
                idempotencyKey = "share:$shareId",
            ),
        )
        return acknowledgement
    }

    @Suppress("DEPRECATION")
    private fun streamUris(intent: Intent): List<Uri> =
        if (intent.action == Intent.ACTION_SEND_MULTIPLE) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM, Uri::class.java)
            } else {
                intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM)
            }.orEmpty()
        } else {
            val single = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                intent.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java)
            } else {
                intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM)
            }
            listOfNotNull(single)
        }

    private companion object {
        const val NOTHING_SHARED = "There was nothing in that to keep."
        const val UNAVAILABLE = "VAN could not store that just now. Try sharing it again."
    }
}
