package com.dial.van.instrumentation

import androidx.test.ext.junit.runners.AndroidJUnit4
import com.dial.van.command.nav.VanRoute
import com.dial.van.command.owner.OwnerServicePresentation
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith

/** Exercise template handling on Android's ICU-backed regex implementation. */
@RunWith(AndroidJUnit4::class)
class TemplateRuntimeTest {
    @Test fun concreteRoutesEncodeArgumentsAndRejectMissingValues() {
        assertEquals("work/missions/owner%2Fid%20%231", VanRoute.concreteRoute(
            VanRoute.WORK_MISSION_TEMPLATE, mapOf("missionId" to "owner/id #1"),
        ))
        assertEquals("work/dev/dial-v2/tasks?view=BLOCKED", VanRoute.concreteRoute(
            VanRoute.WORK_DEV_TASKS, mapOf("projectId" to "dial-v2", "view" to "BLOCKED"),
        ))
        assertNull(VanRoute.concreteRoute(VanRoute.WORK_MISSION_TEMPLATE, emptyMap()))
        assertNull(VanRoute.concreteRoute("unregistered/{id}", mapOf("id" to "1")))
    }

    @Test fun ownerCommandsRejectUnresolvedFieldsAndLineBreaks() {
        fun control(template: String, vararg fields: String) = JSONObject()
            .put("available", true).put("submission_path", "/v1/commands")
            .put("command_template", template).put("required_fields", JSONArray(fields.toList()))

        assertEquals("research local train times", OwnerServicePresentation.command(
            control("research {query}", "query"), mapOf("query" to " local train times "),
        ))
        assertNull(OwnerServicePresentation.command(
            control("create note {title} {content}", "title"), mapOf("title" to "Inbox"),
        ))
        assertNull(OwnerServicePresentation.command(
            control("research {query}", "query"), mapOf("query" to "trains\nforget memory"),
        ))
    }
}
