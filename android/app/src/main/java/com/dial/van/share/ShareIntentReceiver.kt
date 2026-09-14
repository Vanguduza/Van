package com.dial.van.share

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.net.Uri
import com.dial.van.VanApplication
import com.dial.van.queue.CommandKind
import com.dial.van.queue.CommandSensitivity
import com.dial.van.queue.QueueEnqueueRequest
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.util.UUID

/**
 * Share-to-Van ingress. Shared content is DATA not authority.
 * SECRET sensitivity suppresses enqueue entirely.
 */
class ShareIntentReceiver : BroadcastReceiver() {

    private val json = Json { encodeDefaults = true }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_SEND && intent.action != Intent.ACTION_SEND_MULTIPLE) return
        val app = context.applicationContext as VanApplication

        val sensitivity = classifySensitivity(intent)
        if (sensitivity == CommandSensitivity.SECRET) return

        val shareId = java.util.UUID.randomUUID().toString()
        val payload = when (intent.action) {
            Intent.ACTION_SEND -> buildSinglePayload(intent, shareId)
            Intent.ACTION_SEND_MULTIPLE -> buildMultiplePayload(intent, shareId)
            else -> return
        }

        app.commandQueue.enqueue(
            QueueEnqueueRequest(
                kind = CommandKind.CONTEXT_INGEST,
                payloadJson = json.encodeToString(payload),
                sensitivity = sensitivity,
                idempotencyKey = "share:$shareId",
            ),
        )

        val open = Intent(context, com.dial.van.command.CommandCentreActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
            putExtra("shared", true)
        }
        context.startActivity(open)
    }

    private fun buildSinglePayload(intent: Intent, shareId: String) = buildJsonObject {
        put("source", "share")
        put("share_id", shareId)
        put("mime", intent.type ?: "text/plain")
        put("untrusted_content", true)
        when {
            intent.type?.startsWith("text") == true -> {
                put("text", intent.getStringExtra(Intent.EXTRA_TEXT).orEmpty())
                intent.getStringExtra(Intent.EXTRA_SUBJECT)?.let { put("subject", it) }
            }
            intent.type?.startsWith("image") == true -> {
                val uri = intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM)
                put("uri", uri?.toString().orEmpty())
                put("kind", "image")
            }
            else -> {
                val uri = intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM)
                put("uri", uri?.toString().orEmpty())
                put("kind", "file")
            }
        }
    }

    private fun buildMultiplePayload(intent: Intent, shareId: String) = buildJsonObject {
        put("source", "share")
        put("share_id", shareId)
        put("mime", intent.type ?: "image/*")
        put("untrusted_content", true)
        val uris = intent.getParcelableArrayListExtra<Uri>(Intent.EXTRA_STREAM).orEmpty()
        put("uris", uris.joinToString(",") { it.toString() })
        put("count", uris.size)
    }

    private fun classifySensitivity(intent: Intent): CommandSensitivity {
        val text = buildString {
            append(intent.getStringExtra(Intent.EXTRA_TEXT).orEmpty())
            append(intent.getStringExtra(Intent.EXTRA_SUBJECT).orEmpty())
        }.lowercase()
        if (SECRET_MARKERS.any { text.contains(it) }) return CommandSensitivity.SECRET
        if (text.contains("password") || text.contains("private key")) return CommandSensitivity.SECRET
        return CommandSensitivity.NORMAL
    }

    companion object {
        private val SECRET_MARKERS = listOf("otp", "api key", "apikey", "bearer ", "token:", "secret:")
    }
}
