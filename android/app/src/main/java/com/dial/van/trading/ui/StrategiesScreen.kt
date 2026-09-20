package com.dial.van.trading.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.fragment.app.FragmentActivity
import com.dial.van.VanApplication
import com.dial.van.security.BiometricGate
import com.dial.van.security.OwnerApprovalKeyManager
import com.dial.van.trading.Loaded
import com.dial.van.trading.StrategyPromotionCandidate
import com.dial.van.trading.StrategyPromotionVerification
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

/**
 * Owner-only strategy authority surface.
 *
 * This screen never derives a certificate and never chooses a target state. Both
 * arrive from the policy-passing, current-lineage server candidate read model.
 * Promotion requires two independent biometric signatures from the same
 * hardware-backed owner key: the VATI owner-authority grant and the gateway A4
 * one-time challenge.
 */
@Composable
fun StrategiesScreen(
    env: ScreenEnv,
    padding: PaddingValues,
    app: VanApplication,
) {
    val context = LocalContext.current
    val gate = remember(context) { (context as? FragmentActivity)?.let(::BiometricGate) }
    val scope = rememberCoroutineScope()
    var tick by remember { mutableIntStateOf(0) }
    var candidates: Loaded<List<StrategyPromotionCandidate>> by remember {
        mutableStateOf(Loaded.Loading)
    }
    var busyStrategy by remember { mutableStateOf<String?>(null) }
    var status by remember { mutableStateOf("") }

    LaunchedEffect(tick) {
        candidates = Loaded.Loading
        candidates = env.repo.promotionCandidates()
    }

    fun promote(candidate: StrategyPromotionCandidate) {
        if (busyStrategy != null) return
        if (gate == null) {
            status = "Owner biometric approval is unavailable on this screen; nothing was sent."
            return
        }

        val prepared = runCatching {
            app.gatewayClient.prepareTradingPromotionAuthority(
                strategyId = candidate.strategyId,
                targetState = candidate.targetState,
                validationHash = candidate.validationHash,
            )
        }.getOrElse {
            status = "Owner authority key unavailable; nothing was sent."
            return
        }
        val authoritySignature = runCatching {
            app.gatewayClient.newA4ApprovalSignature()
        }.getOrElse {
            status = "Owner authority key unavailable; nothing was sent."
            return
        }

        busyStrategy = candidate.strategyId
        status = "Confirmation 1 of 2: sign the exact strategy authority grant."
        gate.requestA4CommandApproval(
            signature = authoritySignature,
            challenge = prepared.canonical,
            title = "Authorize strategy promotion",
            subtitle = candidate.strategyId + ": " + candidate.currentState + " → " + candidate.targetState,
            onApproved = { authoritySignatureBase64 ->
                val ownerToken = runCatching {
                    prepared.assembleFromSignatureBase64(authoritySignatureBase64)
                }.getOrElse {
                    busyStrategy = null
                    status = "Owner authority token could not be assembled; nothing was sent."
                    return@requestA4CommandApproval
                }
                val issuedAt = System.currentTimeMillis() / 1000L
                status = "Requesting certificate-bound A4 challenge…"
                scope.launch {
                    val challengeReply = runCatching {
                        app.gatewayClient.tradingPromotionChallenge(
                            strategyId = candidate.strategyId,
                            targetState = candidate.targetState,
                            ownerSignatureRef = ownerToken,
                            certificate = candidate.certificate,
                            evidenceRefs = candidate.evidenceRefs,
                            issuedAtUnix = issuedAt,
                        )
                    }.getOrElse {
                        busyStrategy = null
                        status = "Gateway challenge failed; no promotion was sent."
                        return@launch
                    }
                    val parsed = challengeReply.takeIf { it.first in 200..299 }?.let {
                        runCatching { Json.parseToJsonElement(it.second).jsonObject }.getOrNull()
                    }
                    val challenge = parsed?.get("approval_challenge")
                        ?.jsonPrimitive?.contentOrNull
                    val challengeId = parsed?.get("approval_challenge_id")
                        ?.jsonPrimitive?.contentOrNull
                    if (challenge.isNullOrBlank() || challengeId.isNullOrBlank()) {
                        busyStrategy = null
                        status = "Gateway did not issue a valid A4 challenge; no promotion was sent."
                        return@launch
                    }
                    val approvalSignature = runCatching {
                        app.gatewayClient.newA4ApprovalSignature()
                    }.getOrNull()
                    if (approvalSignature == null) {
                        busyStrategy = null
                        status = "Owner approval key unavailable; no promotion was sent."
                        return@launch
                    }

                    status = "Confirmation 2 of 2: approve this exact gateway state change."
                    gate.requestA4CommandApproval(
                        signature = approvalSignature,
                        challenge = challenge,
                        title = "Confirm strategy state change",
                        subtitle = "Promote " + candidate.strategyId + " to " + candidate.targetState,
                        onApproved = { approvalSignatureBase64 ->
                            scope.launch {
                                val proof = buildJsonObject {
                                    put("challenge_id", challengeId)
                                    put("signature_b64", approvalSignatureBase64)
                                    put("algorithm", OwnerApprovalKeyManager.PROOF_ALGORITHM)
                                }
                                val finalReply = runCatching {
                                    app.gatewayClient.tradingPromoteStrategy(
                                        strategyId = candidate.strategyId,
                                        targetState = candidate.targetState,
                                        ownerSignatureRef = ownerToken,
                                        certificate = candidate.certificate,
                                        evidenceRefs = candidate.evidenceRefs,
                                        approvalProof = proof,
                                        issuedAtUnix = issuedAt,
                                    )
                                }.getOrElse {
                                    busyStrategy = null
                                    status = "Promotion request failed; current strategy state was not claimed changed."
                                    return@launch
                                }
                                val body = runCatching {
                                    Json.parseToJsonElement(finalReply.second).jsonObject
                                }.getOrNull()
                                if (finalReply.first !in 200..299) {
                                    busyStrategy = null
                                    status = body?.get("detail")?.jsonPrimitive?.contentOrNull
                                        ?.let { "Promotion refused: " + it }
                                        ?: "Promotion refused by the trading authority."
                                    return@launch
                                }

                                // A 2xx transport answer is not enough to tell the owner that
                                // authority changed. Pin the response to the exact candidate and
                                // require a ledger event before asking the authoritative candidate
                                // read model whether the old parent certificate disappeared.
                                if (!StrategyPromotionVerification.receiptMatches(candidate, body)) {
                                    busyStrategy = null
                                    status = "Gateway returned success without a complete, candidate-bound ledger receipt; VAN is not claiming promotion."
                                    return@launch
                                }

                                status = "Promotion receipt received. Verifying authoritative strategy read-back…"
                                when (val refreshed = env.repo.promotionCandidates()) {
                                    is Loaded.Ready -> {
                                        candidates = refreshed
                                        val staleParentStillOffered =
                                            StrategyPromotionVerification.oldParentStillOffered(
                                                candidate, refreshed.value
                                            )
                                        busyStrategy = null
                                        if (staleParentStillOffered) {
                                            status = "Promotion receipt exists, but the old certificate is still offered by authoritative read-back. VAN is not claiming completion."
                                        } else {
                                            val restart = body?.get("requires_session_restart")
                                                ?.jsonPrimitive?.contentOrNull == "true"
                                            status = if (restart) {
                                                "Promotion verified in the ledger and read-back. Trading session restart is required before the new strategy state can be active."
                                            } else {
                                                "Promotion verified in the ledger and authoritative strategy read-back."
                                            }
                                        }
                                    }
                                    is Loaded.Unavailable -> {
                                        busyStrategy = null
                                        candidates = refreshed
                                        status = "Promotion receipt exists, but strategy read-back is unavailable. VAN is not claiming completion."
                                    }
                                    Loaded.Loading -> {
                                        busyStrategy = null
                                        candidates = refreshed
                                        status = "Promotion receipt exists, but strategy read-back is incomplete. VAN is not claiming completion."
                                    }
                                }
                            }
                        },
                        onDenied = { reason ->
                            busyStrategy = null
                            status = "Final owner approval was not granted: " + reason
                        },
                    )
                }
            },
            onDenied = { reason ->
                busyStrategy = null
                status = "Owner authority was not granted: " + reason
            },
        )
    }

    androidx.compose.foundation.lazy.LazyColumn(
        modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        contentPadding = PaddingValues(vertical = 10.dp),
    ) {
        item {
            Text(
                "Strategies",
                color = Color.White,
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold,
            )
            Text(
                "Only sealed validation certificates on the current capsule lineage appear here. VAN cannot promote itself.",
                color = TradingColors.muted,
                fontSize = 10.sp,
            )
        }
        if (status.isNotBlank()) {
            item {
                Text(
                    status,
                    color = if (
                        status.contains("refused", true) ||
                        status.contains("failed", true) ||
                        status.contains("not granted", true)
                    ) TradingColors.warning else TradingColors.text,
                    fontSize = 11.sp,
                )
            }
        }
        item {
            LoadedBox(candidates, empty = "No strategy is currently eligible for owner promotion.") { rows ->
                if (rows.isEmpty()) {
                    EmptyState(
                        "No strategy is currently eligible for owner promotion.",
                        "A strategy appears only after its exact current revision has a policy-passing validation certificate.",
                    )
                } else {
                    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        rows.forEach { candidate ->
                            StrategyCandidateCard(
                                candidate = candidate,
                                busy = busyStrategy != null,
                                onPromote = { promote(candidate) },
                            )
                        }
                    }
                }
            }
        }
        item {
            Text(
                "Promotion changes authority, not market analysis. The private key never leaves Android Keystore. " +
                    "Two biometric confirmations are deliberate: one signs the VATI owner grant and one signs the gateway's one-time A4 challenge.",
                color = TradingColors.muted,
                fontSize = 9.sp,
            )
        }
    }
}

@Composable
private fun StrategyCandidateCard(
    candidate: StrategyPromotionCandidate,
    busy: Boolean,
    onPromote: () -> Unit,
) {
    Column(
        modifier = Modifier.fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(Color.White.copy(alpha = 0.05f))
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(7.dp),
    ) {
        Row {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    candidate.strategyId,
                    color = Color.White,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    candidate.currentState + " → " + candidate.targetState,
                    color = TradingColors.accent,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                )
            }
            Chip("OWNER DECISION", 0xFFFFB300L)
        }

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            MetricTile(
                "DSR",
                candidate.dsrProbability?.let { String.format(java.util.Locale.ROOT, "%.3f", it) } ?: "—",
                Modifier.weight(1f),
            )
            MetricTile(
                "PBO",
                candidate.pboProbability?.let { String.format(java.util.Locale.ROOT, "%.3f", it) } ?: "—",
                Modifier.weight(1f),
            )
            MetricTile(
                "Edge floor R",
                candidate.expectancyLowerBoundR?.let {
                    String.format(java.util.Locale.ROOT, "%.3f", it)
                } ?: "—",
                Modifier.weight(1f),
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            MetricTile(
                "Profit factor",
                candidate.profitFactor?.let { String.format(java.util.Locale.ROOT, "%.2f", it) } ?: "—",
                Modifier.weight(1f),
            )
            MetricTile(
                "Max drawdown",
                candidate.maxDrawdown?.let { String.format(java.util.Locale.ROOT, "%.2f%%", it) } ?: "—",
                Modifier.weight(1f),
            )
        }

        Text(
            "validation " + candidate.validationHash.take(16) + "… · capsule " + candidate.capsuleHash.take(16) + "…",
            color = TradingColors.muted,
            fontSize = 9.sp,
            fontFamily = FontFamily.Monospace,
        )
        Text(
            "data " + candidate.dataManifestHash.take(18) + "… · " +
                candidate.evidenceRefs.size + " immutable evidence reference(s)",
            color = TradingColors.muted,
            fontSize = 9.sp,
            fontFamily = FontFamily.Monospace,
        )

        Spacer(Modifier.height(2.dp))
        Button(
            onClick = onPromote,
            enabled = !busy,
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(
                containerColor = TradingColors.accent.copy(alpha = 0.18f),
                contentColor = TradingColors.accent,
            ),
        ) {
            Text(
                "Review biometrics & promote to " + candidate.targetState,
                fontWeight = FontWeight.SemiBold,
            )
        }
    }
}
