package com.dial.van.browser

import com.dial.van.gateway.VanGatewayClient
import java.io.ByteArrayOutputStream
import java.io.File
import java.net.URL
import javax.net.ssl.HttpsURLConnection
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject

/** File bytes travel directly to the admitted producer, never through the assistant or gateway. */
class BrowserTransferClient(private val gateway: VanGatewayClient) {
    private fun connection(grant: BrowserTransfers.Grant, method: String): HttpsURLConnection {
        require(System.currentTimeMillis() < grant.expiresAtMs) { "browser_transfer_grant_expired" }
        val url = gateway.admitBrowserTransferUrl(grant.hostUrl)
        return (URL(url).openConnection() as HttpsURLConnection).apply {
            instanceFollowRedirects = false
            connectTimeout = 20_000
            readTimeout = 60_000
            requestMethod = method
            gateway.browserSignalTransport(url)?.let { sslSocketFactory = it }
            setRequestProperty("Authorization", "Bearer ${grant.token}")
            setRequestProperty("X-Van-Producer-Session", grant.context.mediaEpoch)
        }
    }
    private fun response(connection: HttpsURLConnection): JSONObject {
        require(connection.responseCode in 200..299) { "browser_transfer_http_${connection.responseCode}" }
        val output = ByteArrayOutputStream()
        connection.inputStream.use { BrowserTransfers.copy(it, output, 524_288) }
        return JSONObject(output.toString(Charsets.UTF_8.name()))
    }
    suspend fun download(grant: BrowserTransfers.Grant, temporary: File) = withContext(Dispatchers.IO) {
        require(grant.operation == BrowserTransfers.Operation.DOWNLOAD)
        val connection = connection(grant, "GET")
        try {
            require(connection.responseCode in 200..299) { "browser_transfer_http_${connection.responseCode}" }
            val proof = BrowserTransfers.Bytes(grant.byteSize ?: error("browser_download_size_missing"),
                grant.contentSha256 ?: error("browser_download_hash_missing"))
            connection.inputStream.use { input -> temporary.outputStream().use { output ->
                BrowserTransfers.copy(input, output, BrowserTransfers.MAX_FILE_BYTES, proof)
            } }
        } finally { connection.disconnect() }
    }
    suspend fun upload(grant: BrowserTransfers.Grant, temporary: File): JSONObject = withContext(Dispatchers.IO) {
        require(grant.operation == BrowserTransfers.Operation.UPLOAD && temporary.length() == grant.byteSize)
        val connection = connection(grant, "POST")
        try {
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/octet-stream")
            connection.setRequestProperty("X-Van-Content-SHA256", grant.contentSha256)
            connection.setFixedLengthStreamingMode(temporary.length())
            temporary.inputStream().use { input -> connection.outputStream.use { output ->
                BrowserTransfers.copy(input, output, BrowserTransfers.MAX_FILE_BYTES,
                    BrowserTransfers.Bytes(grant.byteSize!!, grant.contentSha256!!))
            } }
            response(connection).also { BrowserTransfers.verifyEffect(it, grant) }
        } finally { connection.disconnect() }
    }
    suspend fun importFile(grant: BrowserTransfers.Grant, temporary: File): JSONObject = withContext(Dispatchers.IO) {
        require(grant.operation == BrowserTransfers.Operation.FILE_IMPORT && temporary.length() == grant.byteSize)
        val connection = connection(grant, "POST")
        try {
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/octet-stream")
            connection.setRequestProperty("X-Van-Content-SHA256", grant.contentSha256)
            connection.setFixedLengthStreamingMode(temporary.length())
            temporary.inputStream().use { input -> connection.outputStream.use { output ->
                BrowserTransfers.copy(input, output, BrowserTransfers.MAX_FILE_BYTES,
                    BrowserTransfers.Bytes(grant.byteSize!!, grant.contentSha256!!))
            } }
            response(connection).also { BrowserFileInspection.validateImport(it, grant) }
        } finally { connection.disconnect() }
    }
    suspend fun analyse(grant: BrowserTransfers.Grant): JSONObject = withContext(Dispatchers.IO) {
        require(grant.operation == BrowserTransfers.Operation.ANALYSE)
        val connection = connection(grant, "POST")
        try {
            connection.doOutput = true
            connection.setFixedLengthStreamingMode(0)
            connection.outputStream.use { }
            response(connection).also { BrowserFileInspection.validateNative(it, grant) }
        } finally { connection.disconnect() }
    }
    suspend fun clipboard(grant: BrowserTransfers.Grant, text: String? = null): String? = withContext(Dispatchers.IO) {
        require(grant.operation in setOf(BrowserTransfers.Operation.COPY, BrowserTransfers.Operation.PASTE))
        val body = JSONObject().put("target_id", grant.context.targetId)
        if (grant.operation == BrowserTransfers.Operation.PASTE) {
            val actual = BrowserTransfers.textProof(text ?: error("browser_clipboard_text_required"))
            require(actual.size == grant.byteSize && actual.sha256 == grant.contentSha256)
            body.put("text", text)
        }
        val connection = connection(grant, "POST")
        try {
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json")
            val bytes = body.toString().toByteArray(Charsets.UTF_8)
            connection.setFixedLengthStreamingMode(bytes.size)
            connection.outputStream.use { it.write(bytes) }
            val response = response(connection)
            if (grant.operation == BrowserTransfers.Operation.PASTE) {
                BrowserTransfers.verifyEffect(response, grant)
                null
            } else {
                require(response.optString("producer_session_id") == grant.context.mediaEpoch &&
                    response.optString("target_id") == grant.context.targetId) { "browser_clipboard_copy_binding_mismatch" }
                response.getString("text").also { BrowserTransfers.textProof(it) }
            }
        } finally { connection.disconnect() }
    }
}
