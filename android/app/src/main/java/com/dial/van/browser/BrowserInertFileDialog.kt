package com.dial.van.browser

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.unit.dp
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject

/** Private file bytes rendered as text, raster pixels or PDF pixels; never a WebView or interpreter. */
@Composable
fun BrowserInertFileDialog(preview: BrowserPhoneActions.FilePreview, onDismiss: () -> Unit) {
    var text by remember(preview) { mutableStateOf<String?>(null) }
    var image by remember(preview) { mutableStateOf<Bitmap?>(null) }
    var error by remember(preview) { mutableStateOf<String?>(null) }
    var page by remember(preview) { mutableStateOf(0) }
    var pages by remember(preview) { mutableStateOf(0) }
    val kind = BrowserFileInspection.inertKind(preview.mime)
    LaunchedEffect(preview, page) {
        try {
            val rendered = withContext(Dispatchers.IO) {
                when (kind) {
                    "TEXT" -> {
                        val buffer = ByteArray(65536)
                        val count = preview.file.inputStream().use { input ->
                            var size = 0
                            while (size < buffer.size) { val read = input.read(buffer, size, buffer.size - size); if (read < 0) break; if (read > 0) size += read }
                            size
                        }
                        val decoded = Charsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPLACE)
                            .onUnmappableCharacter(CodingErrorAction.REPLACE).decode(ByteBuffer.wrap(buffer, 0, count)).toString()
                        Triple(decoded, null, 0)
                    }
                    "IMAGE" -> {
                        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                        BitmapFactory.decodeFile(preview.file.absolutePath, bounds)
                        require(bounds.outWidth in 1..32000 && bounds.outHeight in 1..32000) { "Unsupported image dimensions." }
                        var sample = 1
                        while (bounds.outWidth / sample > 2048 || bounds.outHeight / sample > 2048) sample *= 2
                        val bitmap = BitmapFactory.decodeFile(preview.file.absolutePath, BitmapFactory.Options().apply { inSampleSize = sample })
                            ?: error("The image could not be decoded safely.")
                        Triple(null, bitmap, 0)
                    }
                    "PDF" -> ParcelFileDescriptor.open(preview.file, ParcelFileDescriptor.MODE_READ_ONLY).use { fd ->
                        PdfRenderer(fd).use { pdf ->
                            require(pdf.pageCount in 1..2000) { "The PDF exceeds the viewer's page limit." }
                            pdf.openPage(page.coerceIn(0, pdf.pageCount - 1)).use { sheet ->
                                require(sheet.width > 0 && sheet.height > 0)
                                val scale = minOf(1.0, 1536.0 / maxOf(sheet.width, sheet.height))
                                val bitmap = Bitmap.createBitmap(maxOf(1, (sheet.width * scale).toInt()), maxOf(1, (sheet.height * scale).toInt()), Bitmap.Config.ARGB_8888)
                                bitmap.eraseColor(android.graphics.Color.WHITE)
                                sheet.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                                Triple(null, bitmap, pdf.pageCount)
                            }
                        }
                    }
                    else -> error("This type has no inert VAN viewer.")
                }
            }
            text = rendered.first; image = rendered.second; pages = rendered.third; error = null
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (failure: Exception) { error = failure.message ?: "The verified file could not be rendered." }
    }
    DisposableEffect(image) { val held = image; onDispose { held?.recycle() } }
    AlertDialog(onDismissRequest = onDismiss, title = { Text(preview.name) }, text = {
        Column(Modifier.heightIn(max = 480.dp).verticalScroll(rememberScrollState())) {
            Text("Verified file bytes · untrusted content · no execution or external links")
            error?.let { Text(it) }
            text?.let { Text(it); if (preview.file.length() > 65536) Text("Preview limited to the first 65,536 bytes.") }
            image?.let { Image(it.asImageBitmap(), contentDescription = "File preview", modifier = Modifier.fillMaxWidth()) }
            if (pages > 0) {
                Text("Page ${page + 1} of $pages")
                OutlinedButton(enabled = page > 0, onClick = { page-- }) { Text("Previous page") }
                OutlinedButton(enabled = page + 1 < pages, onClick = { page++ }) { Text("Next page") }
            }
        }
    }, confirmButton = { TextButton(onClick = onDismiss) { Text("Close and discard local preview") } })
}

@Composable
fun BrowserInspectionDialog(result: JSONObject, onDismiss: () -> Unit) {
    AlertDialog(onDismissRequest = onDismiss, title = { Text("Static file inspection") }, text = {
        Column(Modifier.heightIn(max = 480.dp).verticalScroll(rememberScrollState())) {
            Text("Untrusted file evidence. The native host inspected bounded bytes; it did not execute their contents or grant action authority.")
            Text("File ${result.optString("download_id")} · ${result.optLong("byte_size")} bytes\nContent hash ${result.optString("content_sha256")}\nInspection hash ${result.optString("analysis_sha256")}")
            Text("Observed MIME: ${result.optString("observed_mime")}")
            if (result.optBoolean("truncated")) Text("The static inspection preview was truncated.")
            if (!result.isNull("text_preview")) Text(result.optString("text_preview"))
            else Text("No text preview is retained in this receipt.")
        }
    }, confirmButton = { TextButton(onClick = onDismiss) { Text("Close") } })
}
