package com.dial.van.trading.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dial.van.trading.ConfidenceBand
import com.dial.van.trading.DataState
import com.dial.van.trading.Loaded
import com.dial.van.trading.SafetyIdentity
import com.dial.van.trading.TradeConfidence
import com.dial.van.trading.TradeRow
import com.dial.van.visual.VanGlassStyle
import com.dial.van.visual.VanGlassSurface
import com.dial.van.visual.VanGlassTokens

/** Trading semantic colours (blueprint §41): kept separate from Van's emotional/state palette. */
object TradingColors {
    val positive = Color(0xFF69F0AE)
    val negative = Color(0xFFFF5252)
    val warning = Color(0xFFFFB300)
    val neutral = Color(0xFF9AA7B6)
    val text = Color(0xFFE7ECF2)
    val muted = Color(0xFF8A97A6)
    val accent = Color(VanGlassTokens.ACCENT_CYAN)
    val violet = Color(0xFF7C4DFF)
    fun signed(v: Double?): Color = when { v == null -> neutral; v > 0 -> positive; v < 0 -> negative; else -> text }
}

@Composable
fun SectionPanel(title: String, glass: VanGlassStyle, modifier: Modifier = Modifier, action: (@Composable () -> Unit)? = null, content: @Composable () -> Unit) {
    VanGlassSurface(style = glass, modifier = modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(title, color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                action?.invoke()
            }
            Spacer(modifier = Modifier.height(8.dp))
            content()
        }
    }
}

@Composable
fun MetricTile(label: String, value: String, modifier: Modifier = Modifier, tint: Color = TradingColors.text, sub: String? = null) {
    Column(modifier = modifier.clip(RoundedCornerShape(12.dp)).background(Color.White.copy(alpha = 0.05f)).padding(horizontal = 12.dp, vertical = 10.dp)) {
        Text(label, color = TradingColors.muted, fontSize = 10.sp, maxLines = 1)
        Text(value, color = tint, fontSize = 17.sp, fontWeight = FontWeight.Bold, fontFamily = FontFamily.Monospace, maxLines = 1)
        if (sub != null) Text(sub, color = TradingColors.muted, fontSize = 10.sp, maxLines = 1)
    }
}

@Composable
fun Chip(text: String, argb: Long, modifier: Modifier = Modifier, filled: Boolean = false) {
    Box(modifier = modifier.clip(RoundedCornerShape(8.dp)).background(Color(argb).copy(alpha = if (filled) 0.9f else 0.18f)).padding(horizontal = 8.dp, vertical = 3.dp)) {
        Text(text, color = if (filled) Color(0xFF10151F) else Color(argb), fontSize = 10.sp, fontWeight = FontWeight.Bold, maxLines = 1)
    }
}

/** LIVE is solid and loud; everything else is translucent. Never colour alone: the label is the word itself (§9, §41). */
@Composable
fun SafetyChip(safety: SafetyIdentity, modifier: Modifier = Modifier) = Chip(safety.label, safety.argb, modifier, filled = safety == SafetyIdentity.LIVE)

@Composable
fun DataStateChip(state: DataState, modifier: Modifier = Modifier) = Chip(state.label, state.argb, modifier, filled = state == DataState.STALE || state == DataState.OFFLINE)

@Composable
fun ConfidenceChip(c: TradeConfidence, modifier: Modifier = Modifier) = Chip("${c.percentLabel} ${c.band.label}", c.band.argb, modifier)

@Composable
fun TabRowChips(options: List<String>, selected: String, onSelect: (String) -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        options.forEach { o ->
            val active = o == selected
            Box(modifier = Modifier.clip(RoundedCornerShape(10.dp)).background(TradingColors.accent.copy(alpha = if (active) 0.28f else 0.08f)).clickable { onSelect(o) }.padding(horizontal = 12.dp, vertical = 6.dp)) {
                Text(o, color = if (active) TradingColors.accent else TradingColors.text, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
fun TradeRowCard(row: TradeRow, onOpen: (() -> Unit)? = null) {
    Column(modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(Color.White.copy(alpha = 0.04f)).let { if (onOpen != null) it.clickable { onOpen() } else it }.padding(horizontal = 10.dp, vertical = 8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(row.headline, color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, modifier = Modifier.weight(1f))
            Spacer(modifier = Modifier.width(6.dp))
            ConfidenceChip(row.confidence)
        }
        Text(row.detail, color = TradingColors.neutral, fontSize = 10.sp, maxLines = 2)
        row.reasons.firstOrNull()?.let { Text(it, color = TradingColors.muted, fontSize = 10.sp, maxLines = 1) }
    }
}

@Composable
fun EmptyState(text: String, hint: String? = null) {
    Column(modifier = Modifier.fillMaxWidth().padding(vertical = 10.dp)) {
        Text(text, color = TradingColors.neutral, fontSize = 12.sp)
        if (hint != null) Text(hint, color = TradingColors.muted, fontSize = 10.sp)
    }
}

@Composable
fun <T> LoadedBox(state: Loaded<T>, empty: String = "Nothing to show yet.", content: @Composable (T) -> Unit) {
    when (state) {
        Loaded.Loading -> Row(verticalAlignment = Alignment.CenterVertically) { CircularProgressIndicator(modifier = Modifier.height(16.dp).width(16.dp), strokeWidth = 2.dp, color = TradingColors.accent); Spacer(Modifier.width(8.dp)); Text("Reading the ledger…", color = TradingColors.neutral, fontSize = 11.sp) }
        is Loaded.Unavailable -> Text(state.reason, color = TradingColors.warning, fontSize = 11.sp)
        is Loaded.Ready -> content(state.value)
    }
}

val ConfidenceBand.chipArgb: Long get() = argb
