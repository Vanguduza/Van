package com.dial.van.command.nav

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull

class ConcreteRouteRestorationTest {
    @Test fun `process recreation retains the exact selected mission and project`() {
        for ((template, name, id, expected) in listOf(
            listOf(VanRoute.WORK_MISSION_TEMPLATE, "missionId", "mission-42", "work/missions/mission-42"),
            listOf(VanRoute.PROJECT_DETAIL_TEMPLATE, "projectId", "project-17", "projects/project-17"),
            listOf(VanRoute.PROJECT_RATIONALE_TEMPLATE, "projectId", "project-17", "projects/project-17/rationale"),
        )) {
            val persisted = VanRoute.concreteRoute(template, mapOf(name to id))
            assertEquals(expected, persisted)
            assertEquals(expected, VanNavModel.restore(persisted))
            assertFalse(persisted!!.contains('{'))
        }
    }

    @Test fun `development arguments survive without becoming unresolved templates`() {
        val saved = VanRoute.concreteRoute(VanRoute.WORK_DEV_TASKS, mapOf("projectId" to "dial-v2", "view" to "BLOCKED"))
        assertEquals("work/dev/dial-v2/tasks?view=BLOCKED", saved)
        assertEquals(saved, VanNavModel.restore(saved))
        assertEquals("work/dev", VanRoute.concreteRoute(VanRoute.WORK_DEV, emptyMap()))
        assertEquals("work/dev?project=dial-v2", VanRoute.concreteRoute(VanRoute.WORK_DEV, mapOf("project" to "dial-v2")))
    }

    @Test fun `reserved characters stay one encoded identifier and missing arguments cannot be persisted`() {
        val saved = VanRoute.concreteRoute(VanRoute.WORK_MISSION_TEMPLATE, mapOf("missionId" to "owner/id #1"))
        assertEquals("work/missions/owner%2Fid%20%231", saved)
        assertEquals(VanRoute.missionRoute("owner/id #1"), saved)
        assertEquals(saved, VanNavModel.restore(saved))
        assertNull(VanRoute.concreteRoute(VanRoute.WORK_MISSION_TEMPLATE, emptyMap()))
        assertEquals(VanRoute.HOME, VanNavModel.restore(VanRoute.WORK_MISSION_TEMPLATE))
        assertNull(VanRoute.concreteRoute("unregistered/{id}", mapOf("id" to "1")))
        assertNull(VanRoute.concreteRoute(VanRoute.WORK_DEV_PLAN, mapOf("projectId" to "tasks")))
    }
}
