package com.dial.van.memory

import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class LearningProducerTest {
    @Test fun `snapshot ready does not claim a live learning daemon`() {
        assertEquals("Current evidence snapshot computed", LearningProducer.parse(JSONObject().put("status", "READY")).ownerStatus)
    }
    @Test fun `no data partial and unknown preserve uncertainty`() {
        assertEquals("No qualifying observations", LearningProducer.parse(JSONObject().put("status", "NO_DATA")).ownerStatus)
        assertEquals("Some observations could not be compared", LearningProducer.parse(JSONObject().put("status", "PARTIAL")).ownerStatus)
        assertEquals("Current producer state is unknown", LearningProducer.parse(JSONObject().put("status", "RUNNING")).ownerStatus)
    }
    @Test fun `evidence never mints action authority`() {
        assertFailsWith<IllegalArgumentException> { LearningProducer.parse(JSONObject().put("execution_grant", true)) }
    }
}
