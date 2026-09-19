package com.dial.van.command.modules

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.OutlinedTextField
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dial.van.VanApplication
import com.dial.van.command.AdminCard
import com.dial.van.command.SectionHeader
import com.dial.van.command.TruthMessage
import com.dial.van.notification.AppNotificationPolicy
import com.dial.van.notification.QuietHoursConfig

/**
 * Which apps VAN reads, and when it stops.
 *
 * P2-AND-017. `NotificationPolicyStore.setPolicy` and `setQuietHours` had no caller.
 * `VanNotificationListenerService` reads the policy on every arriving notification and
 * mutes, prioritises or drops accordingly — so the mechanism was live and running, and the
 * owner had no way to tell it anything. Every app was NORMAL forever and quiet hours were
 * permanently off.
 *
 * That is a worse failure than a missing screen. VAN holds a notification-listener
 * permission, which is among the most invasive Android grants, and the controls that make
 * it tolerable existed only as functions.
 *
 * The screen lists apps the owner has already decided about rather than every installed
 * package: enumerating installed apps needs QUERY_ALL_PACKAGES, a permission Play treats as
 * sensitive and which VAN does not need — a package arrives here because a notification
 * from it did.
 */
@Composable
internal fun NotificationPolicyModule(
    app: VanApplication,
    glass: com.dial.van.visual.VanGlassStyle,
) {
    val store = app.notificationPolicyStore
    var decided by remember { mutableStateOf(store.decidedPackages()) }
    var quiet by remember { mutableStateOf(store.quietHours()) }
    // Survives rotation: a half-typed package name is exactly what is lost otherwise.
    var draft by rememberSaveable { mutableStateOf("") }

    fun reload() {
        decided = store.decidedPackages()
        quiet = store.quietHours()
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item { SectionHeader("Notifications", "Which apps Van reads, and when it stops") }

        item {
            AdminCard(glass) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Quiet hours", color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.Bold)
                    Text(
                        if (quiet.enabled) {
                            "Van ignores everything except priority apps from " +
                                "${quiet.startHour}:00 to ${quiet.endHour}:00."
                        } else {
                            "Van reads notifications at any hour."
                        },
                        color = Color(0xFFD7E7EC),
                        fontSize = 12.sp,
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = {
                            store.setQuietHours(quiet.copy(enabled = !quiet.enabled))
                            reload()
                        }) { Text(if (quiet.enabled) "Turn off" else "Turn on") }
                        Button(
                            onClick = {
                                store.setQuietHours(
                                    QuietHoursConfig(
                                        enabled = quiet.enabled,
                                        startHour = (quiet.startHour + 1) % 24,
                                        endHour = quiet.endHour,
                                    ),
                                )
                                reload()
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF1E3A44)),
                        ) { Text("Start +1h") }
                        Button(
                            onClick = {
                                store.setQuietHours(
                                    QuietHoursConfig(
                                        enabled = quiet.enabled,
                                        startHour = quiet.startHour,
                                        endHour = (quiet.endHour + 1) % 24,
                                    ),
                                )
                                reload()
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF1E3A44)),
                        ) { Text("End +1h") }
                    }
                }
            }
        }

        item { SectionHeader("Apps", "Set once a notification from the app has arrived") }
        if (decided.isEmpty()) {
            item {
                TruthMessage(
                    "Van has not seen a notification from any app yet, so there is nothing " +
                        "to set. Apps appear here once one arrives.",
                )
            }
        }
        items(decided.entries.sortedBy { it.key }.toList(), key = { it.key }) { entry ->
            AdminCard(glass) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(entry.key, color = Color.White, fontSize = 14.sp, fontWeight = FontWeight.Bold)
                    Text(
                        when (entry.value) {
                            AppNotificationPolicy.MUTE -> "Van ignores this app entirely."
                            AppNotificationPolicy.PRIORITY -> "Van reads this app even during quiet hours."
                            AppNotificationPolicy.NORMAL -> "Van reads this app outside quiet hours."
                        },
                        color = Color(0xFFD7E7EC),
                        fontSize = 12.sp,
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        for (option in AppNotificationPolicy.entries) {
                            Button(
                                onClick = {
                                    store.setPolicy(entry.key, option)
                                    reload()
                                },
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = if (entry.value == option) {
                                        Color(0xFF2E6B7A)
                                    } else {
                                        Color(0xFF1E3A44)
                                    },
                                ),
                            ) { Text(option.name.lowercase().replaceFirstChar { it.uppercase() }) }
                        }
                    }
                }
            }
        }

        item {
            AdminCard(glass) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Mute an app by name", color = Color.White, fontSize = 14.sp)
                    Text(
                        "For an app whose notifications have not reached Van yet.",
                        color = Color(0xFFBCD1D8),
                        fontSize = 11.sp,
                    )
                    OutlinedTextField(
                        value = draft,
                        onValueChange = { draft = it },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Package name") },
                        maxLines = 1,
                    )
                    Button(
                        onClick = {
                            val pkg = draft.trim()
                            if (pkg.isNotEmpty()) {
                                store.setPolicy(pkg, AppNotificationPolicy.MUTE)
                                draft = ""
                                reload()
                            }
                        },
                    ) { Text("Mute") }
                }
            }
        }
    }
}
