package com.dial.van.session

import com.dial.van.events.EventPage
import com.dial.van.events.EventRecord
import org.json.JSONObject

/**
 * Rev 1.5 §§20.1, 20.4 — what arrives on the session socket, and what it means.
 *
 * The Gateway sends exactly two shapes down this socket and the client recognised
 * neither. `onMessage` read `seq` from the top of the frame — it is nested under `event` —
 * and switched on `kind` looking for `"session.ack"` and `"session.epoch_changed"`, which
 * the Gateway never sends. Its acknowledgement carries the *envelope's* kind, so the
 * comparison was against `"command.submit"` and friends.
 *
 * The consequences were all silent. The event cursor never advanced from the socket, so a
 * resume asked to replay from zero. Nothing was ever removed from `inFlight`, so every
 * command stayed pending until a resume reconciled it. And §20.1's "SHALL feed durable
 * downstream pages/events into the existing `EventStream.applyPage`" was not merely unmet
 * — the events were parsed into nothing and dropped.
 *
 * Both shapes are pinned against the Gateway's own construction sites by
 * `tests/contracts/test_session_socket_frames.py`, because this is the failure that keeps
 * happening here: two sides of a wire format, each internally consistent, and nothing that
 * runs both.
 */
object SessionDownstream {

    /** What a frame turned out to be. */
    sealed interface Frame {

        /**
         * One durable event, on its way to `EventStream`.
         *
         * A page of one, because the Gateway sends one event per frame. Building the page
         * here rather than at the call site keeps `nextCursor` and the record's `seq`
         * derived from the same value — the pair that, if they disagreed, would make the
         * stream skip or repeat.
         */
        data class Event(val page: EventPage) : Frame

        /**
         * The Gateway's answer to something this device sent.
         *
         * [accepted] false is an answer too, and a different one from silence: the
         * command reached the Gateway and was refused, so it is no longer in flight and
         * re-sending it on the next resume would be sending something already declined.
         */
        data class Acknowledgement(
            val messageId: String,
            val accepted: Boolean,
            val refusal: String?,
        ) : Frame

        /** Anything else, including a shape from a Gateway newer than this build. */
        data object Unrecognised : Frame
    }

    /**
     * The Gateway's word for a frame carrying an event rather than an answer.
     *
     * Compared rather than assumed: a frame with neither `direction` nor `message_id` is
     * from a protocol this build does not know, and guessing which of the two it is would
     * mean either dropping an event or acknowledging a command that was never answered.
     */
    const val DIRECTION_DOWNSTREAM: String = "DOWNSTREAM"

    fun parse(frame: JSONObject): Frame {
        val event = frame.optJSONObject("event")
        if (frame.optString("direction") == DIRECTION_DOWNSTREAM && event != null) {
            val seq = event.optLong("seq", -1L)
            // A record with no sequence cannot be merged or cursored, and taking zero
            // would rewind the stream to the beginning on the next resume.
            if (seq < 0) return Frame.Unrecognised
            val record = EventRecord(
                seq = seq,
                type = event.optString("event_type", "event"),
                // Kept as the bytes rather than parsed: `EventStream` holds it opaquely
                // and each screen reads the fields it knows, so a payload this build has
                // no model for still reaches the one that does.
                payloadJson = event.optJSONObject("payload")?.toString() ?: "{}",
                createdAtUnix = event.optLong("created_at_unix", 0L),
            )
            return Frame.Event(
                EventPage(events = listOf(record), nextCursor = seq, truncated = false),
            )
        }
        // The acknowledgement. Identified by `message_id` plus `accepted` rather than by
        // `kind`, which is the envelope's kind and says nothing about the frame.
        val messageId = frame.optString("message_id")
        if (messageId.isNotEmpty() && frame.has("accepted")) {
            return Frame.Acknowledgement(
                messageId = messageId,
                accepted = frame.optBoolean("accepted", false),
                refusal = frame.optString("refusal").takeIf { it.isNotEmpty() },
            )
        }
        return Frame.Unrecognised
    }
}
