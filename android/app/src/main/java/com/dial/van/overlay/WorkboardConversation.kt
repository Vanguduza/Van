package com.dial.van.overlay

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.gestures.scrollBy
import androidx.compose.foundation.gestures.animateScrollBy
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dial.van.control.VanConversationMessage
import com.dial.van.control.VanMessageRole
import com.dial.van.visual.rememberReducedMotion
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.collect

/** One virtualized history; opening a long chat shows the latest actual message. */
@Composable
internal fun ColumnScope.WorkboardConversation(
    messages: List<VanConversationMessage>, latestMessage: String?, accent: Int, systemLine: String,
) {
    val scroll = rememberLazyListState()
    val policy = remember { ConversationFollowPolicy() }
    val scope = rememberCoroutineScope()
    val reduced = rememberReducedMotion()
    var programmatic by remember { mutableStateOf(false) }
    var scrollGeneration by remember { mutableStateOf(0L) }
    var unread by remember { mutableStateOf(false) }
    val last = messages.lastOrNull()
    suspend fun showLatest(intent: ConversationScrollIntent) {
        if (intent == ConversationScrollIntent.NONE || messages.isEmpty()) return
        val generation = ++scrollGeneration
        programmatic = true
        try {
            if (intent == ConversationScrollIntent.IMMEDIATE || reduced) scroll.scrollToItem(messages.lastIndex)
            else scroll.animateScrollToItem(messages.lastIndex)
            // Wait for this measured item once, not another perpetual frame loop.
            // A user gesture can cancel either scroll through LazyList's mutator.
            withFrameNanos { }
            val layout = scroll.layoutInfo
            val tail = layout.visibleItemsInfo.lastOrNull { it.index == messages.lastIndex }
            if (tail != null) {
                val overflow = OverlayUsabilityPolicy.tailOverflow(tail.offset, tail.size, layout.viewportEndOffset).toFloat()
                if (overflow > 0f) {
                    if (reduced || intent == ConversationScrollIntent.IMMEDIATE) scroll.scrollBy(overflow)
                    else scroll.animateScrollBy(overflow)
                }
            }
        } finally { if (generation == scrollGeneration) programmatic = false }
    }
    LaunchedEffect(scroll) {
        snapshotFlow { Triple(scroll.isScrollInProgress, scroll.canScrollForward, programmatic) }.collect { (moving, forward, ownScroll) ->
            if (!ownScroll) { policy.ownerViewport(atLatest = !forward, interacting = moving); unread = policy.unread }
        }
    }
    LaunchedEffect(last?.id, last?.text, last?.status) {
        val intent = policy.content(last?.id, last?.let { "${it.status}:${it.text}" },
            last?.role == VanMessageRole.OWNER, scroll.isScrollInProgress && !programmatic)
        unread = policy.unread
        showLatest(intent)
    }
    Column(Modifier.weight(1f).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(5.dp)) {
        if (unread) {
            WorkChip("Latest messages", accent, modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }) {
                val intent = policy.latest(); unread = false; scope.launch { showLatest(intent) }
            }
        }
        LazyColumn(Modifier.weight(1f).fillMaxWidth(), state = scroll, verticalArrangement = Arrangement.spacedBy(7.dp)) {
            if (messages.isEmpty()) item(key = "empty") {
                Text(latestMessage ?: "Ask VAN a question or describe what you need done.", color = Color(0xFFB8CBD2), fontSize = 13.sp)
            }
            items(messages, key = { it.id }) { message -> ConversationBubble(message.role, message.text, accent) }
        }
        if (systemLine.isNotBlank()) Text(systemLine, color = Color(0xFFB8CBD2), fontSize = 12.sp, maxLines = 2)
    }
}
