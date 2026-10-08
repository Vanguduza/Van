package com.dial.van.memory

import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse

class DerivedMemoryRecordTest {
    private fun record() = JSONObject().put("store", "owner_cognitive_model").put("record_id", "mr_" + "a".repeat(64))
        .put("revision_sha256", "b".repeat(64)).put("content_screened", true).put("execution_grant", false)
    private fun plan() = record().put("action_class", "A4").put("command_text",
        "forget owner-derived memory record owner_cognitive_model mr_${"a".repeat(64)} ${"b".repeat(64)}")

    @Test fun `current exact plan is forwarded for biometric approval`() {
        assertEquals(plan().getString("command_text"), DerivedMemoryRecord.parse(record()).erasureCommand(plan()))
    }
    @Test fun `stale revision or other record cannot retarget an erasure`() {
        val selected = DerivedMemoryRecord.parse(record())
        assertFailsWith<IllegalArgumentException> { selected.erasureCommand(plan().put("revision_sha256", "c".repeat(64))) }
        assertFailsWith<IllegalArgumentException> { selected.erasureCommand(plan().put("record_id", "mr_" + "c".repeat(64))) }
        assertFalse(selected.matches(DerivedMemoryRecord.parse(record().put("revision_sha256", "c".repeat(64)))))
    }
    @Test fun `execution privilege and arbitrary command are refused`() {
        assertFailsWith<IllegalArgumentException> { DerivedMemoryRecord.parse(record().put("execution_grant", true)) }
        assertFailsWith<IllegalArgumentException> { DerivedMemoryRecord.parse(record()).erasureCommand(plan().put("command_text", "forget all owner-derived memory")) }
        assertFailsWith<IllegalArgumentException> { DerivedMemoryRecord.parse(record()).erasureCommand(plan().put("action_class", "A1")) }
    }
    @Test fun `unknown source is honestly unclassified`() {
        assertEquals("Source classification not established", DerivedMemoryRecord.parse(record().put("source_class", "OWNER_SIGNED")).sourceLabel)
        assertEquals("VAN's inference", DerivedMemoryRecord.parse(record().put("source_class", "INFERRED")).sourceLabel)
    }
}
