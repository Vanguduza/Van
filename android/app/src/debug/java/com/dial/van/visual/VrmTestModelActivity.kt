package com.dial.van.visual

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * DEBUG ONLY — the owner picks a `.vrm` downloaded on the phone, and it is copied into the
 * app's private files, where [VrmTestRenderer] draws it in place of VAN everywhere he appears.
 * "Remove" deletes the copy and VAN is himself again.
 */
class VrmTestModelActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            VanTheme {
                Surface(Modifier.fillMaxSize()) {
                    val scope = rememberCoroutineScope()
                    val file = VrmTestModel.file(this)
                    var status by remember { mutableStateOf(describe()) }
                    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
                        if (uri == null) return@rememberLauncherForActivityResult
                        status = "Importing…"
                        scope.launch {
                            status = withContext(Dispatchers.IO) {
                                runCatching {
                                    contentResolver.openInputStream(uri)!!.use { input ->
                                        file.outputStream().use { input.copyTo(it) }
                                    }
                                    describe()
                                }.getOrElse { "Import failed: ${it.message}" }
                            }
                        }
                    }
                    Column(
                        modifier = Modifier.padding(24.dp),
                        verticalArrangement = Arrangement.spacedBy(16.dp),
                    ) {
                        Text("Test model (debug only)")
                        Text(
                            "Pick a .vrm file downloaded on this phone. It is drawn in place of VAN " +
                                "everywhere he appears, driven by his live state. It stays on this " +
                                "phone and is never part of a release build.",
                        )
                        Text(status)
                        Button(onClick = { picker.launch(arrayOf("*/*")) }) { Text("Import .vrm") }
                        OutlinedButton(onClick = {
                            file.delete()
                            status = describe()
                        }) { Text("Remove test model") }
                    }
                }
            }
        }
    }

    private fun describe(): String {
        val file = VrmTestModel.file(this)
        return if (file.isFile) {
            "Test model in use (${file.length() / 1024} KB). Reopen VAN's screens to see it."
        } else {
            "No test model. VAN is drawn as himself."
        }
    }
}
