package com.dial.van.command.nav

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.test.assertFalse

class VanNavModelTest {

    @Test
    fun `restore falls back to home for null, blank or unknown routes`() {
        assertEquals(VanRoute.HOME, VanNavModel.restore(null))
        assertEquals(VanRoute.HOME, VanNavModel.restore(""))
        assertEquals(VanRoute.HOME, VanNavModel.restore("not-a-route"))
    }

    @Test
    fun `restore keeps a known concrete route, including one with an argument`() {
        assertEquals(VanRoute.ATTENTION, VanNavModel.restore(VanRoute.ATTENTION))
        assertEquals("work/missions/m-42", VanNavModel.restore("work/missions/m-42"))
        assertEquals("projects/acme", VanNavModel.restore("projects/acme"))
    }

    @Test
    fun `startDestination resolves a plain launch to home`() {
        assertEquals(VanRoute.HOME, VanNavModel.startDestination(null))
        assertEquals(VanRoute.HOME, VanNavModel.startDestination("  "))
    }

    @Test
    fun `startDestination honours a new-style route already`() {
        assertEquals(VanRoute.TRADING, VanNavModel.startDestination(VanRoute.TRADING))
    }

    @Test
    fun `startDestination maps every legacy CommandModule id somewhere known`() {
        val legacyIds = listOf(
            "overview", "chat", "tasks", "missions", "activity", "decisions", "projects",
            "browser_automation", "browser_tasks", "browser_escalations", "browser_sessions",
            "browser_policy", "systems", "connections", "notifications", "speech", "settings",
        )
        for (id in legacyIds) {
            val resolved = VanNavModel.startDestination(id)
            assertTrue(VanRoute.isKnown(resolved), "legacy id '$id' resolved to unknown route '$resolved'")
        }
    }

    @Test
    fun `startDestination falls back to home for an unrecognised extra`() {
        assertEquals(VanRoute.HOME, VanNavModel.startDestination("something-else-entirely"))
    }

    @Test
    fun `deepLink parses every primary and more destination`() {
        for (route in VanRoute.PRIMARY + VanRoute.MORE) {
            assertEquals(route, VanNavModel.deepLink("van://$route"))
        }
    }

    @Test
    fun `deepLink parses a concrete argument route`() {
        assertEquals("projects/acme-42", VanNavModel.deepLink("van://projects/acme-42"))
        assertEquals("work/missions/m-1", VanNavModel.deepLink("van://work/missions/m-1"))
    }

    @Test
    fun `deepLink bare scheme resolves to home`() {
        assertEquals(VanRoute.HOME, VanNavModel.deepLink("van://"))
    }

    @Test
    fun `deepLink rejects a foreign scheme or unknown path`() {
        assertNull(VanNavModel.deepLink("https://home"))
        assertNull(VanNavModel.deepLink("van://not-a-real-route"))
    }

    @Test
    fun `deepLink ignores a trailing query string`() {
        assertEquals(VanRoute.ATTENTION, VanNavModel.deepLink("van://attention?source=notification"))
    }

    @Test
    fun `back returns each route's DNA-declared parent, and null at home`() {
        assertNull(VanNavModel.back(VanRoute.HOME))
        assertEquals(VanRoute.HOME, VanNavModel.back(VanRoute.ATTENTION))
        assertEquals(VanRoute.HOME, VanNavModel.back(VanRoute.WORK))
        assertEquals(VanRoute.WORK, VanNavModel.back(VanRoute.WORK_BROWSER))
        assertEquals(VanRoute.WORK_BROWSER, VanNavModel.back(VanRoute.WORK_BROWSER_TASKS))
        assertEquals(VanRoute.WORK, VanNavModel.back("work/missions/m-1"))
        assertEquals(VanRoute.PROJECTS, VanNavModel.back("projects/acme"))
        assertEquals(VanRoute.HOME, VanNavModel.back(VanRoute.SETTINGS))
    }

    @Test
    fun `back on an unknown route is null rather than a guess`() {
        assertNull(VanNavModel.back("nonsense"))
    }

    @Test
    fun `isPrimary is true only for the five adaptive-nav destinations`() {
        assertTrue(VanNavModel.isPrimary(VanRoute.HOME))
        assertTrue(VanNavModel.isPrimary(VanRoute.ATTENTION))
        assertTrue(VanNavModel.isPrimary(VanRoute.WORK))
        assertTrue(VanNavModel.isPrimary(VanRoute.TRADING))
        assertTrue(VanNavModel.isPrimary(VanRoute.MEMORY))
        assertFalse(VanNavModel.isPrimary(VanRoute.SETTINGS))
        assertFalse(VanNavModel.isPrimary(VanRoute.CONNECTED))
        assertFalse(VanNavModel.isPrimary("projects/acme"))
    }

    @Test
    fun `every route template has exactly one parent chain up to home`() {
        for (template in VanRoute.ALL_TEMPLATES) {
            if (template == VanRoute.HOME) continue
            var current: String? = template
            var hops = 0
            while (current != null && current != VanRoute.HOME) {
                current = VanRoute.PARENTS[current]
                hops += 1
                assertTrue(hops < 10, "possible cycle starting at $template")
            }
            assertEquals(VanRoute.HOME, current, "$template does not resolve up to home")
        }
    }

    @Test
    fun `missionRoute and projectRoute build routes VanRoute recognises`() {
        val mission = VanRoute.missionRoute("m 1")
        assertTrue(VanRoute.isKnown(mission))
        val project = VanRoute.projectRoute("acme")
        assertTrue(VanRoute.isKnown(project))
    }

    // ---- VAN-DEV-003: the DIAL Development Control Centre (VAN-DEVCC-R1 §2.1) ----------

    private val devRoutes = listOf(
        "work/dev" to VanRoute.WORK_DEV,
        "work/dev?project=dial-development-system" to VanRoute.WORK_DEV,
        "work/dev/dial-development-system/plan" to VanRoute.WORK_DEV_PLAN,
        "work/dev/dial-development-system/tasks" to VanRoute.WORK_DEV_TASKS,
        "work/dev/dial-development-system/tasks?view=blocked" to VanRoute.WORK_DEV_TASKS,
        "work/dev/dial-development-system/graph" to VanRoute.WORK_DEV_GRAPH,
        "work/dev/tasks/HOT-DU-021" to VanRoute.WORK_DEV_TASK,
        "work/dev/agents" to VanRoute.WORK_DEV_AGENTS,
        "work/dev/workspaces" to VanRoute.WORK_DEV_WORKSPACES,
        "work/dev/workspaces/ws-7" to VanRoute.WORK_DEV_WORKSPACE,
        "work/dev/research" to VanRoute.WORK_DEV_RESEARCH,
        "work/dev/design" to VanRoute.WORK_DEV_DESIGN,
        "work/dev/ci" to VanRoute.WORK_DEV_CI,
        "work/dev/security" to VanRoute.WORK_DEV_SECURITY,
        "work/dev/reviews" to VanRoute.WORK_DEV_REVIEWS,
        "work/dev/memory" to VanRoute.WORK_DEV_MEMORY,
        "work/dev/evidence/EV-42" to VanRoute.WORK_DEV_EVIDENCE,
    )

    @Test
    fun `every section 2_1 development route resolves to its own template`() {
        for ((concrete, template) in devRoutes) {
            assertEquals(template, VanRoute.templateFor(concrete), concrete)
        }
    }

    @Test
    fun `the development templates are exactly the fifteen section 2_1 names, all registered`() {
        assertEquals(
            setOf(
                "work/dev?project={project}", "work/dev/{projectId}/plan", "work/dev/{projectId}/tasks?view={view}",
                "work/dev/{projectId}/graph", "work/dev/tasks/{taskId}", "work/dev/agents", "work/dev/workspaces",
                "work/dev/workspaces/{workspaceId}", "work/dev/research", "work/dev/design", "work/dev/ci",
                "work/dev/security", "work/dev/reviews", "work/dev/memory", "work/dev/evidence/{evidenceRef}",
            ),
            VanRoute.DEV_TEMPLATES.toSet(),
        )
        assertEquals(VanRoute.DEV_TEMPLATES.size, VanRoute.DEV_TEMPLATES.toSet().size)
        assertTrue(VanRoute.ALL_TEMPLATES.containsAll(VanRoute.DEV_TEMPLATES))
    }

    @Test
    fun `every work-dev route's parent is Work, and none is a new destination`() {
        for (template in VanRoute.DEV_TEMPLATES) {
            assertEquals(VanRoute.WORK, VanRoute.PARENTS[template], template)
            assertFalse(template in VanRoute.PRIMARY || template in VanRoute.MORE, template)
        }
        for ((concrete, _) in devRoutes) {
            assertEquals(VanRoute.WORK, VanNavModel.back(concrete), concrete)
            assertFalse(VanNavModel.isPrimary(concrete), concrete)
        }
        assertEquals(8, (VanRoute.PRIMARY + VanRoute.MORE).size, "DNA §4: eight destinations, still eight")
    }

    @Test
    fun `development deep links use the van scheme and keep only declared queries`() {
        assertEquals("work/dev/tasks/HOT-DU-021", VanNavModel.deepLink("van://work/dev/tasks/HOT-DU-021"))
        assertEquals("work/dev/p1/tasks?view=blocked", VanNavModel.deepLink("van://work/dev/p1/tasks?view=blocked&utm=x"))
        assertEquals("work/dev?project=p1", VanNavModel.deepLink("van://work/dev?project=p1"))
        assertEquals("work/dev/agents", VanNavModel.deepLink("van://work/dev/agents?view=blocked"))
        assertEquals("work/dev/p1/tasks", VanNavModel.deepLink("van://work/dev/p1/tasks?view="))
        assertNull(VanNavModel.deepLink("van://work/dev/nonsense/deeper/still"))
        for ((concrete, _) in devRoutes) {
            val link = VanRoute.toDeepLink(concrete)
            assertTrue(link.startsWith("van://work/dev"), link)
            assertEquals(VanRoute.templateFor(concrete), VanNavModel.deepLink(link)?.let(VanRoute::templateFor), link)
        }
    }

    @Test
    fun `a literal segment beats a placeholder when two development templates both fit`() {
        // A task literally named "plan" is a task, not a project called "tasks".
        assertEquals(VanRoute.WORK_DEV_TASK, VanRoute.templateFor("work/dev/tasks/plan"))
        assertEquals(VanRoute.WORK_DEV_WORKSPACE, VanRoute.templateFor("work/dev/workspaces/graph"))
        assertEquals(VanRoute.WORK_DEV_EVIDENCE, VanRoute.templateFor("work/dev/evidence/plan"))
        assertEquals(VanRoute.WORK_DEV_PLAN, VanRoute.templateFor("work/dev/p1/plan"))
    }

    @Test
    fun `the development route builders produce routes VanRoute recognises`() {
        val built = listOf(
            VanRoute.devHomeRoute(), VanRoute.devHomeRoute("dial development"), VanRoute.devPlanRoute("p/1"),
            VanRoute.devTasksRoute("p1"), VanRoute.devTasksRoute("p1", "needs_me"), VanRoute.devGraphRoute("p1"),
            VanRoute.devTaskRoute("HOT-DU-021"), VanRoute.devWorkspaceRoute("ws 1"), VanRoute.devEvidenceRoute("EV/1"),
        )
        for (route in built) assertTrue(VanRoute.isKnown(route), route)
        assertEquals("work/dev?project=dial%20development", VanRoute.devHomeRoute("dial development"))
        assertEquals("work/dev/p%2F1/plan", VanRoute.devPlanRoute("p/1"))
        assertEquals("work/dev/p1/tasks?view=needs_me", VanRoute.devTasksRoute("p1", "needs_me"))
    }

    @Test
    fun `restore keeps a development route across process death`() {
        assertEquals("work/dev/tasks/HOT-DU-021", VanNavModel.restore("work/dev/tasks/HOT-DU-021"))
        assertEquals("work/dev", VanNavModel.restore("work/dev"))
    }
}
