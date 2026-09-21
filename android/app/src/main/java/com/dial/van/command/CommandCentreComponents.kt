package com.dial.van.command

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dial.van.control.VanConversationMessage
import com.dial.van.control.VanMessageRole
import com.dial.van.status.OwnerLanguage
import com.dial.van.status.VanCommandStatus
import com.dial.van.visual.VanGlassSurface
import com.dial.van.visual.VanGlassTokens
import org.json.JSONArray
import org.json.JSONObject

/**
 * The pieces every Command Centre module draws with.
 *
 * Split out of `CommandCentreActivity` (P3-AND-009).
 */

@Composable
internal fun DashboardPageHeader(
    title: String,
    parent: String,
    back: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(vertical = 4.dp)) {
        Button(
            onClick = back,
            contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Color(VanGlassTokens.TINT_NAVY).copy(alpha = 0.72f)),
        ) {
            Text("← $parent", fontSize = 10.sp)
        }
        Text(title, color = Color.White, fontSize = 19.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
internal fun SectionHeader(title: String, detail: String) {
    Column(modifier = Modifier.padding(vertical = 4.dp)) {
        Text(title, color = Color.White, fontSize = 19.sp, fontWeight = FontWeight.Bold)
        Text(detail, color = Color(0xFFBCD1D8), fontSize = 11.sp)
    }
}

@Composable
internal fun AdminCard(
    glass: com.dial.van.visual.VanGlassStyle,
    content: @Composable () -> Unit,
) {
    VanGlassSurface(style = glass, modifier = Modifier.fillMaxWidth()) {
        Box(modifier = Modifier.padding(14.dp)) { content() }
    }
}

@Composable
internal fun AdminActionCard(
    title: String,
    detail: String,
    glass: com.dial.van.visual.VanGlassStyle,
    onClick: () -> Unit,
) {
    AdminCard(glass) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(modifier = Modifier.weight(1f)) {
                Text(title, color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.Bold)
                Text(detail, color = Color(0xFFBCD1D8), fontSize = 11.sp)
            }
            Button(onClick = onClick) { Text("Open") }
        }
    }
}

@Composable
internal fun TruthMessage(text: String, warning: Boolean = false) {
    Text(
        text,
        color = if (warning) Color(VanGlassTokens.ACCENT_AMBER) else Color(0xFFBCD1D8),
        fontSize = 12.sp,
        modifier = Modifier.padding(vertical = 8.dp),
    )
}

@Composable
internal fun CommandMessageBubble(
    message: VanConversationMessage,
    glass: com.dial.van.visual.VanGlassStyle,
) {
    val tint = when (message.role) {
        VanMessageRole.OWNER -> Color(VanGlassTokens.ACCENT_CYAN)
        VanMessageRole.VAN -> Color(VanGlassTokens.BABY_CYAN)
        VanMessageRole.SYSTEM -> Color(VanGlassTokens.ACCENT_AMBER)
    }
    VanGlassSurface(
        style = glass.copy(
            backgroundAlpha = (glass.backgroundAlpha - 0.08f).coerceAtLeast(0.52f),
            contaminationAlpha = 0.08f,
        ),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(10.dp)) {
            Text(
                when (message.role) {
                    VanMessageRole.OWNER -> "You"
                    VanMessageRole.VAN -> "Van"
                    VanMessageRole.SYSTEM -> "System"
                },
                color = tint,
                fontSize = 10.sp,
                fontWeight = FontWeight.Bold,
            )
            Text(message.text, color = Color(0xFFF4FCFF), fontSize = 12.sp)
            message.status?.let {
                // P2-UX-001 — this printed `status.name`, so the owner read
                // PARTIALLY_SUCCEEDED and COULD_NOT_VERIFY off their own phone.
                Text(OwnerLanguage.commandStatus(it), color = statusColor(it), fontSize = 9.sp)
            }
        }
    }
}

/**
 * Exhaustive on purpose (P0-EXEC-003). The `else` branch this replaces painted every
 * status it did not name in the working colour, so an unknown or unverified outcome looked
 * to the owner exactly like one under way.
 */

internal fun statusColor(status: VanCommandStatus): Color = when (status) {
    VanCommandStatus.SUCCEEDED -> Color(VanGlassTokens.ACCENT_GREEN)
    VanCommandStatus.FAILED,
    VanCommandStatus.CANCELLED,
    VanCommandStatus.EXPIRED,
    VanCommandStatus.REFUSED,
    -> Color(VanGlassTokens.ACCENT_RED)
    // Finished, but not cleanly. Amber is the colour that asks the owner to look.
    VanCommandStatus.PARTIALLY_SUCCEEDED,
    VanCommandStatus.COULD_NOT_VERIFY,
    VanCommandStatus.APPROVAL_REQUIRED,
    VanCommandStatus.UNKNOWN,
    -> Color(VanGlassTokens.ACCENT_AMBER)
    VanCommandStatus.LOCAL_DRAFT,
    VanCommandStatus.SUBMITTING,
    VanCommandStatus.ACCEPTED,
    VanCommandStatus.IN_FLIGHT,
    -> Color(VanGlassTokens.EDGE_CYAN)
}

internal fun JSONArray.objectList(): List<JSONObject> = buildList {
    for (index in 0 until length()) optJSONObject(index)?.let(::add)
}

internal fun JSONArray.stringList(): List<String> = buildList {
    for (index in 0 until length()) {
        optString(index).takeIf { it.isNotBlank() }?.let(::add)
    }
}
