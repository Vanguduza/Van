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

// CommandMessageBubble/statusColor (the VanGlassStyle-based conversation bubble and its
// P0-EXEC-003 exhaustive status→colour mapping) are removed here: the Work destination that
// replaced ChatModule.kt/the old Tasks surface (`command/work/WorkRoute.kt`) has its own
// tokens-based `ConversationBubble`/`statusRole`, following the same exhaustive-`when` rule
// (see that file). Nothing else called these two.

internal fun JSONArray.objectList(): List<JSONObject> = buildList {
    for (index in 0 until length()) optJSONObject(index)?.let(::add)
}

internal fun JSONArray.stringList(): List<String> = buildList {
    for (index in 0 until length()) {
        optString(index).takeIf { it.isNotBlank() }?.let(::add)
    }
}
