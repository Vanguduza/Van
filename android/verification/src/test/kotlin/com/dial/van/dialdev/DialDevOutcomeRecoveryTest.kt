package com.dial.van.dialdev

import kotlin.test.*

class DialDevOutcomeRecoveryTest {
    @Test fun `service unavailability after a possible effect retains original request identity`() {
        val result = DialDevActionReducer.onResponse(503, """{"error":"dial_dev_unavailable","reason":"timeout"}""")
        assertIs<DialDevActionStatus.Unconfirmed>(result)
        assertEquals(DialDevActionReducer.RetryMode.SAME_KEY, DialDevActionReducer.retry(result))
    }

    @Test fun `an idempotency conflict is not permission to issue a new action`() {
        val result = DialDevActionReducer.onResponse(409, """{"error":"idempotency_conflict"}""")
        assertIs<DialDevActionStatus.Unconfirmed>(result)
        assertEquals(DialDevActionReducer.RetryMode.SAME_KEY, DialDevActionReducer.retry(result))
    }

    @Test fun `native stale view identifies its actual current revision`() {
        assertEquals(DialDevActionStatus.StaleView("sha256:new"),
            DialDevActionReducer.onResponse(409, """{"error":"STALE_VIEW","current_projection_revision":"sha256:new"}"""))
    }

    @Test fun `a native control error after a previous attempt remains unresolved`() {
        for (reason in listOf("CONTROL_UNAUTHORIZED", "CONTROL_RPC_ERROR:lost acknowledgement", "CONTROL_REFUSED:effect uncertain", "FORWARDER_ERROR:reply lost")) {
            val body = org.json.JSONObject().put("action_id","act_original").put("state","REJECTED").put("reason",reason).toString()
            assertIs<DialDevActionStatus.Unconfirmed>(DialDevActionReducer.onResponse(202,body))
            assertIs<DialDevActionStatus.Unconfirmed>(DialDevActionReducer.reconcile(
                DialDevActionStatus.Accepted("act_original"),listOf(ProjectedAction("act_original","REJECTED",reason))))
        }
    }
    @Test fun `recent metadata cannot bypass a durable originals bound native read`() {
        val original=DialDevActionStatus.Accepted("act_original")
        assertEquals(original,DialDevActionReducer.reconcileDurable(original,
            listOf(ProjectedAction("act_original","APPLIED",null)),setOf("act_original")))
    }
    @Test fun `a late observer cannot report its result as a newer owner control`() {
        assertFalse(DialDevActionReducer.observesCurrentOriginal("old-key","new-key"))
        assertTrue(DialDevActionReducer.observesCurrentOriginal("old-key","old-key"))
        assertTrue(DialDevActionReducer.observesCurrentOriginal("old-key",null))
    }
}
