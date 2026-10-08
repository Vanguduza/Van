package com.dial.van.visual

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.yield

/**
 * Debug-only interactive lab for exercising the complete Candidate-B Rive contract.
 * Nothing here is compiled into release builds.
 */
@Composable
fun CharacterRigLab(bytes: ByteArray) {
    var stateCode by remember { mutableIntStateOf(VanDurableState.IDLE.code) }
    var actionCode by remember { mutableIntStateOf(0) }
    var viseme by remember { mutableIntStateOf(0) }
    var speaking by remember { mutableStateOf(false) }
    var listening by remember { mutableStateOf(false) }
    var attentionX by remember { mutableFloatStateOf(0f) }
    var attentionY by remember { mutableFloatStateOf(0f) }
    var mouthOpen by remember { mutableFloatStateOf(0f) }
    var urgency by remember { mutableFloatStateOf(0f) }
    var trigger by remember { mutableStateOf<String?>(null) }
    var autoDemo by remember { mutableStateOf(false) }
    var showAura by remember { mutableStateOf(true) }

    val scope = rememberCoroutineScope()
    val durable = VanDurableState.fromCode(stateCode)
    val actionName = VanFiniteAction.fromCode(actionCode)?.name ?: "NONE"
    val visemeName = listOf("neutral_closed", "small_neutral", "medium_spread", "wide_vertical", "rounded")[viseme.coerceIn(0, 4)]

    LaunchedEffect(autoDemo) {
        if (!autoDemo) return@LaunchedEffect
        while (true) {
            for (code in 0..17) {
                stateCode = code
                listening = code == VanDurableState.LISTENING.code
                speaking = code == VanDurableState.SPEAKING.code
                mouthOpen = if (speaking) 0.72f else 0f
                viseme = if (speaking) ((code % 4) + 1) else 0
                attentionX = when (code % 3) { 0 -> -0.85f; 1 -> 0f; else -> 0.85f }
                attentionY = when (code % 3) { 0 -> 0.7f; 1 -> 0f; else -> -0.7f }
                urgency = if (code in 13..16) 0.85f else 0f
                delay(900)
            }
            stateCode = VanDurableState.IDLE.code
            speaking = false
            listening = false
            mouthOpen = 0f
            viseme = 0
            attentionX = 0f
            attentionY = 0f
            urgency = 0f
            for (code in 1..14) {
                actionCode = code
                delay(900)
            }
            actionCode = 0
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xFF0B0F14))
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("VAN Candidate B — Character Rig Lab")
        Text("LIVE .RIV • animated mechanics prototype • debug only")
        Text("State: ${durable.name}  •  Action: $actionName  •  Viseme: $viseme $visemeName")

        BoxWithConstraints(
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(1f),
            contentAlignment = Alignment.Center,
        ) {
            val previewSize = minOf(maxWidth, 340.dp)
            val auraTransition = rememberInfiniteTransition(label = "rig-lab-aura")
            val auraPhase by auraTransition.animateFloat(
                initialValue = 0f,
                targetValue = 1f,
                animationSpec = infiniteRepeatable(tween(2200, easing = LinearEasing)),
                label = "rig-lab-aura-phase",
            )
            Box(Modifier.size(previewSize), contentAlignment = Alignment.Center) {
                if (showAura) {
                    VanAuraLayer(
                        spec = VanAuraSpecs.forState(durable, VanEffectBudget.FULL),
                        semanticSpec = VanAuraSpecs.forState(durable, VanEffectBudget.FULL),
                        phase = auraPhase,
                        budget = VanEffectBudget.FULL,
                        characterScale = 0.90f,
                        framing = VanFraming.FULL_BODY,
                        depth = VanAuraDepth.BACK,
                        modifier = Modifier.fillMaxSize(),
                    )
                }
                RiveCandidateFrame(
                    bytes = bytes,
                    size = previewSize * 0.88f,
                    stateCode = stateCode,
                    speaking = speaking,
                    listening = listening,
                    attentionX = attentionX,
                    attentionY = attentionY,
                    mouthOpen = mouthOpen,
                    urgency = urgency,
                    viseme = viseme,
                    actionCode = actionCode,
                    trigger = trigger,
                )
                if (showAura) {
                    VanAuraLayer(
                        spec = VanAuraSpecs.forState(durable, VanEffectBudget.FULL),
                        semanticSpec = VanAuraSpecs.forState(durable, VanEffectBudget.FULL),
                        phase = auraPhase,
                        budget = VanEffectBudget.FULL,
                        characterScale = 0.90f,
                        framing = VanFraming.FULL_BODY,
                        depth = VanAuraDepth.FRONT,
                        modifier = Modifier.fillMaxSize(),
                    )
                }
            }
        }

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("Auto-cycle whole rig")
            Switch(checked = autoDemo, onCheckedChange = { autoDemo = it })
        }
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("Native VAN aura")
            Switch(checked = showAura, onCheckedChange = { showAura = it })
        }

        HorizontalDivider()

        Text("Durable state — all 18")
        Stepper(
            label = durable.name,
            onPrevious = { stateCode = (stateCode - 1).coerceAtLeast(0) },
            onNext = { stateCode = (stateCode + 1).coerceAtMost(17) },
        )

        Text("Finite action — all 14")
        Stepper(
            label = actionName,
            onPrevious = { actionCode = (actionCode - 1).coerceAtLeast(0) },
            onNext = { actionCode = (actionCode + 1).coerceAtMost(14) },
        )

        Text("Speech viseme — all 5")
        Stepper(
            label = "$viseme • $visemeName",
            onPrevious = { viseme = (viseme - 1).coerceAtLeast(0) },
            onNext = { viseme = (viseme + 1).coerceAtMost(4) },
        )

        ToggleRow("Speaking", speaking) { speaking = it }
        ToggleRow("Listening", listening) { listening = it }

        RigSlider("Gaze X", attentionX, -1f..1f) { attentionX = it }
        RigSlider("Gaze Y", attentionY, -1f..1f) { attentionY = it }
        RigSlider("Mouth open", mouthOpen, 0f..1f) { mouthOpen = it }
        RigSlider("Urgency", urgency, 0f..1f) { urgency = it }

        Text("One-shot triggers")
        val triggerRows = listOf(
            listOf("wave", "ack", "point", "celebrate"),
            listOf("warning", "shrug", "present", "panel"),
        )
        triggerRows.forEach { row ->
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                row.forEach { wire ->
                    Button(
                        modifier = Modifier.weight(1f),
                        onClick = {
                            scope.launch {
                                trigger = null
                                yield()
                                trigger = wire
                                delay(120)
                                trigger = null
                            }
                        },
                    ) { Text(wire) }
                }
            }
        }

        HorizontalDivider()

        Text("Readability sizes")
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceEvenly,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            RiveCandidateFrame(
                bytes = bytes,
                size = 48.dp,
                stateCode = stateCode,
                speaking = speaking,
                listening = listening,
                attentionX = attentionX,
                attentionY = attentionY,
                mouthOpen = mouthOpen,
                urgency = urgency,
                viseme = viseme,
                actionCode = actionCode,
            )
            RiveCandidateFrame(
                bytes = bytes,
                size = 96.dp,
                stateCode = stateCode,
                speaking = speaking,
                listening = listening,
                attentionX = attentionX,
                attentionY = attentionY,
                mouthOpen = mouthOpen,
                urgency = urgency,
                viseme = viseme,
                actionCode = actionCode,
            )
        }

        Spacer(Modifier.height(24.dp))
        Text("Prototype scope: mechanics are animated; M1 semantic-vector review and M2/M3 polish gates are still required before this can become production van.riv.")
    }
}

@Composable
private fun Stepper(label: String, onPrevious: () -> Unit, onNext: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Button(onClick = onPrevious) { Text("−") }
        Text(label, modifier = Modifier.weight(1f))
        Button(onClick = onNext) { Text("+") }
    }
}

@Composable
private fun ToggleRow(label: String, checked: Boolean, onCheckedChange: (Boolean) -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label)
        Switch(checked = checked, onCheckedChange = onCheckedChange)
    }
}

@Composable
private fun RigSlider(label: String, value: Float, range: ClosedFloatingPointRange<Float>, onValueChange: (Float) -> Unit) {
    Column {
        Text("$label: ${"%.2f".format(value)}")
        Slider(
            value = value,
            onValueChange = onValueChange,
            valueRange = range,
        )
    }
}