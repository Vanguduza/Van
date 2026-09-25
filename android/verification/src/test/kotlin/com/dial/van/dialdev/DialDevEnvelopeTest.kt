package com.dial.van.dialdev

import com.dial.van.design.DegradedCatalog
import com.dial.van.design.ScreenState
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** `VAN-DEVCC-R1` §3.1 / §3.4 — the envelope and its mapping onto DNA §5's seven states. */
class DialDevEnvelopeTest {

    private fun body(freshness: Long? = 1_800, degraded: String = "[]", data: String = """{"tasks":[{"task_id":"T1","state":"RUNNING"}]}""") =
        """
        {"projection_revision":"sha256:abc","observed_at":"2026-09-23T16:40:00Z",
         "sources":{"stage_plan_revision":12,"orca_runtime_id":"orca-1"},
         ${freshness?.let { "\"freshness_ms\":$it," } ?: ""}
         "degraded":$degraded,"data":$data}
        """.trimIndent()

    private fun loaded(b: String, at: Long = 1_000L) = DialDevFetch.Loaded(DialDevEnvelope.parse(b)!!, at)

    private fun reduce(fetch: DialDevFetch, last: DialDevFetch.Loaded? = null, now: Long = 1_000L, threshold: Long = DialDevFreshness.DEFAULT_STALE_MS) =
        DialDevScreenReducer.reduce(
            fetch, last, now, threshold,
            parse = { env -> DialDevParse.tasks(env.data, env.observedAt) },
            isEmpty = { it.isEmpty() },
            emptySentence = "Nothing here.",
        )

    @Test
    fun `the envelope parses revision, sources, freshness and degraded rows`() {
        val env = DialDevEnvelope.parse(body(degraded = """[{"subsystem":"OPENVIKING","effect":"semantic recall unavailable","still_works":["tasks","workspaces","evidence"]}]"""))!!
        assertEquals("sha256:abc", env.projectionRevision)
        assertEquals("12", env.sources["stage_plan_revision"])
        assertEquals(1_800L, env.freshnessMs)
        val row = env.degraded.single().toRow()
        assertEquals("openviking", row.subsystem)
        assertEquals("OpenViking recall: semantic recall unavailable. Still works: tasks, workspaces, evidence.", row.sentence)
    }

    @Test
    fun `a body without a projection revision is not a projection`() {
        assertNull(DialDevEnvelope.parse("""{"data":{}}"""))
        assertNull(DialDevEnvelope.parse("not json"))
    }

    @Test
    fun `a missing freshness is unknown, and unknown reads as stale`() {
        val state = reduce(loaded(body(freshness = null)))
        assertIs<ScreenState.Stale<*>>(state)
    }

    @Test
    fun `fresh data with no degraded subsystems is CONTENT`() {
        assertIs<ScreenState.Content<*>>(reduce(loaded(body())))
    }

    @Test
    fun `a non-empty degraded list is DEGRADED with the surviving data`() {
        val state = reduce(loaded(body(degraded = """[{"subsystem":"orca","effect":"daemon down","still_works":["tasks"]}]""")))
        val degraded = assertIs<ScreenState.Degraded<List<DevTaskRow>>>(state)
        assertEquals("T1", degraded.data!!.single().taskId)
        assertEquals("orca", degraded.rows.single().subsystem)
    }

    @Test
    fun `a bare degraded key still becomes a row with the catalogue's sentence`() {
        val state = assertIs<ScreenState.Degraded<*>>(reduce(loaded(body(degraded = """["vekl"]"""))))
        assertEquals(DegradedCatalog.sentenceFor("vekl"), state.rows.single().sentence)
    }

    @Test
    fun `freshness over the 30 s default is STALE, and stale outranks degraded`() {
        val state = reduce(loaded(body(freshness = 30_001, degraded = """["orca"]""")))
        assertEquals(30_001L, assertIs<ScreenState.Stale<*>>(state).ageMs)
        assertIs<ScreenState.Content<*>>(reduce(loaded(body(freshness = 30_000))))
    }

    @Test
    fun `workspaces go stale at 10 s`() {
        val b = loaded(body(freshness = 12_000))
        assertIs<ScreenState.Content<*>>(reduce(b, threshold = DialDevFreshness.DEFAULT_STALE_MS))
        assertIs<ScreenState.Stale<*>>(reduce(b, threshold = DialDevFreshness.WORKSPACES_STALE_MS))
    }

    @Test
    fun `age keeps growing on the phone after the projection was served`() {
        val b = loaded(body(freshness = 5_000), at = 1_000L)
        val state = reduce(b, now = 1_000L + 26_000L)
        assertEquals(31_000L, assertIs<ScreenState.Stale<*>>(state).ageMs)
    }

    @Test
    fun `503 dial_dev_unavailable with nothing on screen is a retryable ERROR`() {
        val state = reduce(DialDevFetch.Failed(503, """{"detail":{"error":"dial_dev_unavailable"}}""", null))
        assertTrue(assertIs<ScreenState.Error>(state).canRetry)
        assertEquals("dial_dev_unavailable", DialDevScreenReducer.errorCode("""{"detail":{"error":"dial_dev_unavailable"}}"""))
    }

    @Test
    fun `an unauthorised phone is an ERROR it cannot retry its way out of`() {
        assertFalse(assertIs<ScreenState.Error>(reduce(DialDevFetch.Failed(403, "{}", null))).canRetry)
    }

    @Test
    fun `offline with nothing on screen is OFFLINE with no owner work queued`() {
        assertEquals(0, assertIs<ScreenState.Offline>(reduce(DialDevFetch.Offline)).queuedCount)
    }

    @Test
    fun `offline or failed with a last-known projection keeps it on screen as STALE`() {
        val last = loaded(body(freshness = 1_000), at = 1_000L)
        assertIs<ScreenState.Stale<*>>(reduce(DialDevFetch.Offline, last, now = 2_000L))
        assertIs<ScreenState.Stale<*>>(reduce(DialDevFetch.Failed(503, "{}", null), last, now = 2_000L))
    }

    @Test
    fun `a refetch in flight keeps the last projection judged by its own age`() {
        val last = loaded(body(freshness = 1_000), at = 1_000L)
        assertIs<ScreenState.Content<*>>(reduce(DialDevFetch.Loading, last, now = 2_000L))
        assertIs<ScreenState.Loading>(reduce(DialDevFetch.Loading))
    }

    @Test
    fun `an empty task list is EMPTY, unless DIAL says it is degraded`() {
        assertIs<ScreenState.Empty>(reduce(loaded(body(data = """{"tasks":[]}"""))))
        assertIs<ScreenState.Degraded<*>>(reduce(loaded(body(data = """{"tasks":[]}""", degraded = """["dial_dev"]"""))))
    }

    @Test
    fun `DegradedCatalog names every DIAL development subsystem`() {
        for (key in listOf("dial_dev", "orca", "spmrf", "openviking", "vekl", "artemis", "zuul", "hermes_dial")) {
            val sentence = DegradedCatalog.sentenceFor(key)
            assertFalse(sentence.endsWith(" is degraded."), "$key fell through to the generic sentence: $sentence")
        }
    }
}
