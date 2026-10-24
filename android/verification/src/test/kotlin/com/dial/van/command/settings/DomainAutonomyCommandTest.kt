package com.dial.van.command.settings

import org.json.JSONArray
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertNull

class DomainAutonomyCommandTest {
    private fun discovery() = JSONObject().put("typed_command_prefix", DomainAutonomyOptions.COMMAND_PREFIX)
        .put("known_domains", JSONArray(listOf("google.gmail", "owner.autonomy")))
        .put("supported_levels", JSONArray(listOf("S0", "S1", "S2", "S3", "S4")))

    @Test fun preservesOwnerChoiceForTheSealedCommand() {
        val options = assertNotNull(DomainAutonomyOptions.parse(discovery()))
        val command = options.commandText("google.gmail", "S0")
        val params = JSONObject(command.removePrefix(DomainAutonomyOptions.COMMAND_PREFIX))
        assertEquals("google.gmail", params.getString("domain"))
        assertEquals("S0", params.getString("level"))
        assertEquals(setOf("domain", "level"), params.keys().asSequence().toSet())
    }

    @Test fun rejectsAnUnlistedDomainAndUnsupportedEscalation() {
        val options = assertNotNull(DomainAutonomyOptions.parse(discovery()))
        assertFailsWith<IllegalArgumentException> { options.commandText("global", "S0") }
        assertFailsWith<IllegalArgumentException> { options.commandText("google.gmail", "S5") }
    }

    @Test fun unavailableDiscoveryCannotCreateOwnerChoices() {
        assertNull(DomainAutonomyOptions.parse(JSONObject()))
        assertNull(DomainAutonomyOptions.parse(discovery().put("typed_command_prefix", "approve anything ")))
        assertNull(DomainAutonomyOptions.parse(discovery().put("supported_levels", JSONArray(listOf("S0", "S5")))))
        assertNull(DomainAutonomyOptions.parse(discovery().put("known_domains", JSONArray(listOf("google.gmail", "google.gmail")))))
        assertNull(DomainAutonomyOptions.parse(discovery().put("known_domains", JSONArray(listOf("google.gmail\n")))))
        assertNull(DomainAutonomyOptions.parse(discovery().put("known_domains", JSONArray(listOf("*")))))
        assertNull(DomainAutonomyOptions.parse(discovery().put("known_domains", JSONArray(listOf("google/gmail")))))
    }
}
