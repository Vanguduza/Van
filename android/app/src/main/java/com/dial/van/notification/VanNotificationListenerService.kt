package com.dial.van.notification

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import com.dial.van.VanApplication
import com.dial.van.queue.CommandKind
import com.dial.van.queue.CommandSensitivity
import com.dial.van.queue.QueueEnqueueRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.security.MessageDigest

class VanNotificationListenerService : NotificationListenerService() {

    private val json = Json { encodeDefaults = true }

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        if (sbn == null) return
        val app = application as VanApplication
        val policyStore = app.notificationPolicyStore
        val packageName = sbn.packageName

        when (policyStore.policyFor(packageName)) {
            AppNotificationPolicy.MUTE -> return
            AppNotificationPolicy.NORMAL,
            AppNotificationPolicy.PRIORITY,
            -> Unit
        }

        if (policyStore.isQuietNow() && policyStore.policyFor(packageName) != AppNotificationPolicy.PRIORITY) {
            return
        }

        val extras = sbn.notification.extras
        val title = extras.getCharSequence("android.title")?.toString().orEmpty()
        val body = extras.getCharSequence("android.text")?.toString().orEmpty()
        val combined = "$title\n$body"
        val redacted = SecretRedactor.redact(combined)
        val hash = sha256("$packageName|$redacted")

        if (policyStore.shouldSuppressDuplicate(hash)) return

        val payload = buildJsonObject {
            put("source", "notification")
            put("package", packageName)
            put("title", SecretRedactor.redact(title))
            put("body", redacted)
            put("posted_at", sbn.postTime)
            put("priority", policyStore.policyFor(packageName).name)
            put("untrusted_content", true)
        }

        // Off the service's main thread, for the reason given in `ShareIntakeActivity`:
        // the queue's write is synchronous since the outbox needed it to be, and
        // `onNotificationPosted` is called on the main thread. A phone that receives a
        // burst of notifications would otherwise do one encrypted disk write per
        // notification, in a row, on the thread that draws.
        app.appScope.launch(Dispatchers.IO) {
            app.commandQueue.enqueue(
                QueueEnqueueRequest(
                    kind = CommandKind.CONTEXT_INGEST,
                    payloadJson = json.encodeToString(payload),
                    sensitivity = CommandSensitivity.NORMAL,
                    idempotencyKey = "notif:$hash",
                ),
            )
        }
    }

    private fun sha256(input: String): String {
        val digest = MessageDigest.getInstance("SHA-256")
        return digest.digest(input.toByteArray()).joinToString("") { "%02x".format(it) }
    }
}
