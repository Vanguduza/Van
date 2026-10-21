package com.dial.van.memory

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class MemoryEffectReceiptTest {
    @Test fun `observed erasure waits for authoritative command completion`() {
        val receipt = MemoryEffectReceipt.observed("memory.erase", "VERIFIED_SUCCESS", mapOf("owner_facts" to 0L), setOf("owner_facts"), "audit:receipt-1", emptyList())
        assertNotNull(receipt)
        assertFalse(receipt.mayRender(false))
        assertTrue(receipt.mayRender(true))
    }

    @Test fun `unverified mismatched and malformed effect receipts cannot claim erasure`() {
        assertNull(MemoryEffectReceipt.observed("memory.erase", "SUBMITTED", mapOf("owner_facts" to 4L), setOf("owner_facts"), "audit:1", emptyList()))
        assertNull(MemoryEffectReceipt.observed("memory.remember", "VERIFIED_SUCCESS", mapOf("owner_facts" to 4L), setOf("owner_facts"), "audit:1", emptyList()))
        assertNull(MemoryEffectReceipt.observed("memory.erase", "VERIFIED_SUCCESS", mapOf("owner_facts" to 4L), setOf("intent_nodes"), "audit:1", emptyList()))
        assertNull(MemoryEffectReceipt.observed("memory.erase", "VERIFIED_SUCCESS", mapOf("owner_facts" to -1L), setOf("owner_facts"), "audit:1", emptyList()))
        assertNull(MemoryEffectReceipt.observed("memory.erase", "VERIFIED_SUCCESS", mapOf("credentials" to 4L), setOf("credentials"), "audit:1", emptyList()))
    }
}
