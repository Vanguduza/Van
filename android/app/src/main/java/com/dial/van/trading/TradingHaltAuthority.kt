package com.dial.van.trading

import com.dial.van.security.OwnerApprovalKeyManager
import com.dial.van.security.OwnerAuthorityToken

/**
 * GAP-F-005 owner halt — the client half of the authority `TradingHaltExecutor`
 * (`backend/van_gateway/command/local_executors.py`) requires.
 *
 * The gateway executes the typed command `"halt trading"` (action class A4) only when the
 * dispatched command's `client_context["owner_halt_authority_ref"]` carries a valid
 * [OwnerAuthorityToken] bound to act `"owner-halt"`, subject `"van-trading-core"` — a
 * *second*, independently-signed credential alongside the ordinary A4 approval proof
 * (`TradingHaltExecutor`'s own doc comment). [prepare] mints the canonical statement for
 * that token; the caller signs it under `BIOMETRIC_STRONG` (`BiometricGate
 * .requestA4CommandApproval`) and finishes with
 * `OwnerAuthorityToken.Prepared.assembleFromSignatureBase64` to get the ref string, exactly
 * as `TradingCommandCentreActivity`'s existing `prepareTradingPromotionAuthority` does for
 * strategy promotion.
 *
 * `OwnerApprovalKeyManager` is instantiated locally rather than reached through
 * `VanGatewayClient.approvalKeys` (that field is `private`, by design — the gateway client
 * does not hand out the raw key manager). Both instances address the same fixed Android
 * Keystore alias (`OwnerApprovalKeyManager.KEY_ALIAS`), so they sign with the same
 * hardware-backed owner key; a new instance here is not a second key, it is a second handle
 * to the one key.
 *
 * The ref reaches the gateway as `client_context[owner_halt_authority_ref]`:
 * `VanCommandController.submitText(clientContext = …)` → `VanOwnerCommand.clientContext` →
 * `VanGatewayClient.dispatchCommand`/`buildCommandBody` → the request body's `client_context`
 * (`backend/van_gateway/models.py` `CommandRequest.client_context`, read by
 * `TradingHaltExecutor`). The same map rides the A4 re-dispatch after the owner signs the
 * gateway's challenge, so both credentials arrive on the command that executes.
 */
object TradingHaltAuthority {
    /** The exact typed-command text `local_executors.LOCAL_EXECUTORS["trading.halt"]` resolves. */
    const val HALT_COMMAND_TEXT = "halt trading"
    const val ACTION_CLASS = "A4"
    const val AUTHORITY_ACT = "owner-halt"
    const val AUTHORITY_SUBJECT = "van-trading-core"

    /** `TradingHaltExecutor.PARAMETER_NAME` — the `client_context` key the gateway reads. */
    const val CLIENT_CONTEXT_KEY = "owner_halt_authority_ref"

    /**
     * Prepares the canonical `owner-halt` statement for `van-trading-core`. The caller signs
     * [OwnerAuthorityToken.Prepared.canonical] under biometric authentication and calls
     * [OwnerAuthorityToken.Prepared.assembleFromSignatureBase64] on the result to obtain the
     * `owner_halt_authority_ref` string.
     */
    fun prepare(issuedAtUnix: Long = System.currentTimeMillis() / 1000L): OwnerAuthorityToken.Prepared =
        OwnerApprovalKeyManager().prepareOwnerAuthority(
            act = AUTHORITY_ACT,
            subject = AUTHORITY_SUBJECT,
            issuedAtUnix = issuedAtUnix,
        )
}
