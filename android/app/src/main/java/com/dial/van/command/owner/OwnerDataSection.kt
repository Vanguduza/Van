package com.dial.van.command.owner

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.components.SectionHeader
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.text.DateFormat
import java.util.Date

interface OwnerSectionActions {
    val canMutate: Boolean
    fun pending(key: String): Boolean
    fun refresh()
    fun mutate(key: String, success: String, action: suspend () -> JSONObject)
}

/** Each source recovers independently and keeps its last read visible when a refresh fails. */
@Composable
fun OwnerDataSection(
    title: String,
    load: suspend () -> JSONObject,
    content: @Composable (JSONObject, OwnerSectionActions) -> Unit,
) {
    val tokens = LocalVanTokens.current
    val scope = rememberCoroutineScope()
    var data by remember(title) { mutableStateOf<JSONObject?>(null) }
    var loading by remember(title) { mutableStateOf(false) }
    var error by remember(title) { mutableStateOf<String?>(null) }
    var mutationError by remember(title) { mutableStateOf<String?>(null) }
    var notice by remember(title) { mutableStateOf<String?>(null) }
    var pending by remember(title) { mutableStateOf<Set<String>>(emptySet()) }
    var lastRead by remember(title) { mutableStateOf(0L) }
    suspend fun refreshData() {
        if (loading) return
        loading = true
        try {
            data = load()
            lastRead = System.currentTimeMillis()
            error = null
            mutationError = null
        } catch (cancel: CancellationException) {
            throw cancel
        } catch (failure: Exception) {
            error = failure.message ?: "VAN is temporarily unavailable."
        } finally { loading = false }
    }
    val actions = object : OwnerSectionActions {
        override val canMutate get() = data != null && error == null && mutationError == null && !loading && pending.isEmpty()
        override fun pending(key: String) = key in pending
        override fun refresh() { scope.launch { refreshData() } }
        override fun mutate(key: String, success: String, action: suspend () -> JSONObject) {
            if (!canMutate || key in pending) return
            pending = pending + key
            mutationError = null
            notice = null
            scope.launch {
                try {
                    action()
                    notice = success
                    refreshData()
                } catch (cancel: CancellationException) {
                    throw cancel
                } catch (failure: Exception) {
                    mutationError = "VAN could not confirm this change. Refresh before trying again. ${failure.message.orEmpty()}"
                } finally { pending = pending - key }
            }
        }
    }
    LaunchedEffect(title) {
        refreshData()
        while (true) {
            delay(15_000L)
            if (error != null && pending.isEmpty()) refreshData()
        }
    }
    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
        SectionHeader(title)
        if (loading) Text("Refreshing…", style = tokens.type.label, color = tokens.color.textSecondary)
        error?.let { Text("VAN could not refresh this section. It will retry automatically. $it", style = tokens.type.body, color = tokens.color.textSecondary) }
        if (lastRead > 0L) Text("Last read ${ownerTime(lastRead)}${if (error != null) " · last known information" else ""}", style = tokens.type.label, color = tokens.color.textTertiary)
        mutationError?.let { Text(it, style = tokens.type.body, color = tokens.color.textSecondary) }
        notice?.let { Text(it, style = tokens.type.label, color = tokens.color.textSecondary) }
        OutlinedButton(enabled = !loading && pending.isEmpty(), onClick = { actions.refresh() }) { Text("Refresh") }
        data?.let { content(it, actions) }
    }
}

fun JSONArray?.ownerRows(): List<JSONObject> = if (this == null) emptyList() else (0 until length()).mapNotNull { optJSONObject(it) }
fun ownerTime(value: Long): String = if (value <= 0L) "Not recorded" else DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT).format(Date(value))
fun JSONObject.ownerValue(key: String, fallback: String = "Not recorded"): String = if (isNull(key)) fallback else optString(key).ifBlank { fallback }
