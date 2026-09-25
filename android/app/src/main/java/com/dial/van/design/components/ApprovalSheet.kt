package com.dial.van.design.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics
import kotlinx.coroutines.launch

/**
 * DNA §3: "ApprovalSheet (biometric prompt inline, action digest)." A `ModalBottomSheet`
 * hosting a caller-supplied approval action — this composable does **not** call any
 * `BiometricGate` itself (that authority-sensitive call is the owning screen's, per the task
 * boundary: `com.dial.van.design` never reaches into `overlay/`/`voice`/`gateway`/security
 * code). [onApprove] is that call, handed in as a `suspend () -> Result<Unit>`.
 *
 * [actionDigest] is the plain-language summary of exactly what will happen — DNA's "action
 * digest" — shown above the approve control every time, never collapsed behind a details
 * toggle: an approval sheet's whole job is to be readable before the thumbprint, not after.
 *
 * [confirmation] is an optional slot under the digest for a typed confirmation or a required
 * reason (VAN-DEVCC-R1 §3.3/§5: revoking a DIAL task is confirmed by typing its id; rejecting a
 * decision carries the owner's reason). While [approveEnabled] is false the approve control is
 * disabled — the caller decides when what was typed is enough. Both default to the original
 * behaviour, so existing call sites are unchanged.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ApprovalSheet(
    title: String,
    actionDigest: String,
    onApprove: suspend () -> Result<Unit>,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier,
    onApproved: (() -> Unit)? = null,
    approveLabel: String = "Approve",
    cancelLabel: String = "Cancel",
    approveEnabled: Boolean = true,
    confirmation: (@Composable () -> Unit)? = null,
) {
    val tokens = LocalVanTokens.current
    val sheetState = rememberModalBottomSheetState()
    val scope = rememberCoroutineScope()
    var inFlight by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        modifier = modifier,
        sheetState = sheetState,
        containerColor = tokens.color.surfaceAcrylic,
        contentColor = tokens.color.textPrimary,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = tokens.space.space5, vertical = tokens.space.space3),
            verticalArrangement = Arrangement.spacedBy(tokens.space.space3),
        ) {
            Text(title, style = tokens.type.title, color = tokens.color.textPrimary)
            Text(actionDigest, style = tokens.type.body, color = tokens.color.textSecondary)
            confirmation?.invoke()
            if (errorMessage != null) {
                Text(
                    errorMessage.orEmpty(),
                    style = tokens.type.label,
                    color = tokens.color.forStatusRole(StatusSemantics.ROLE_CRITICAL),
                )
            }
            Column(
                modifier = Modifier.fillMaxWidth().padding(bottom = tokens.space.space4),
                verticalArrangement = Arrangement.spacedBy(tokens.space.space2),
            ) {
                Button(
                    onClick = {
                        if (inFlight) return@Button
                        inFlight = true
                        errorMessage = null
                        scope.launch {
                            val result = onApprove()
                            inFlight = false
                            result.fold(
                                onSuccess = {
                                    onApproved?.invoke()
                                    onDismiss()
                                },
                                onFailure = { error ->
                                    errorMessage = error.message ?: "Approval failed."
                                },
                            )
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !inFlight && approveEnabled,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = tokens.color.accentCyan,
                        contentColor = tokens.color.textInverse,
                    ),
                ) {
                    if (inFlight) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(16.dp),
                            color = tokens.color.textInverse,
                            strokeWidth = 2.dp,
                        )
                    } else {
                        Text(approveLabel, style = tokens.type.headline)
                    }
                }
                TextButton(
                    onClick = onDismiss,
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !inFlight,
                ) {
                    Text(cancelLabel, style = tokens.type.body, color = tokens.color.textSecondary)
                }
            }
        }
    }
}
