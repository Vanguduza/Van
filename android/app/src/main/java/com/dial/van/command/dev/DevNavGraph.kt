package com.dial.van.command.dev

import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.dial.van.VanApplication
import com.dial.van.command.nav.VanRoute

/** How a development screen moves: to a concrete route `VanRoute` built. */
fun interface DevNavigator {
    fun open(route: String)
}

/**
 * VAN-DEV-003 — the Development Control Centre's `composable` registrations, one per
 * [VanRoute.DEV_TEMPLATES] entry, in that order, inside the Command Centre's one `NavHost`
 * (`CommandCentreActivity`). Kept in its own file so the shell stays a shell; every route here
 * is a child of Work ([VanRoute.PARENTS]), never a new destination.
 */
fun NavGraphBuilder.dialDevGraph(app: VanApplication, nav: NavHostController) {
    val navigator = DevNavigator { route -> nav.navigate(route) }

    composable(
        VanRoute.WORK_DEV,
        arguments = listOf(navArgument("project") { type = NavType.StringType; nullable = true; defaultValue = null }),
    ) { entry -> DevHomeRoute(app, entry.arguments?.getString("project"), navigator) }

    composable(VanRoute.WORK_DEV_TASK, arguments = listOf(stringArg("taskId"))) { entry ->
        DevTaskDetailRoute(app, entry.arguments?.getString("taskId").orEmpty(), navigator)
    }
    composable(VanRoute.WORK_DEV_WORKSPACES) { DevWorkspacesRoute(app, navigator) }
    composable(VanRoute.WORK_DEV_WORKSPACE, arguments = listOf(stringArg("workspaceId"))) { entry ->
        DevWorkspaceDetailRoute(app, entry.arguments?.getString("workspaceId").orEmpty(), navigator)
    }
    composable(VanRoute.WORK_DEV_EVIDENCE, arguments = listOf(stringArg("evidenceRef"))) { entry ->
        DevEvidenceRoute(app, entry.arguments?.getString("evidenceRef").orEmpty(), navigator)
    }
    composable(VanRoute.WORK_DEV_PLAN, arguments = listOf(stringArg("projectId"))) { entry ->
        DevPlanRoute(app, entry.arguments?.getString("projectId").orEmpty(), navigator)
    }
    composable(
        VanRoute.WORK_DEV_TASKS,
        arguments = listOf(
            stringArg("projectId"),
            navArgument("view") { type = NavType.StringType; nullable = true; defaultValue = null },
        ),
    ) { entry ->
        DevTasksRoute(app, entry.arguments?.getString("projectId").orEmpty(), entry.arguments?.getString("view"), navigator)
    }
    composable(VanRoute.WORK_DEV_GRAPH, arguments = listOf(stringArg("projectId"))) { entry ->
        DevGraphRoute(app, entry.arguments?.getString("projectId").orEmpty(), navigator)
    }
    composable(VanRoute.WORK_DEV_AGENTS) { DevAgentsRoute(app, navigator) }
    composable(VanRoute.WORK_DEV_RESEARCH) { DevResearchRoute(app, navigator) }
    composable(VanRoute.WORK_DEV_DESIGN) { DevDesignRoute(app, navigator) }
    composable(VanRoute.WORK_DEV_CI) { DevCiRoute(app, navigator) }
    composable(VanRoute.WORK_DEV_SECURITY) { DevSecurityRoute(app, navigator) }
    composable(VanRoute.WORK_DEV_REVIEWS) { DevReviewsRoute(app, navigator) }
    composable(VanRoute.WORK_DEV_MEMORY) { DevMemoryRoute(app, navigator) }
}

private fun stringArg(name: String) = navArgument(name) { type = NavType.StringType }
