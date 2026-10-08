package com.dial.van.command.attention

import org.json.JSONArray
import org.json.JSONObject

data class OwnerDecisionChoice(val id: String, val label: String, val description: String)

/** A decision records an owner answer. It never confers execution authority. */
data class OwnerDecision(
    val id: String,
    val revision: Int,
    val title: String,
    val body: String,
    val status: String,
    val expiresAtUnix: Long?,
    val choices: List<OwnerDecisionChoice>,
    val evidence: List<JSONObject>,
    val missionId: String?,
    val selectedChoice: String?,
    val answerNote: String,
    val resolutionRequestId: String?,
) {
    fun answerable(nowUnix: Long): Boolean = status == "OPEN" && revision >= 1 &&
        choices.isNotEmpty() && (expiresAtUnix == null || nowUnix < expiresAtUnix)

    fun prepareAnswer(choiceId: String, note: String, requestId: String, nowUnix: Long): JSONObject {
        require(answerable(nowUnix)) { "This decision is no longer open. Refresh its current state." }
        require(choices.any { it.id == choiceId }) { "Choose one of the current decision options." }
        require(note.length <= 2_000) { "Your reason must be at most 2000 characters." }
        require(requestId.matches(Regex("[A-Za-z0-9_-]{16,128}"))) { "Decision request identity is invalid." }
        return JSONObject().put("choice_id", choiceId).put("expected_revision", revision)
            .put("request_id", requestId).put("note", note.trim())
    }

    fun confirms(request: JSONObject): Boolean = selectedChoice == request.optString("choice_id") &&
        resolutionRequestId == request.optString("request_id") && answerNote == request.optString("note") &&
        status in setOf("APPROVED", "REJECTED", "ANSWERED")

    companion object {
        fun parse(value: JSONObject): OwnerDecision {
            val id = value.optString("id").ifBlank { value.optString("decision_id") }
            require(id.isNotBlank()) { "Decision identity is missing." }
            val choices = value.optJSONArray("choices").rows().map {
                OwnerDecisionChoice(it.getString("id"), it.getString("label"), it.optString("description"))
            }
            require(choices.map { it.id }.distinct().size == choices.size && choices.all { it.id.isNotBlank() }) {
                "Decision choices are ambiguous."
            }
            require(!value.optBoolean("grants_action_authority")) { "A decision cannot grant action authority." }
            return OwnerDecision(id, value.optInt("revision"), value.optString("title", "Decision"),
                value.optString("body"), value.optString("status"),
                if (value.isNull("expires_at_unix")) null else value.optLong("expires_at_unix"), choices,
                value.optJSONArray("evidence").rows(), value.nullableString("mission_id"),
                value.nullableString("selected_choice_id"), value.optString("answer_note"),
                value.nullableString("resolution_request_id"))
        }
    }
}

private fun JSONArray?.rows(): List<JSONObject> = if (this == null) emptyList() else
    (0 until length()).mapNotNull { optJSONObject(it) }
private fun JSONObject.nullableString(name: String): String? = if (isNull(name)) null else
    optString(name).takeIf { it.isNotBlank() }
