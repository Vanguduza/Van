package com.dial.van.command.work

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.FileProvider
import com.dial.van.VanApplication
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.VanPanel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

private data class RenderedPdf(
    val bitmap: Bitmap,
    val pageIndex: Int,
    val pageCount: Int,
)


@Composable
fun DocumentRoute(
    app: VanApplication,
    documentId: String,
    onBack: () -> Unit,
) {
    val tokens = LocalVanTokens.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val textValues = remember(documentId) { mutableStateMapOf<String, String>() }
    val boolValues = remember(documentId) { mutableStateMapOf<String, Boolean>() }
    var document by remember(documentId) { mutableStateOf<JSONObject?>(null) }
    var preview by remember(documentId) { mutableStateOf<RenderedPdf?>(null) }
    var pageIndex by remember(documentId) { mutableStateOf(0) }
    var zoom by remember(documentId) { mutableStateOf(1f) }
    var loading by remember(documentId) { mutableStateOf(true) }
    var notice by remember(documentId) { mutableStateOf<String?>(null) }

    fun refresh() {
        scope.launch {
            loading = true
            runCatching { app.gatewayClient.convergenceDocument(documentId) }
                .onSuccess { doc ->
                    document = doc
                    val fields = doc.optJSONArray("fields")
                    jsonObjects(fields ?: JSONArray()).forEach { field ->
                        val name = field.optString("name")
                        when (field.optString("kind")) {
                            "CHECKBOX" -> boolValues.putIfAbsent(name, field.optBoolean("value", false))
                            else -> textValues.putIfAbsent(name, field.optString("value", ""))
                        }
                    }
                    val variant = if (doc.optString("output_artifact_id").isNotBlank()) "output" else "source"
                    runCatching {
                        val bytes = app.gatewayClient.convergenceDocumentContent(documentId, variant)
                        renderPdfPage(context, documentId, bytes, pageIndex, zoom)
                    }.onSuccess { preview = it }
                        .onFailure { notice = it.message ?: "Preview unavailable" }
                    loading = false
                }
                .onFailure {
                    notice = it.message ?: "Document unavailable"
                    loading = false
                }
        }
    }

    LaunchedEffect(documentId, pageIndex, zoom) { refresh() }

    Column(
        modifier = Modifier.fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = tokens.space.pageGutter, vertical = tokens.space.space3),
        verticalArrangement = Arrangement.spacedBy(tokens.space.space3),
    ) {
        Button(onClick = onBack) { Text("← Documents") }
        SectionHeader(
            document?.optString("filename", "Document") ?: "Document",
            detail = if (loading) "Loading…" else "Source preserved; fills create a new copy",
        )
        notice?.let { Text(it, style = tokens.type.label, color = tokens.color.forStatusRole(StatusSemantics.ROLE_EVENT_RISK)) }

        preview?.let { rendered ->
            VanPanel {
                Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                    Image(
                        bitmap = rendered.bitmap.asImageBitmap(),
                        contentDescription = "PDF page ${rendered.pageIndex + 1} of ${rendered.pageCount}",
                        modifier = Modifier.fillMaxWidth().heightIn(max = tokens.space.pageGutter * 40),
                        contentScale = ContentScale.Fit,
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                        OutlinedButton(
                            enabled = rendered.pageIndex > 0,
                            onClick = { pageIndex = (pageIndex - 1).coerceAtLeast(0) },
                        ) { Text("Previous") }
                        Text("${rendered.pageIndex + 1}/${rendered.pageCount}", style = tokens.type.label)
                        OutlinedButton(
                            enabled = rendered.pageIndex + 1 < rendered.pageCount,
                            onClick = { pageIndex += 1 },
                        ) { Text("Next") }
                        OutlinedButton(onClick = { zoom = (zoom - 0.25f).coerceAtLeast(0.75f) }) { Text("−") }
                        OutlinedButton(onClick = { zoom = (zoom + 0.25f).coerceAtMost(2f) }) { Text("+") }
                    }
                }
            }
        }

        val shareVariant = if (document?.optString("output_artifact_id").orEmpty().isNotBlank()) "output" else "source"
        OutlinedButton(
            enabled = document != null && !loading,
            onClick = {
                val filename = document?.optString("filename", "document.pdf") ?: "document.pdf"
                scope.launch {
                    runCatching {
                        val bytes = app.gatewayClient.convergenceDocumentContent(documentId, shareVariant)
                        stageAndSharePdf(context, documentId, filename, bytes)
                    }.onFailure { notice = it.message ?: "Unable to share document" }
                }
            },
        ) { Text("Share copy") }

        val fields = jsonObjects(document?.optJSONArray("fields") ?: JSONArray())
        if (fields.isNotEmpty()) {
            SectionHeader("Form fields", detail = "Review values before creating a filled copy")
            fields.forEach { field ->
                val name = field.optString("name")
                when (field.optString("kind")) {
                    "CHECKBOX" -> VanPanel(dense = true) {
                        Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                            Checkbox(
                                checked = boolValues[name] ?: false,
                                onCheckedChange = { boolValues[name] = it },
                            )
                            Text(name, style = tokens.type.body, color = tokens.color.textPrimary)
                        }
                    }
                    else -> OutlinedTextField(
                        value = textValues[name] ?: "",
                        onValueChange = { textValues[name] = it },
                        label = { Text(name) },
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
            Button(
                enabled = !loading,
                onClick = {
                    scope.launch {
                        loading = true
                        val values = JSONObject()
                        fields.forEach { field ->
                            val name = field.optString("name")
                            if (field.optString("kind") == "CHECKBOX") {
                                values.put(name, boolValues[name] ?: false)
                            } else {
                                values.put(name, textValues[name] ?: "")
                            }
                        }
                        runCatching {
                            app.gatewayClient.convergenceFillDocument(documentId, values)
                        }.onSuccess {
                            pageIndex = 0
                            notice = "Filled copy created and digest-verified."
                            refresh()
                        }.onFailure {
                            notice = it.message ?: "Unable to fill document"
                            loading = false
                        }
                    }
                },
            ) { Text("Create filled copy") }
        } else if (!loading) {
            Text("This PDF has no supported fillable fields.", style = tokens.type.body, color = tokens.color.textSecondary)
        }
    }
}


private suspend fun stageAndSharePdf(
    context: Context,
    documentId: String,
    filename: String,
    bytes: ByteArray,
) {
    val staged = withContext(Dispatchers.IO) {
        val signature = "%PDF-".toByteArray(Charsets.US_ASCII)
        require(bytes.size >= signature.size && bytes.copyOfRange(0, signature.size).contentEquals(signature)) {
            "pdf_signature_invalid"
        }
        val directory = File(context.cacheDir, "document_exports").apply {
            mkdirs()
            require(canonicalPath.startsWith(context.cacheDir.canonicalPath)) { "export_path_invalid" }
        }
        val safeId = documentId.filter { it.isLetterOrDigit() || it == '_' || it == '-' }.take(80)
        val safeName = filename.substringAfterLast('/').substringAfterLast('\\')
            .filter { it.isLetterOrDigit() || it in "._- " }
            .trim()
            .ifBlank { "document.pdf" }
            .let { if (it.lowercase().endsWith(".pdf")) it else "$it.pdf" }
            .take(120)
        File(directory, "$safeId-$safeName").apply { writeBytes(bytes) }
    }
    val uri = FileProvider.getUriForFile(
        context,
        "${context.packageName}.fileprovider",
        staged,
    )
    val send = Intent(Intent.ACTION_SEND).apply {
        type = "application/pdf"
        putExtra(Intent.EXTRA_STREAM, uri)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    context.startActivity(Intent.createChooser(send, "Share PDF"))
}


private suspend fun renderPdfPage(
    context: Context,
    documentId: String,
    bytes: ByteArray,
    requestedPage: Int,
    zoom: Float,
): RenderedPdf = withContext(Dispatchers.IO) {
    val safe = documentId.filter { it.isLetterOrDigit() || it == '_' || it == '-' }.take(80)
    val file = File(context.cacheDir, "van-document-$safe.pdf")
    file.writeBytes(bytes)
    val descriptor = ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY)
    try {
        val renderer = PdfRenderer(descriptor)
        try {
            require(renderer.pageCount > 0) { "pdf_has_no_pages" }
            val index = requestedPage.coerceIn(0, renderer.pageCount - 1)
            val page = renderer.openPage(index)
            try {
                val width = (page.width * zoom).toInt().coerceIn(1, 2400)
                val height = (page.height * zoom).toInt().coerceIn(1, 3200)
                val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
                page.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                RenderedPdf(bitmap, index, renderer.pageCount)
            } finally {
                page.close()
            }
        } finally {
            renderer.close()
        }
    } finally {
        descriptor.close()
    }
}
