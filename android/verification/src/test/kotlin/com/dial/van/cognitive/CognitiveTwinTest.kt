package com.dial.van.cognitive

import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test

class CognitiveTwinTest {
    private fun body(classification: String = "PUBLIC") = """{"state":"AVAILABLE","projection":{"schema_version":1,"twin_id":"twin:van","twin_kind":"DEVELOPMENT","scope_id":"van","repository_sha":"abc","project_truth_hash":"truth","projection_revision":"revision","machine_facts_hash":"machine","generated_at":"2026-10-06T12:00:00Z","freshness":{"state":"CURRENT","expires_at":"2026-10-06T12:05:00Z"},"facts":[{"id":"repo","classification":"$classification","authority":"CANONICAL","evidence_refs":["git:abc"]}],"dot_synthesis":{"hypotheses":[{"id":"h1","classification":"INTERNAL_SANITIZED","authority":"DERIVED","hypothesis":"check","evidence_refs":["git:abc"]}]}}}"""
    @Test fun `separate source facts and hypotheses preserve revision and evidence`() {
        val twin = CognitiveTwin.parse(body())!!
        assertEquals("revision", twin.projectionRevision)
        assertEquals("CANONICAL", twin.facts.single().authority)
        assertEquals("check", twin.hypotheses.single().summary)
        assertEquals(listOf("git:abc"), twin.facts.single().evidenceRefs)
        assertFalse(twin.staleAt(twin.generatedAtMs + 1))
        assertTrue(twin.staleAt(twin.expiresAtMs))
        assertTrue(twin.staleAt(twin.generatedAtMs - 1))
    }
    @Test fun `restricted records and degraded sources never become a current twin`() {
        assertNull(CognitiveTwin.parse(body("RESTRICTED")))
        assertNull(CognitiveTwin.parse("""{"state":"DEGRADED","reason":"unconfigured"}"""))
    }
}
