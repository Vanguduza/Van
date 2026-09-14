package com.dial.van.visual

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Paths

class RiveContractTest {

    private val json = Json { ignoreUnknownKeys = true }

    @Test
    fun durableStatesMatchCanonicalContract() {
        val contract = loadContract()
        val states = contract["durable_states"]!!.jsonObject
        assertEquals(VanDurableState.entries.size, states.size)
        VanDurableState.entries.forEach { state ->
            val code = states[state.name]?.jsonPrimitive?.content?.toInt()
            assertEquals("Code mismatch for ${state.name}", state.code, code)
        }
    }

    @Test
    fun finiteActionsMatchCanonicalContract() {
        val contract = loadContract()
        val actions = contract["finite_actions"]!!.jsonObject
        assertEquals(VanFiniteAction.entries.size, actions.size)
        VanFiniteAction.entries.forEach { action ->
            val code = actions[action.name]?.jsonPrimitive?.content?.toInt()
            assertEquals("Code mismatch for ${action.name}", action.code, code)
        }
    }

    @Test
    fun triggersMatchCanonicalContract() {
        val contract = loadContract()
        val triggers = contract["triggers"]!!.toString()
        VanTrigger.entries.forEach { trigger ->
            assertTrue("Missing trigger ${trigger.wireName}", triggers.contains("\"${trigger.wireName}\""))
            assertNotNull(VanTrigger.fromWireName(trigger.wireName))
        }
        assertEquals(8, VanTrigger.entries.size)
    }

    @Test
    fun inputsMatchCanonicalContract() {
        val contract = loadContract()
        val inputs = contract["inputs"]!!.toString()
        VanInput.entries.forEach { input ->
            assertTrue("Missing input ${input.wireName}", inputs.contains("\"${input.wireName}\""))
        }
        assertEquals(9, VanInput.entries.size)
    }

    @Test
    fun bindingConstantsMatchArtboardAndStateMachine() {
        val contract = loadContract()
        assertEquals(RiveBindingContract.ARTBOARD, contract["artboard"]!!.jsonPrimitive.content)
        assertEquals(RiveBindingContract.STATE_MACHINE, contract["state_machine"]!!.jsonPrimitive.content)
    }

    @Test
    fun repoCanonicalContractMatchesTestFixture() {
        val repoFile = Paths.get("..", "visual-authority", "rive_contract.json").toFile().canonicalFile
        if (!repoFile.exists()) return
        val repo = json.parseToJsonElement(repoFile.readText()).jsonObject
        val fixture = loadContract()
        assertEquals(
            repo["durable_states"]!!.jsonObject.keys,
            fixture["durable_states"]!!.jsonObject.keys,
        )
        assertEquals(
            repo["finite_actions"]!!.jsonObject.keys,
            fixture["finite_actions"]!!.jsonObject.keys,
        )
    }

    private fun loadContract(): JsonObject {
        val classpath = javaClass.classLoader.getResource("rive_contract.json")
        requireNotNull(classpath) { "rive_contract.json missing from test resources" }
        return json.parseToJsonElement(classpath.readText()).jsonObject
    }
}
