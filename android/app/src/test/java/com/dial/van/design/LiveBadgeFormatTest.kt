package com.dial.van.design

import org.junit.Assert.assertEquals
import org.junit.Test

class LiveBadgeFormatTest {

    @Test
    fun `zero age is 00 colon 00`() {
        assertEquals("00:00", LiveBadgeFormat.hhmm(0L))
    }

    @Test
    fun `exactly one hour rolls minutes over rather than reading 00 colon 60`() {
        assertEquals("01:00", LiveBadgeFormat.hhmm(3_600_000L))
    }

    @Test
    fun `negative ages clamp to zero`() {
        assertEquals("00:00", LiveBadgeFormat.hhmm(-5_000L))
    }
}
