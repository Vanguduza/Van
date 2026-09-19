package com.dial.van.status

import org.json.JSONArray
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * P3-AND-003 — attention() and briefing() were declared and called by nothing.
 *
 * The gateway maintained an attention queue and built a briefing; the app had methods to
 * fetch both and no surface that did. Two capabilities that existed end to end apart from
 * the last ten lines.
 */
class OwnerOverviewTest {

    private fun attention(vararg rows: Triple<String, String, String>): JSONArray {
        val array = JSONArray()
        rows.forEach { (id, title, severity) ->
            array.put(
                JSONObject()
                    .put("id", id)
                    .put("title", title)
                    .put("severity", severity)
                    .put("source", "van"),
            )
        }
        return array
    }

    @Test
    fun `an empty queue and an unreachable gateway never say the same thing`() {
        // The rule that shapes the whole summariser. "Nothing is waiting for you" is a
        // claim about the world, and VAN may only make it when it has looked.
        val empty = OwnerOverview.summarize(JSONArray(), null)
        val unreachable = OwnerOverview.summarize(null, null, error = "Gateway unreachable")
        assertTrue(empty.loaded)
        assertFalse(unreachable.loaded)
        assertEquals("Nothing is waiting for you", empty.headline)
        assertTrue(unreachable.headline.contains("could not reach"))
        assertTrue(empty.headline != unreachable.headline)
    }

    @Test
    fun `blockers are counted and informational items are not`() {
        val summary = OwnerOverview.summarize(
            attention(
                Triple("a", "Approve the trading account", "BLOCKER"),
                Triple("b", "Deploy finished", "INFO"),
                Triple("c", "Margin pressure", "URGENT"),
            ),
            null,
        )
        assertEquals(2, summary.waitingCount)
        assertEquals("2 things are waiting for you", summary.headline)
    }

    @Test
    fun `one waiting item reads as one, not as a number`() {
        val summary = OwnerOverview.summarize(
            attention(Triple("a", "Approve the trading account", "BLOCKER")), null,
        )
        assertEquals("One thing is waiting for you", summary.headline)
    }

    @Test
    fun `informational items alone do not read as something waiting`() {
        val summary = OwnerOverview.summarize(
            attention(Triple("b", "Deploy finished", "INFO")), null,
        )
        assertEquals(0, summary.waitingCount)
        assertTrue(summary.headline.startsWith("Nothing needs you"))
    }

    @Test
    fun `blockers sort above information and the order is stable`() {
        // A list that reshuffles on every poll is a list nobody trusts.
        val rows = attention(
            Triple("a", "Zebra info", "INFO"),
            Triple("b", "Alpha blocker", "BLOCKER"),
            Triple("c", "Beta blocker", "URGENT"),
        )
        val first = OwnerOverview.summarize(rows, null).items.map { it.id }
        val second = OwnerOverview.summarize(rows, null).items.map { it.id }
        assertEquals(first, second)
        assertEquals(listOf("b", "c", "a"), first)
    }

    @Test
    fun `a malformed row does not take the whole queue down`() {
        val array = JSONArray().put("not an object").put(
            JSONObject().put("id", "a").put("title", "Real").put("severity", "BLOCKER"),
        )
        val summary = OwnerOverview.summarize(array, null)
        assertEquals(1, summary.items.size)
        assertEquals("Real", summary.items.first().title)
    }

    @Test
    fun `an item with no title is labelled rather than shown blank`() {
        val array = JSONArray().put(JSONObject().put("id", "a").put("severity", "INFO"))
        assertEquals("Untitled", OwnerOverview.summarize(array, null).items.first().title)
    }

    @Test
    fun `a briefing with nothing to say contributes no line`() {
        // A card that always has text trains the owner to stop reading it.
        assertNull(OwnerOverview.briefingLine(null))
        assertNull(OwnerOverview.briefingLine(JSONObject()))
        assertNull(OwnerOverview.briefingLine(JSONObject().put("headline", "   ")))
        assertEquals(
            "Two meetings and one deadline",
            OwnerOverview.briefingLine(JSONObject().put("headline", "Two meetings and one deadline")),
        )
    }

    @Test
    fun `the briefing falls back to its summary when it has no headline`() {
        assertEquals(
            "Quiet morning",
            OwnerOverview.briefingLine(JSONObject().put("summary", "Quiet morning")),
        )
    }

    @Test
    fun `a failure carries its reason to the owner`() {
        val summary = OwnerOverview.summarize(null, null, error = "gateway_http_503")
        assertEquals("gateway_http_503", summary.error)
        assertTrue(summary.items.isEmpty())
        assertNull(summary.briefingLine)
    }
}
