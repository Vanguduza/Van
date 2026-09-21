package com.dial.van.session

import com.dial.van.events.EventStream
import com.dial.van.events.EventStreamState
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Rev 1.5 §20.1 — the socket's two shapes, read as the Gateway writes them.
 *
 * Every test here is a frame the Gateway actually sends, and the old `onMessage` would
 * have matched none of them.
 */
class SessionDownstreamTest {

    private fun frame(json: String) = SessionDownstream.parse(JSONObject(json))

    private val downstream = """
        {"direction":"DOWNSTREAM","event":{"seq":41,"event_type":"mission.completed",
         "payload":{"mission_id":"m_1"},"created_at_unix":1700000000}}
    """.trimIndent()

    private val acknowledgement = """
        {"accepted":true,"message_id":"msg_1","kind":"command.submit",
         "refusal":null,"admission":"ADMITTED","result":{"status":"accepted"}}
    """.trimIndent()

    @Test
    fun `a downstream event becomes a page the stream can apply`() {
        val parsed = frame(downstream)
        assertTrue(parsed is SessionDownstream.Frame.Event)
        val record = parsed.page.events.single()
        assertEquals(41L, record.seq)
        assertEquals("mission.completed", record.type)
        assertEquals(41L, parsed.page.nextCursor, "the cursor and the record must agree")
        assertTrue("m_1" in record.payloadJson)
    }

    @Test
    fun `the event is not mistaken for an acknowledgement`() {
        // The old code read `kind` off the top of the frame. A downstream event has no
        // `kind` and no `message_id`, so treating the two shapes as one would have
        // acknowledged a command nobody answered.
        val parsed = frame(downstream)
        assertTrue(parsed !is SessionDownstream.Frame.Acknowledgement)
    }

    @Test
    fun `an acknowledgement is recognised by message id rather than by kind`() {
        // The defect, precisely. The Gateway's answer carries the *envelope's* kind —
        // "command.submit" here — and the client compared it to "session.ack", so nothing
        // was ever taken out of flight.
        val parsed = frame(acknowledgement)
        assertTrue(parsed is SessionDownstream.Frame.Acknowledgement)
        assertEquals("msg_1", parsed.messageId)
        assertTrue(parsed.accepted)
        assertEquals(null, parsed.refusal)
    }

    @Test
    fun `a refusal is an answer, and carries its reason`() {
        // Not the same as silence: the command reached the Gateway and was declined, so
        // it is no longer in flight and a resume must not send it again.
        val parsed = frame(
            """{"accepted":false,"message_id":"msg_2","kind":"mission.cancel",
                "refusal":"mission_unknown"}""",
        )
        assertTrue(parsed is SessionDownstream.Frame.Acknowledgement)
        assertTrue(!parsed.accepted)
        assertEquals("mission_unknown", parsed.refusal)
    }

    @Test
    fun `an event with no sequence is refused rather than cursored at zero`() {
        // Taking zero would rewind the stream to the beginning on the next resume, and
        // the owner would watch every event they have already seen arrive again.
        val parsed = frame("""{"direction":"DOWNSTREAM","event":{"event_type":"x"}}""")
        assertTrue(parsed is SessionDownstream.Frame.Unrecognised)
    }

    @Test
    fun `a shape this build does not know is left alone`() {
        for (unknown in listOf(
            """{"kind":"session.epoch_changed","session_epoch":4}""",
            """{"direction":"DOWNSTREAM"}""",
            """{"hello":"world"}""",
        )) {
            assertTrue(frame(unknown) is SessionDownstream.Frame.Unrecognised, unknown)
        }
    }

    @Test
    fun `successive events advance the stream without repeating one`() {
        // The join with `EventStream`, which is the SHALL §20.1 states: the socket's
        // events go into the same reducer the REST floor uses, so a page that overlaps
        // what is held does not produce a duplicate row for the owner to read twice.
        var state = EventStreamState()
        for (seq in listOf(41L, 42L, 42L, 43L)) {
            val parsed = frame(
                """{"direction":"DOWNSTREAM","event":{"seq":$seq,"event_type":"e",
                    "payload":{},"created_at_unix":1}}""",
            )
            state = EventStream.applyPage(state, (parsed as SessionDownstream.Frame.Event).page)
        }
        assertEquals(listOf(43L, 42L, 41L), state.events.map { it.seq })
        assertEquals(43L, state.cursor)
    }
}
