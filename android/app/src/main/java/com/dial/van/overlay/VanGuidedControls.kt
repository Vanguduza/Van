package com.dial.van.overlay

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dial.van.visual.VanGlassTokens
import com.dial.van.visual.rememberVanGuidanceTarget

/** Original controls keep their click behavior; measured guidance is a separate long press. */
@OptIn(ExperimentalFoundationApi::class)
@Composable
internal fun ContextAction(title: String, detail: String, onClick: () -> Unit) {
    val guidance = rememberVanGuidanceTarget("overlay-context:$title")
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = 64.dp)
            .clip(RoundedCornerShape(10.dp))
            .background(Color(VanGlassTokens.BABY_CYAN).copy(alpha = 0.08f))
            .then(guidance.modifier)
            .combinedClickable(onClick = onClick, onLongClick = guidance.point, onLongClickLabel = "Ask VAN to point here")
            .padding(9.dp),
    ) {
        Column {
            Text(title, color = Color.White, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
            Text(detail, color = Color(0xFFB8CBD2), fontSize = 12.sp)
        }
    }
}


@OptIn(ExperimentalFoundationApi::class)
@Composable
internal fun WorkChip(label: String, accent: Int, selected: Boolean = false, enabled: Boolean = true, onClick: () -> Unit) {
    val guidance = rememberVanGuidanceTarget("overlay-chip:$label")
    Box(
        modifier = Modifier
            .heightIn(min = 48.dp)
            .widthIn(min = 48.dp)
            .clip(RoundedCornerShape(9.dp))
            .background(Color(accent).copy(alpha = if (selected) 0.28f else 0.12f))
            .border(if (selected) 1.5.dp else 0.dp, if (selected) Color(accent) else Color.Transparent, RoundedCornerShape(9.dp))
            .semantics { this.selected = selected }
            .then(guidance.modifier)
            .combinedClickable(enabled = enabled, role = Role.Button, onClick = onClick,
                onLongClick = guidance.point, onLongClickLabel = "Ask VAN to point here")
            .padding(horizontal = 12.dp, vertical = 8.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = if (enabled) Color(0xFFF4FCFF) else Color(0xFF83969E), fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
    }
}
