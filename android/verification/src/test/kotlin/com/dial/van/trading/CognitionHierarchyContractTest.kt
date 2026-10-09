package com.dial.van.trading

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class CognitionHierarchyContractTest {
    private fun parse(authority: String) = CognitionSnapshot.parse("""{"authority":$authority}""")!!
    @Test fun `existing native legacy hierarchy contract remains readable`() {
        assertEquals(listOf("fable-5.1", "gpt-6-astra", "claude-opus-5", "gpt-5.6-sol"),
            parse("""{"model_hierarchy":["fable-5.1","gpt-6-astra","claude-opus-5","gpt-5.6-sol"]}""").modelHierarchy)
    }
    @Test fun `supported hierarchy is authoritative when both keys are present`() {
        assertEquals(listOf("supported"), parse("""{"supported_model_hierarchy":["supported"],"model_hierarchy":["legacy"]}""").modelHierarchy)
        assertEquals(emptyList<String>(), parse("""{"supported_model_hierarchy":[],"model_hierarchy":["legacy"]}""").modelHierarchy)
    }
}
