package com.dial.van.overlay

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
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
            .clip(RoundedCornerShape(10.dp))
            .background(Color(VanGlassTokens.BABY_CYAN).copy(alpha = 0.08f))
            .then(guidance.modifier)
            .combinedClickable(onClick = onClick, onLongClick = guidance.point, onLongClickLabel = "Ask VAN to point here")
            .padding(9.dp),
    ) {
        Column {
            Text(title, color = Color.White, fontWeight = FontWeight.SemiBold, fontSize = 12.sp)
            Text(detail, color = Color(0xFFB8CBD2), fontSize = 10.sp)
        }
    }
}


@OptIn(ExperimentalFoundationApi::class)
@Composable
internal fun WorkChip(label: String, accent: Int, onClick: () -> Unit) {
    val guidance = rememberVanGuidanceTarget("overlay-chip:$label")
    Box(
        modifier = Modifier
            .height(30.dp)
            .clip(RoundedCornerShape(9.dp))
            .background(Color(accent).copy(alpha = 0.16f))
            .then(guidance.modifier)
            .combinedClickable(onClick = onClick, onLongClick = guidance.point, onLongClickLabel = "Ask VAN to point here")
            .padding(horizontal = 7.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = Color(0xFFF4FCFF), fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
    }
}
