package com.dial.van.command

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dial.van.degraded.DegradedSubsystem
import com.dial.van.degraded.RestoreAction
import com.dial.van.degraded.SubsystemHealth
import com.dial.van.degraded.SubsystemStatus
import com.dial.van.visual.VanGlassStyle
import com.dial.van.visual.VanGlassTokens

/**
 * What is not working, and what the owner can do about it.
 *
 * P3-AND-005 — every one of `RestoreAction`'s seven values was defined, carried through the
 * degraded-mode contract, and rendered by nothing. The contract therefore carried an
 * actionable instruction to a screen that dropped it, which is the worst of both: VAN knew
 * what the owner should press and never said so.
 *
 * P3-AND-004 is the other half. Five subsystems reported WORKING because nothing wrote them,
 * so this panel would have been empty on a phone with every permission denied. The signals
 * that fill it now come from `SubsystemHealth`, and the wording is `SubsystemHealth`'s too,
 * so what the owner reads is executed in `android/verification` rather than checked by eye.
 *
 * The panel renders nothing when nothing is wrong. A permanent "all systems nominal" banner
 * is how an owner learns to stop reading this part of the screen.
 */
@Composable
internal fun DegradedPanel(
    subsystems: List<DegradedSubsystem>,
    glass: VanGlassStyle,
    onRestore: (DegradedSubsystem) -> Unit,
) {
    val impaired = subsystems.filter { it.status != SubsystemStatus.WORKING }
    if (impaired.isEmpty()) return

    AdminCard(glass) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(
                if (impaired.any { it.status == SubsystemStatus.BROKEN }) {
                    "Some things are not working"
                } else {
                    "Some things are switched off"
                },
                color = MaterialTheme.colorScheme.onSurface,
                fontSize = 15.sp,
                fontWeight = FontWeight.Bold,
            )
            impaired.forEach { subsystem ->
                Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(
                        subsystem.label,
                        color = when (subsystem.status) {
                            SubsystemStatus.BROKEN -> Color(VanGlassTokens.ACCENT_RED)
                            SubsystemStatus.WONT_DO -> Color(VanGlassTokens.ACCENT_AMBER)
                            SubsystemStatus.WORKING -> MaterialTheme.colorScheme.onSurface
                        },
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        subsystem.detail,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 11.sp,
                    )
                    if (SubsystemHealth.isActionable(subsystem.restoreAction)) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            modifier = Modifier.fillMaxWidth().padding(top = 2.dp),
                        ) {
                            Button(onClick = { onRestore(subsystem) }) {
                                Text(
                                    SubsystemHealth.restoreLabel(subsystem.restoreAction),
                                    fontSize = 11.sp,
                                )
                            }
                            Text(
                                SubsystemHealth.restoreSentence(subsystem.restoreAction),
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 10.sp,
                            )
                        }
                    } else if (subsystem.restoreAction == RestoreAction.NONE) {
                        // Saying nothing here would read as "there is a button missing".
                        Text(
                            "There is nothing to press for this one.",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 10.sp,
                        )
                    }
                }
            }
        }
    }
}
