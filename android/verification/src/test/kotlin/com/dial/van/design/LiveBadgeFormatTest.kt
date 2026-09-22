package com.dial.van.design

import kotlin.test.Test
import kotlin.test.assertEquals

class LiveBadgeFormatTest {

    @Test
    fun `zero age is 00 colon 00`() {
        assertEquals("00:00", LiveBadgeFormat.hhmm(0L))
    }

    @Test
    fun `under a minute floors to 00 colon 00`() {
        assertEquals("00:00", LiveBadgeFormat.hhmm(59_999L))
    }

    @Test
    fun `exactly one minute`() {
        assertEquals("00:01", LiveBadgeFormat.hhmm(60_000L))
    }

    @Test
    fun `exactly one hour rolls minutes over rather than reading 00 colon 60`() {
        assertEquals("01:00", LiveBadgeFormat.hhmm(3_600_000L))
    }

    @Test
    fun `an hour and a half`() {
        assertEquals("01:30", LiveBadgeFormat.hhmm(5_400_000L))
    }

    @Test
    fun `negative ages are clamped to zero rather than producing a negative string`() {
        assertEquals("00:00", LiveBadgeFormat.hhmm(-1_000L))
    }

    @Test
    fun `hours beyond 24 keep counting rather than wrapping to a day`() {
        assertEquals("30:00", LiveBadgeFormat.hhmm(30L * 3_600_000L))
    }
}
