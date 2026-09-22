package com.dial.van.visual

import android.content.Context
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import app.rive.runtime.kotlin.RiveAnimationView
import app.rive.runtime.kotlin.core.Alignment as RiveAlignment
import app.rive.runtime.kotlin.core.Fit
import app.rive.runtime.kotlin.core.Loop
import app.rive.runtime.kotlin.core.Rive

@Composable
fun RiveCandidateHost(bytes: ByteArray, modifier: Modifier = Modifier) {
    var stateCode by remember { mutableIntStateOf(VanDurableState.IDLE.code) }
    var actionCode by remember { mutableIntStateOf(0) }
    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Staged VAN candidate — debug only")
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { stateCode = (stateCode - 1).coerceAtLeast(0) }) { Text("State −") }
            Text(VanDurableState.fromCode(stateCode).name)
            Button(onClick = { stateCode = (stateCode + 1).coerceAtMost(17) }) { Text("State +") }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { actionCode = (actionCode - 1).coerceAtLeast(0) }) { Text("Action −") }
            Text(VanFiniteAction.fromCode(actionCode)?.name ?: "NONE")
            Button(onClick = { actionCode = (actionCode + 1).coerceAtMost(14) }) { Text("Action +") }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
            RiveCandidateFrame(bytes, 48.dp, stateCode = stateCode, actionCode = actionCode)
            RiveCandidateFrame(bytes, 96.dp, stateCode = stateCode, actionCode = actionCode)
            RiveCandidateFrame(bytes, 320.dp, stateCode = stateCode, actionCode = actionCode)
        }
    }
}

@Composable
fun RiveCandidateFrame(
    bytes: ByteArray,
    size: Dp,
    modifier: Modifier = Modifier,
    stateCode: Int = VanDurableState.IDLE.code,
    speaking: Boolean = false,
    listening: Boolean = false,
    attentionX: Float = 0f,
    attentionY: Float = 0f,
    mouthOpen: Float = 0f,
    urgency: Float = 0f,
    viseme: Int = 0,
    actionCode: Int = 0,
    trigger: String? = null,
) {
    AndroidView(
        modifier = modifier,
        factory = { context ->
            VanRiveRuntime.ensure(context.applicationContext)
            RiveAnimationView(context).apply {
                layoutParams = android.view.ViewGroup.LayoutParams(
                    (size.value * resources.displayMetrics.density).toInt(),
                    (size.value * resources.displayMetrics.density).toInt(),
                )
                setRiveBytes(
                    bytes,
                    artboardName = RiveBindingContract.ARTBOARD,
                    stateMachineName = RiveBindingContract.STATE_MACHINE,
                    animationName = null,
                    autoplay = true,
                    fit = Fit.CONTAIN,
                    alignment = RiveAlignment.CENTER,
                    loop = Loop.LOOP,
                )
            }
        },
        update = { view ->
            view.postDelayed({
                val sm = RiveBindingContract.STATE_MACHINE
                view.setNumberState(sm, VanInput.STATE.wireName, stateCode.toFloat())
                view.setBooleanState(sm, VanInput.SPEAKING.wireName, speaking)
                view.setBooleanState(sm, VanInput.LISTENING.wireName, listening)
                view.setNumberState(sm, VanInput.ATTENTION_X.wireName, attentionX)
                view.setNumberState(sm, VanInput.ATTENTION_Y.wireName, attentionY)
                view.setNumberState(sm, VanInput.MOUTH_OPEN.wireName, mouthOpen)
                view.setNumberState(sm, VanInput.URGENCY.wireName, urgency)
                view.setNumberState(sm, VanInput.VISEME.wireName, viseme.toFloat())
                view.setNumberState(sm, VanInput.ACTION_CODE.wireName, actionCode.toFloat())
                trigger?.let { view.fireState(sm, it) }
            }, 250L)
        },
    )
}

object VanRiveRuntime {
    @Volatile private var initialized = false

    @Synchronized
    fun ensure(context: Context) {
        if (initialized) return
        Rive.init(context.applicationContext)
        initialized = true
    }
}
