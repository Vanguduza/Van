package com.dial.van.memory

import org.json.JSONArray
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class MemoryModelsTest {

    private fun factRow(
        factId: String = "fact_1",
        subject: String = "OWNER",
        predicate: String = "coffee_order",
        value: Any = "flat white",
        authority: String = "CANONICAL_OWNER",
        sourceTrust: String = "OWNER_EXPLICIT",
        scope: String = "global",
        validFromMs: Long = 1_000L,
        validUntilMs: Long? = null,
        confidencePermille: Int = 1000,
    ): JSONObject {
        val row = JSONObject()
            .put("fact_id", factId)
            .put("subject", subject)
            .put("predicate", predicate)
            .put("value", value)
            .put("authority", authority)
            .put("source_trust", sourceTrust)
            .put("source_ref", "owner-device:d1")
            .put("scope", scope)
            .put("valid_from_ms", validFromMs)
            .put("observed_at_ms", validFromMs)
            .put("confidence_permille", confidencePermille)
        row.put("valid_until_ms", validUntilMs ?: JSONObject.NULL)
        return row
    }

    private fun exportWith(vararg rows: JSONObject): JSONObject {
        val records = JSONArray()
        rows.forEach { records.put(it) }
        val ownerFacts = JSONObject().put("records", records)
        val stores = JSONObject().put("owner_facts", ownerFacts)
        return JSONObject().put("stores", stores)
    }

    // ---- parseExportFacts ---------------------------------------------------------------

    @Test
    fun `parses fields off an owner_facts export row`() {
        val export = exportWith(factRow())
        val facts = MemoryReadModel.parseExportFacts(export)
        assertEquals(1, facts.size)
        val fact = facts.single()
        assertEquals("fact_1", fact.factId)
        assertEquals("OWNER", fact.subject)
        assertEquals("coffee_order", fact.predicate)
        assertEquals("flat white", fact.value)
        assertEquals("CANONICAL_OWNER", fact.authority)
        assertEquals(null, fact.validUntilMs)
        assertEquals(100, fact.confidencePercent)
    }

    @Test
    fun `numeric and boolean values stringify without a trailing decimal`() {
        val export = exportWith(
            factRow(factId = "f_int", predicate = "age", value = 41),
            factRow(factId = "f_bool", predicate = "night_owl", value = true),
        )
        val facts = MemoryReadModel.parseExportFacts(export).associateBy { it.factId }
        assertEquals("41", facts.getValue("f_int").value)
        assertEquals("true", facts.getValue("f_bool").value)
    }

    @Test
    fun `a row with no fact_id is dropped rather than crashing`() {
        val badRow = JSONObject().put("subject", "OWNER").put("predicate", "x").put("value", "y")
        val export = exportWith(badRow)
        assertTrue(MemoryReadModel.parseExportFacts(export).isEmpty())
    }

    @Test
    fun `missing stores block parses as no facts, not a crash`() {
        assertTrue(MemoryReadModel.parseExportFacts(JSONObject()).isEmpty())
    }

    // ---- grouping -------------------------------------------------------------------------

    @Test
    fun `factsByScope excludes decisions and expired facts, groups the rest by scope`() {
        val now = 10_000L
        val facts = listOf(
            factRow(factId = "f1", predicate = "coffee_order", scope = "global"),
            factRow(factId = "f2", predicate = "decision", value = "ship on Friday", scope = "decisions"),
            factRow(factId = "f3", predicate = "branch", scope = "project:van", validUntilMs = 5_000L),
        ).let { MemoryReadModel.parseExportFacts(exportWith(*it.toTypedArray())) }

        val grouped = MemoryReadModel.factsByScope(facts, now)
        assertEquals(setOf("global"), grouped.keys)
        assertEquals(listOf("coffee_order"), grouped.getValue("global").map { it.predicate })
    }

    @Test
    fun `decisions returns only the predicate decision, newest first`() {
        val now = 10_000L
        val facts = listOf(
            factRow(factId = "d1", predicate = "decision", value = "ship on Friday", scope = "decisions", validFromMs = 1_000L),
            factRow(factId = "d2", predicate = "decision", value = "use Postgres", scope = "decisions", validFromMs = 5_000L),
            factRow(factId = "p1", predicate = "coffee_order", scope = "global"),
        ).let { MemoryReadModel.parseExportFacts(exportWith(*it.toTypedArray())) }

        val decisions = MemoryReadModel.decisions(facts, now)
        assertEquals(listOf("d2", "d1"), decisions.map { it.factId })
    }

    @Test
    fun `preferences excludes both decision and generic statement predicates`() {
        val now = 10_000L
        val facts = listOf(
            factRow(factId = "p1", predicate = "coffee_order", scope = "global"),
            factRow(factId = "s1", predicate = "statement", value = "likes long runs", scope = "global"),
            factRow(factId = "d1", predicate = "decision", value = "ship Friday", scope = "decisions"),
        ).let { MemoryReadModel.parseExportFacts(exportWith(*it.toTypedArray())) }

        val preferences = MemoryReadModel.preferences(facts, now)
        assertEquals(listOf("p1"), preferences.map { it.factId })
    }

    @Test
    fun `recentChanges sorts newest first and respects the limit`() {
        val facts = (1..5).map { i ->
            factRow(factId = "f$i", predicate = "p$i", validFromMs = i * 1000L)
        }.let { MemoryReadModel.parseExportFacts(exportWith(*it.toTypedArray())) }

        val recent = MemoryReadModel.recentChanges(facts, limit = 3)
        assertEquals(listOf("f5", "f4", "f3"), recent.map { it.factId })
    }

    // ---- freshness --------------------------------------------------------------------

    @Test
    fun `freshness classifies no-expiry, current, expiring-soon and expired`() {
        val now = 100_000L
        val noExpiry = factRow(factId = "a", validUntilMs = null)
        val farOut = factRow(factId = "b", validUntilMs = now + 30L * 24 * 60 * 60 * 1000L)
        val soon = factRow(factId = "c", validUntilMs = now + 1L * 24 * 60 * 60 * 1000L)
        val expired = factRow(factId = "d", validUntilMs = now - 1_000L)

        val export = exportWith(noExpiry, farOut, soon, expired)
        val facts = MemoryReadModel.parseExportFacts(export).associateBy { it.factId }

        assertEquals(FactFreshness.NO_EXPIRY, MemoryFreshness.classify(facts.getValue("a"), now))
        assertEquals(FactFreshness.CURRENT, MemoryFreshness.classify(facts.getValue("b"), now))
        assertEquals(FactFreshness.EXPIRING_SOON, MemoryFreshness.classify(facts.getValue("c"), now))
        assertEquals(FactFreshness.EXPIRED, MemoryFreshness.classify(facts.getValue("d"), now))
    }

    @Test
    fun `staleOrExpiringFacts surfaces shaken authorities and near-expiry facts still in force`() {
        val now = 100_000L
        val shaken = factRow(factId = "shaken", authority = "CONFLICTED")
        val expiringSoon = factRow(factId = "soon", validUntilMs = now + 60_000L)
        val healthy = factRow(factId = "healthy", validUntilMs = now + 30L * 24 * 60 * 60 * 1000L)
        val alreadyExpired = factRow(factId = "expired", validUntilMs = now - 1L)

        val facts = MemoryReadModel.parseExportFacts(exportWith(shaken, expiringSoon, healthy, alreadyExpired))
        val ids = MemoryReadModel.staleOrExpiringFacts(facts, now).map { it.factId }.toSet()

        assertTrue("shaken" in ids)
        assertTrue("soon" in ids)
        assertFalse("healthy" in ids)
        // Already expired is no longer "currently held" at all — it belongs to history, not
        // to "things VAN is unsure about right now".
        assertFalse("expired" in ids)
    }

    // ---- conflicts --------------------------------------------------------------------

    @Test
    fun `parseConflicts pairs both sides of blocking and inferred_only conflicts`() {
        fun side(factId: String, value: String, authority: String) = JSONObject()
            .put("fact_id", factId).put("value", value).put("authority", authority)
            .put("source_trust", "OWNER_EXPLICIT").put("observed_at_ms", 1000L)

        val blocking = JSONArray().put(
            JSONObject().put("subject", "OWNER").put("predicate", "timezone").put("scope", "global")
                .put("sides", JSONArray().put(side("f1", "SAST", "CANONICAL_OWNER")).put(side("f2", "UTC", "CANONICAL_OWNER"))),
        )
        val conflicts = JSONObject().put("blocking", blocking).put("inferred_only", JSONArray()).put("total", 1)

        val parsed = MemoryReadModel.parseConflicts(conflicts)
        assertEquals(1, parsed.size)
        val conflict = parsed.single()
        assertTrue(conflict.blocking)
        assertEquals("timezone", conflict.predicate)
        assertEquals(listOf("SAST", "UTC"), conflict.sides.map { it.value })
    }

    // ---- provenance tiers -----------------------------------------------------------------

    @Test
    fun `provenance tiers map every authority to one of the four DNA chips`() {
        assertEquals(ProvenanceTier.CANONICAL_OWNER, ProvenanceTiers.forAuthority("CANONICAL_OWNER"))
        assertEquals(ProvenanceTier.PROJECT_TRUTH, ProvenanceTiers.forAuthority("PROJECT_TRUTH"))
        assertEquals(ProvenanceTier.VERIFIED, ProvenanceTiers.forAuthority("VERIFIED_LIVE_STATE"))
        assertEquals(ProvenanceTier.VERIFIED, ProvenanceTiers.forAuthority("CONFIRMED_LEARNED"))
        assertEquals(ProvenanceTier.INFERRED, ProvenanceTiers.forAuthority("INFERRED"))
        assertEquals(ProvenanceTier.INFERRED, ProvenanceTiers.forAuthority("STALE"))
        assertEquals(ProvenanceTier.INFERRED, ProvenanceTiers.forAuthority("SOME_FUTURE_TIER"))
    }
}
