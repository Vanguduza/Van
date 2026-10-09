package com.dial.van.memory

import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class OwnerMemoryDeclarationsTest {
    private fun receipt(id: String = "write-1") = JSONObject().put("status", "SAVED").put("execution_grant", false)
        .put("provenance", JSONObject().put("state", "OWNER_CONFIRMED").put("source", "OWNER_AUTHORED")
            .put("write_id", id).put("content_sha256", "a".repeat(64)))

    @Test fun vocabularyIsAnExactScopedDeclaration() {
        val definition = OwnerVocabularyDefinition.prepare("  My   TERM ", " meaning ", " operation ", listOf(" example "), projectId = " MyProject ")
        assertEquals("my term", definition.term)
        assertEquals("myproject", definition.projectId)
        definition.verifyEntry(definition.content())
        assertFailsWith<IllegalArgumentException> { definition.verifyEntry(definition.content().put("project_id", JSONObject.NULL)) }
        assertFailsWith<IllegalArgumentException> { definition.verifyEntry(definition.content().put("owner_meaning", "different")) }
    }
    @Test fun unboundedOrIncompleteVocabularyCannotBeSubmitted() {
        assertFailsWith<IllegalArgumentException> { OwnerVocabularyDefinition.prepare("", "meaning", "operation") }
        assertFailsWith<IllegalArgumentException> { OwnerVocabularyDefinition.prepare("term", " ", "operation") }
        assertFailsWith<IllegalArgumentException> { OwnerVocabularyDefinition.prepare("term", "meaning", "operation", List(17) { "example" }) }
    }
    @Test fun collaborationPreferenceDoesNotAcceptWildcardOrDiagnosticFields() {
        val preference = OwnerCollaborationPreference.prepare(" Google.Gmail ", " Ask before scheduling ")
        assertEquals(setOf("domain", "preferred_collaboration_pattern"), preference.content().keys().asSequence().toSet())
        preference.verifyEntry(preference.content().put("entry_id", "persisted-1"))
        assertFailsWith<IllegalArgumentException> { OwnerCollaborationPreference.prepare("*", "anything") }
        assertFailsWith<IllegalArgumentException> { preference.verifyEntry(preference.content().put("entry_id", "persisted-1").put("domain", "google.calendar")) }
    }
    @Test fun supersededUnconfirmedOrAuthorityBearingReadbacksNeverMeanSaved() {
        verifyOwnerMemoryReadback(receipt(), receipt())
        assertFailsWith<IllegalArgumentException> { verifyOwnerMemoryReadback(receipt(), receipt("later-write")) }
        assertFailsWith<IllegalArgumentException> { verifyOwnerMemoryReadback(receipt(), receipt().put("execution_grant", true)) }
        assertFailsWith<IllegalArgumentException> { verifyOwnerMemoryReadback(receipt(), receipt().put("status", "OBSERVED")) }
        assertFailsWith<IllegalArgumentException> { verifyOwnerMemoryReadback(receipt(), receipt().put("provenance", JSONObject(receipt().getJSONObject("provenance").toString()).put("content_sha256", "b".repeat(64)))) }
    }
}
