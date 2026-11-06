package com.dial.van.dialdev

import kotlin.test.*
import org.json.JSONObject
import java.util.concurrent.Executors

class DialDevOriginalOperationsTest {
    class Memory : DialDevOperationStore {
        var raw: String? = null
        var writable = true
        override fun load() = raw
        override fun save(value: String): Boolean { if (!writable) return false; raw=value; return true }
    }
    private val target = DialDevActionTarget("van","task-A")
    private fun request(key: String="original-key",revision: String="sha256:old",params: Map<String,String> = mapOf("guidance" to "Original instruction"),scope: DialDevActionTarget=target) =
        requireNotNull(DialDevActionRequest.build(DialDevActionKind.STEER_TASK,scope,params,revision,key))
    private fun outcome(id: String="act_original",state: String="APPLIED",project: String="van",task: String="task-A",reason: String?=null,freshness: Long=0): String =
        JSONObject().put("projection_revision","sha256:current").put("freshness_ms",freshness)
            .put("observed_at","2026-10-23T12:00:00Z").put("sources",JSONObject()).put("degraded",org.json.JSONArray())
            .put("data",JSONObject().put("action_id",id).put("action","STEER_TASK")
                .put("typed_control",JSONObject().put("tool","dial_owner_steer"))
                .put("control_result",JSONObject().put("steer_id","steer_original").put("sequence",1).put("steer_state","PENDING"))
                .put("target",JSONObject().put("project_id",project).put("task_id",task))
                .put("state",state).put("reason",reason ?: JSONObject.NULL)).toString()

    @Test fun `cold retry keeps exact original revision parameters and key`() {
        val memory=Memory();val first=DialDevOriginalOperations(memory).prepare("phone",request())
        val retry=DialDevOriginalOperations(memory).prepare("phone",request("new-key-ignored","sha256:new"))
        assertEquals(first,retry);assertEquals("original-key",retry.request().idempotencyKey)
        assertEquals("sha256:old",retry.request().expectedProjectionRevision)
    }
    @Test fun `changed parameters cannot replace an unknown original`() {
        val memory=Memory();val store=DialDevOriginalOperations(memory);val first=store.prepare("phone",request());val before=memory.raw
        assertFails { store.prepare("phone",request("different-key",params=mapOf("guidance" to "Changed instruction"))) }
        assertEquals(before,memory.raw);assertEquals(listOf(first),store.pending("phone",target))
    }
    @Test fun `caller mutable parameters cannot change a prepared request`() {
        val params=mutableMapOf("guidance" to "Original instruction");val desired=request(params=params)
        params["guidance"]="Changed outside the operation"
        assertEquals("Original instruction",DialDevOriginalOperations(Memory()).prepare("phone",desired).request().params["guidance"])
    }
    @Test fun `failed or corrupt persistence refuses new dispatch`() {
        val memory=Memory();memory.writable=false
        assertFails { DialDevOriginalOperations(memory).prepare("phone",request()) };assertNull(memory.raw)
        memory.writable=true;memory.raw="{corrupt"
        assertFails { DialDevOriginalOperations(memory).prepare("phone",request()) };assertEquals("{corrupt",memory.raw)
    }
    @Test fun `accepted identity survives restart and foreign readbacks never clear it`() {
        val memory=Memory();val store=DialDevOriginalOperations(memory);val original=store.prepare("phone",request())
        store.accepted(original,JSONObject().put("action_id","act_original"))
        val restarted=DialDevOriginalOperations(memory);val pending=restarted.pending("phone",target).single()
        assertNull(restarted.observe(pending,outcome(id="act_other")))
        assertNull(restarted.observe(pending,outcome(project="other")))
        assertNull(restarted.observe(pending,outcome(task="task-B")))
        assertNull(restarted.observe(pending,outcome(freshness=30001)))
        assertEquals(1,restarted.pending("phone",target).size)
        assertEquals(DialDevActionStatus.Applied("act_original"),restarted.observe(pending,outcome()))
        assertTrue(restarted.pending("phone",target).isEmpty())
        assertFalse(memory.raw!!.contains("Original instruction"))
    }
    @Test fun `unknown native timeout reason does not become proven refusal`() {
        val memory=Memory();val store=DialDevOriginalOperations(memory);val original=store.prepare("phone",request())
        store.accepted(original,JSONObject().put("action_id","act_original"));val pending=store.pending("phone",target).single()
        assertIs<DialDevActionStatus.Unconfirmed>(store.observe(pending,outcome(state="REJECTED",reason="CONTROL_UNAVAILABLE:reply lost")))
        assertEquals(1,store.pending("phone",target).size)
    }
    @Test fun `two client instances cannot mint separate original operations`() {
        val memory=object : DialDevOperationStore {
            @Volatile var raw: String? = null
            val readers=java.util.concurrent.CountDownLatch(2)
            override fun load(): String? {
                val snapshot=raw
                readers.countDown();readers.await(200,java.util.concurrent.TimeUnit.MILLISECONDS)
                return snapshot
            }
            override fun save(value: String): Boolean { raw=value;return true }
        }
        val pool=Executors.newFixedThreadPool(2)
        try {
            val a=pool.submit<PendingDialDevOperation> { DialDevOriginalOperations(memory).prepare("phone",request("first-key")) }
            val b=pool.submit<PendingDialDevOperation> { DialDevOriginalOperations(memory).prepare("phone",request("second-key")) }
            assertEquals(a.get(),b.get());assertEquals(1,DialDevOriginalOperations(memory).pending("phone",target).size)
        } finally { pool.shutdownNow() }
    }
    @Test fun `distinct typed controls preserve independent originals and native authorization`() {
        val memory=Memory();val store=DialDevOriginalOperations(memory)
        val global=requireNotNull(DialDevActionRequest.build(DialDevActionKind.PAUSE_MISSION,DialDevActionTarget("van"),emptyMap(),"sha256:old","original-key"))
        store.prepare("phone",global)
        val task=store.prepare("phone",request("task-original-key"))
        assertEquals(1,store.pending("phone",target).size)
        assertEquals(1,store.pending("phone",DialDevActionTarget("van")).size)
        assertEquals("task-original-key",task.request().idempotencyKey)
    }
    @Test fun `same task name in another project has a different scope`() {
        val memory=Memory();val store=DialDevOriginalOperations(memory)
        store.prepare("phone",request());store.prepare("phone",request("other-key",scope=DialDevActionTarget("another-project","task-A")))
        assertEquals(1,store.pending("phone",target).size)
        assertEquals(1,store.pending("phone",DialDevActionTarget("another-project","task-A")).size)
    }
    @Test fun `an old terminal observer cannot erase a newer operation`() {
        val memory=Memory();val store=DialDevOriginalOperations(memory);val first=store.prepare("phone",request())
        store.accepted(first,JSONObject().put("action_id","act_original"));val old=store.pending("phone",target).single()
        store.observe(old,outcome());val next=store.prepare("phone",request("next-key",params=mapOf("guidance" to "New owner instruction")))
        assertEquals(DialDevActionStatus.Applied("act_original"),store.observe(old,outcome()))
        assertEquals(listOf(next),store.pending("phone",target))
    }
    @Test fun `malformed native freshness cannot retire an original control`() {
        val memory=Memory();val store=DialDevOriginalOperations(memory);val first=store.prepare("phone",request())
        store.accepted(first,JSONObject().put("action_id","act_original"));val pending=store.pending("phone",target).single()
        assertNull(store.observe(pending,JSONObject(outcome()).put("freshness_ms","0").toString()))
        assertNull(store.observe(pending,JSONObject(outcome()).put("freshness_ms",false).toString()))
        assertEquals(1,store.pending("phone",target).size)
    }
    @Test fun `a separately authorized protective pause stays available without replacing the original`() {
        val memory=Memory();val store=DialDevOriginalOperations(memory);val first=store.prepare("phone",request())
        val pause=requireNotNull(DialDevActionRequest.build(DialDevActionKind.PAUSE_MISSION,DialDevActionTarget("van"),emptyMap(),"sha256:current","protective-key"))
        val result=runCatching { store.prepare("phone",pause) }
        assertTrue(result.isSuccess)
        val protective=result.getOrThrow()
        assertEquals("protective-key",protective.request().idempotencyKey)
        assertEquals(1,store.pending("phone",target).size)
        assertEquals(1,store.pending("phone",DialDevActionTarget("van")).size)
        assertTrue(first in store.pending("phone",target))
        val taskPause=requireNotNull(DialDevActionRequest.build(DialDevActionKind.PAUSE_TASK_SAFE,target,emptyMap(),"sha256:current","task-protective-key"))
        val taskResult=runCatching { store.prepare("phone",taskPause) }
        assertTrue(taskResult.isSuccess)
        assertEquals(2,store.pending("phone",target).size)
        assertFails { store.prepare("phone",request("changed-key",params=mapOf("guidance" to "Replace original"))) }
    }
    @Test fun `different native decisions keep different original requests`() {
        val memory=Memory();val store=DialDevOriginalOperations(memory)
        fun decision(id: String,key: String)=requireNotNull(DialDevActionRequest.build(DialDevActionKind.DECIDE,
            DialDevActionTarget("van",decisionId=id),mapOf("decision" to "approve"),"sha256:current",key))
        store.prepare("phone",decision("decision-A","decision-key-a"))
        store.prepare("phone",decision("decision-B","decision-key-b"))
        assertEquals("decision-key-a",store.pending("phone",DialDevActionTarget("van",decisionId="decision-A")).single().request().idempotencyKey)
        assertEquals("decision-key-b",store.pending("phone",DialDevActionTarget("van",decisionId="decision-B")).single().request().idempotencyKey)
    }
    @Test fun `an applied label without its native acknowledgement cannot settle an original`() {
        val memory=Memory();val store=DialDevOriginalOperations(memory);val first=store.prepare("phone",request())
        store.accepted(first,JSONObject().put("action_id","act_original"));val pending=store.pending("phone",target).single()
        val missing=JSONObject(outcome());missing.getJSONObject("data").remove("control_result")
        assertNull(store.observe(pending,missing.toString()))
        val empty=JSONObject(outcome());empty.getJSONObject("data").put("control_result",JSONObject().put("steer_id",JSONObject.NULL))
        assertNull(store.observe(pending,empty.toString()))
        assertEquals(1,store.pending("phone",target).size)
    }
}
