package com.dial.van.command.jev

import com.dial.van.gateway.VanGatewayClient

class JevRepository(private val gateway: VanGatewayClient) {
    suspend fun snapshot(): JevServiceSnapshot =
        JevJson.snapshot(gateway.jevStatus(), gateway.jevHealth())

    suspend fun outcomes(projectId: String, limit: Int = 100): List<JevOutcome> =
        JevJson.outcomes(gateway.jevActivity(projectId, limit))

    suspend fun contribution(projectId: String, moduleId: String): JevContribution =
        JevJson.contribution(moduleId, gateway.jevContribution(projectId, moduleId))
}
