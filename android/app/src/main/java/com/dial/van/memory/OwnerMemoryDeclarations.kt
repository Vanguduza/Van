package com.dial.van.memory

import java.util.Locale
import org.json.JSONArray
import org.json.JSONObject

data class OwnerVocabularyDefinition(
    val term: String, val ownerMeaning: String, val operationalization: String,
    val examples: List<String>, val antiExamples: List<String>, val projectId: String?,
) {
    fun content(): JSONObject = JSONObject().put("term", term).put("owner_meaning", ownerMeaning)
        .put("system_operationalization", operationalization).put("examples", JSONArray(examples))
        .put("anti_examples", JSONArray(antiExamples)).put("project_id", projectId ?: JSONObject.NULL)

    fun verifyEntry(entry: JSONObject) {
        for (key in listOf("term", "owner_meaning", "system_operationalization")) {
            require(entry.getString(key) == content().getString(key)) { "Vocabulary readback differs from your declaration." }
        }
        require((if (entry.isNull("project_id")) null else entry.getString("project_id")) == projectId)
        for ((key, expected) in listOf("examples" to examples, "anti_examples" to antiExamples)) {
            val rows = entry.getJSONArray(key)
            require((0 until rows.length()).map { rows.get(it) as? String } == expected)
        }
    }

    companion object {
        fun prepare(term: String, meaning: String, operationalization: String,
                    examples: List<String> = emptyList(), antiExamples: List<String> = emptyList(),
                    projectId: String? = null): OwnerVocabularyDefinition {
            val canonicalTerm = term.trim().split(Regex("\\s+")).joinToString(" ").lowercase(Locale.ROOT)
            require(canonicalTerm.length in 1..128 && canonicalTerm.none { it.isISOControl() }) { "Enter a term of up to 128 characters." }
            fun text(value: String, max: Int): String = value.trim().also {
                require(it.length in 1..max && '\u0000' !in it) { "Enter text of up to $max characters." }
            }
            fun examples(values: List<String>): List<String> {
                require(values.size <= 16) { "Supply at most 16 examples." }
                return values.map { text(it, 512) }.distinct()
            }
            val project = projectId?.trim()?.lowercase(Locale.ROOT)?.also { require(it.matches(Regex("[a-z][a-z0-9_-]{0,63}"))) }
            return OwnerVocabularyDefinition(canonicalTerm, text(meaning, 4000), text(operationalization, 4000),
                examples(examples), examples(antiExamples), project)
        }
    }
}

data class OwnerCollaborationPreference(val domain: String, val pattern: String) {
    fun content() = JSONObject().put("domain", domain).put("preferred_collaboration_pattern", pattern)
    fun verifyEntry(entry: JSONObject) {
        require(entry.getString("domain") == domain && entry.getString("preferred_collaboration_pattern") == pattern)
        require(entry.getString("entry_id").isNotBlank())
    }
    companion object {
        fun prepare(domain: String, pattern: String): OwnerCollaborationPreference {
            val canonical = domain.trim().lowercase(Locale.ROOT)
            require(canonical.length in 1..128 && canonical.matches(Regex("[a-z][a-z0-9_-]*(?:\\.[a-z][a-z0-9_-]*){0,7}"))) { "Enter a specific domain, such as google.gmail." }
            val value = pattern.trim()
            require(value.length in 1..4000 && '\u0000' !in value) { "Enter a collaboration preference of up to 4000 characters." }
            return OwnerCollaborationPreference(canonical, value)
        }
    }
}

/** A lost or superseded write never becomes a successful owner confirmation. */
fun verifyOwnerMemoryReadback(saved: JSONObject, observed: JSONObject) {
    for (body in listOf(saved, observed)) {
        require(body.getString("status") == "SAVED" && body.get("execution_grant") == false)
        val provenance = body.getJSONObject("provenance")
        require(provenance.getString("state") == "OWNER_CONFIRMED" && provenance.getString("source") == "OWNER_AUTHORED")
        require(provenance.getString("write_id").isNotBlank())
        require(provenance.getString("content_sha256").matches(Regex("[0-9a-f]{64}")))
    }
    val expected = saved.getJSONObject("provenance")
    val actual = observed.getJSONObject("provenance")
    require(expected.getString("write_id") == actual.getString("write_id") &&
        expected.getString("content_sha256") == actual.getString("content_sha256")) { "This declaration changed before readback. Refresh before trying again." }
}
