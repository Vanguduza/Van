package com.dial.van.visual

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Text
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.unit.dp

class RiveCandidateHostActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val production = intent.getBooleanExtra(EXTRA_PRODUCTION, false)
        val asset = if (production) RiveBindingContract.ASSET_FILE else "van_candidate.riv"
        val bytes = runCatching { assets.open(asset).use { it.readBytes() } }.getOrNull()
        setContent {
            VanTheme {
                if (intent.getBooleanExtra(EXTRA_PRODUCTION_PATH, false)) {
                    // The production renderer, not RiveCandidateFrame: VanAvatar resolves the
                    // shipped van.riv itself and reports RIVE or its fallback reason.
                    Box(Modifier.fillMaxSize().background(Color(0xFF0B0F14)), contentAlignment = Alignment.Center) {
                        VanAvatar(
                            state = VanVisualState(
                                durableState = VanDurableState.fromCode(intent.getIntExtra(EXTRA_STATE, 2)),
                                speaking = intent.getBooleanExtra(EXTRA_SPEAKING, false),
                                mouthOpen = intent.getFloatExtra(EXTRA_MOUTH_OPEN, 0f),
                                actionCode = intent.getIntExtra(EXTRA_ACTION, 0),
                            ),
                            modifier = Modifier.size(96.dp),
                            onDecision = { lastProductionDecision = it },
                        )
                    }
                } else if (bytes == null) {
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { Text("NO_RIVE_ASSET") }
                } else if (intent.getBooleanExtra(EXTRA_TEST_MODE, false)) {
                    val backgroundName = intent.getStringExtra(EXTRA_BACKGROUND) ?: "dark"
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        when (backgroundName) {
                            "light" -> Box(Modifier.fillMaxSize().background(Color(0xFFF4F6F8)))
                            "busy" -> Canvas(Modifier.fillMaxSize()) {
                                val cell = 32.dp.toPx()
                                var yy = 0f
                                var row = 0
                                while (yy < size.height) {
                                    var xx = 0f
                                    var col = 0
                                    while (xx < size.width) {
                                        drawRect(
                                            if ((row + col) % 2 == 0) Color.White else Color.Black,
                                            topLeft = androidx.compose.ui.geometry.Offset(xx, yy),
                                            size = androidx.compose.ui.geometry.Size(cell, cell),
                                        )
                                        xx += cell
                                        col++
                                    }
                                    yy += cell
                                    row++
                                }
                            }
                            else -> Box(Modifier.fillMaxSize().background(Color(0xFF0B0F14)))
                        }
                        RiveCandidateFrame(
                            bytes = bytes,
                            size = intent.getIntExtra(EXTRA_SIZE_DP, 320).dp,
                            stateCode = intent.getIntExtra(EXTRA_STATE, 2),
                            speaking = intent.getBooleanExtra(EXTRA_SPEAKING, false),
                            listening = intent.getBooleanExtra(EXTRA_LISTENING, false),
                            attentionX = intent.getFloatExtra(EXTRA_ATTENTION_X, 0f),
                            attentionY = intent.getFloatExtra(EXTRA_ATTENTION_Y, 0f),
                            mouthOpen = intent.getFloatExtra(EXTRA_MOUTH_OPEN, 0f),
                            urgency = intent.getFloatExtra(EXTRA_URGENCY, 0f),
                            viseme = intent.getIntExtra(EXTRA_VISEME, 0),
                            actionCode = intent.getIntExtra(EXTRA_ACTION, 0),
                            trigger = intent.getStringExtra(EXTRA_TRIGGER),
                        )
                    }
                } else {
                    CharacterRigLab(bytes = bytes)
                }
            }
        }
    }

    companion object {
        /** Last decision the production VanAvatar reported; read by RiveContractTest. */
        @Volatile var lastProductionDecision: VanRenderDecision? = null
        const val EXTRA_PRODUCTION_PATH = "forge.productionPath"
        const val EXTRA_TEST_MODE = "forge.test"
        const val EXTRA_PRODUCTION = "forge.production"
        const val EXTRA_BACKGROUND = "forge.background"
        const val EXTRA_SIZE_DP = "forge.sizeDp"
        const val EXTRA_STATE = "forge.state"
        const val EXTRA_SPEAKING = "forge.speaking"
        const val EXTRA_LISTENING = "forge.listening"
        const val EXTRA_ATTENTION_X = "forge.attentionX"
        const val EXTRA_ATTENTION_Y = "forge.attentionY"
        const val EXTRA_MOUTH_OPEN = "forge.mouthOpen"
        const val EXTRA_URGENCY = "forge.urgency"
        const val EXTRA_VISEME = "forge.viseme"
        const val EXTRA_ACTION = "forge.action"
        const val EXTRA_TRIGGER = "forge.trigger"
    }
}