package com.dial.van.browser

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class BrowserKeyMappingTest {
    @Test fun `Android enter delete and navigation become actual CDP virtual keys`() {
        assertEquals(BrowserKeyMapping.Key(13, 0, "\r"), BrowserKeyMapping.key(66, 10, 0, true))
        assertEquals(BrowserKeyMapping.Key(8, 0, ""), BrowserKeyMapping.key(67, 0, 0, true))
        assertEquals(37, BrowserKeyMapping.key(21, 0, 0, true)!!.virtualKey)
        assertEquals(46, BrowserKeyMapping.key(112, 0, 0, true)!!.virtualKey)
    }
    @Test fun `printable hardware key carries text only on key down and never treats Unicode as modifiers`() {
        assertEquals(BrowserKeyMapping.Key(65, 0, "a"), BrowserKeyMapping.key(29, 97, 0, true))
        assertEquals(BrowserKeyMapping.Key(65, 0, ""), BrowserKeyMapping.key(29, 97, 0, false))
        assertEquals(BrowserKeyMapping.Key(65, 8, "A"), BrowserKeyMapping.key(29, 65, 1, true))
    }
    @Test fun `Ctrl Meta Alt and Shift shortcuts carry canonical modifier bits without inserting their letter`() {
        assertEquals(BrowserKeyMapping.Key(65, 2, ""), BrowserKeyMapping.key(29, 97, 0x1000, true))
        assertEquals(BrowserKeyMapping.Key(65, 15, ""), BrowserKeyMapping.key(29, 97, 0x7000 or 0x70000 or 0xc1 or 0x32, true))
    }
    @Test fun `Unicode supplementary characters remain intact and unknown nonprintable keys are refused`() {
        assertEquals("🙂", BrowserKeyMapping.key(0, 0x1f642, 0, true)!!.text)
        assertNull(BrowserKeyMapping.key(0, 0xd800, 0, true))
        assertNull(BrowserKeyMapping.key(0, 0, 0, true))
    }
}
