package com.dial.van.memory

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import com.dial.van.VanApplication
import com.dial.van.command.owner.OwnerDataSection
import com.dial.van.command.owner.ownerRows
import com.dial.van.command.owner.ownerTime
import com.dial.van.command.owner.ownerValue
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.components.VanPanel
import org.json.JSONObject

@Composable
internal fun LearningProducerSection(app: VanApplication) {
    val tokens = LocalVanTokens.current
    OwnerDataSection("Actual learning producers", load = { app.gatewayClient.learningProducers() }) { body, _ ->
        if (body.optBoolean("execution_grant")) Text("The learning response carries an invalid authority claim. Refresh before using it.")
        else {
            Text("These producers compute a bounded evidence snapshot when read. They are not separate agents and grant no action permission.", style = tokens.type.label)
            Text("Observed ${ownerTime(body.optLong("observed_at_ms"))}", style = tokens.type.label)
            val producers = body.optJSONArray("producers").ownerRows()
            if (producers.isEmpty()) Text("No producer state was supplied. This does not establish that learning is active.")
            producers.forEach { row -> VanPanel(dense = true) { Column {
                val producer = LearningProducer.parse(row)
                Text(producer.id.replace('-', ' '), style = tokens.type.body)
                Text(producer.ownerStatus, style = tokens.type.label)
                Text(row.ownerValue("why"), style = tokens.type.body)
                Text("${row.optInt("observations")} observations · ${row.optInt("comparisons")} comparisons · ${row.optInt("unmeasured")} unmeasured", style = tokens.type.label)
                if (row.optBoolean("truncated")) Text("The snapshot is bounded; additional records were not measured in this read.", style = tokens.type.label)
                Text("Snapshot: ${row.ownerValue("snapshot_sha256")}", style = tokens.type.label)
                val refs = row.optJSONArray("evidence_refs")
                if (refs == null || refs.length() == 0) Text("No supporting evidence references recorded.", style = tokens.type.label)
                else (0 until refs.length()).forEach { Text("Evidence: ${refs.optString(it)}", style = tokens.type.label) }
            } } }
        }
    }
}

@Composable
internal fun LearningComparisonRows(body: JSONObject, name: String) {
    val tokens = LocalVanTokens.current
    body.optJSONArray(name).ownerRows().forEach { row -> VanPanel(dense = true) {
        Column {
            // All fields in this projection are typed, screened, source-bound read evidence.
            row.keys().asSequence().toList().forEach { field ->
                Text("${field.replace('_', ' ')}: ${row.ownerValue(field)}", style = tokens.type.label)
            }
            Text("This observed pattern or comparison does not declare your intent or authorize an action.", style = tokens.type.label)
        }
    } }
}
