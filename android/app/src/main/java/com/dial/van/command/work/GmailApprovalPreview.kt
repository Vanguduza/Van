package com.dial.van.command.work

import java.security.MessageDigest
import org.json.JSONObject

/** A fresh private preview must match the draft content sealed into this challenge. */
data class GmailApprovalPreview(
    val sender: String, val to: List<String>, val cc: List<String>, val bcc: List<String>,
    val subject: String, val body: String, val contentDigest: String,
) {
    companion object {
        fun parse(parameters: JSONObject, observed: JSONObject): GmailApprovalPreview? = runCatching {
            val digest = parameters.getString("draft_content_sha256")
            require(digest.matches(Regex("[0-9a-f]{64}")))
            require(parameters.getString("draft_id") == observed.getString("draft_id"))
            require(digest == observed.getString("draft_content_sha256"))
            require(observed.getBoolean("immutable_payload_send_supported"))
            val content = observed.getJSONObject("preview")
            val body = content.getString("body")
            require(body.toByteArray(Charsets.UTF_8).size <= 131_072)
            val hash = MessageDigest.getInstance("SHA-256").digest(body.toByteArray(Charsets.UTF_8))
                .joinToString("") { "%02x".format(it.toInt() and 0xff) }
            require(hash == observed.getString("body_sha256"))
            fun addresses(name: String): List<String> {
                val rows = content.getJSONArray(name)
                require(rows.length() <= 100)
                return (0 until rows.length()).map { rows.getString(it).also { address -> require(address.isNotBlank() && address.length <= 512) } }
            }
            GmailApprovalPreview(content.getString("from"), addresses("to"), addresses("cc"),
                addresses("bcc"), content.getString("subject"), body, digest)
        }.getOrNull()
    }
}
