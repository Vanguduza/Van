package com.dial.van.dialdev

import org.json.JSONArray
import org.json.JSONObject

/** Production storage is encrypted. No proof, token, endpoint or native credential is stored. */
interface DialDevOperationStore {
    fun load(): String?
    fun save(value: String): Boolean
}

data class PendingDialDevOperation(
    val deviceId: String,
    val requestBody: String,
    val actionId: String? = null,
) {
    fun request(): DialDevActionRequest = DialDevOriginalOperations.decodeRequest(requestBody)
}

class DialDevOriginalOperations(private val store: DialDevOperationStore) {
    companion object {
        private val lock = Any()
        private val identifier = Regex("[A-Za-z0-9][A-Za-z0-9._:-]{0,159}")
        private fun text(o: JSONObject, key: String): String = o.opt(key) as? String
            ?: error("dial_dev_original_history_unreadable")
        private fun keys(o: JSONObject) = o.keys().asSequence().toSet()
        internal fun decodeRequest(body: String): DialDevActionRequest {
            require(body.length <= 65536)
            val o = JSONObject(body)
            check(keys(o) == setOf("action","target","params","idempotency_key","expected_projection_revision"))
            val target = o.getJSONObject("target")
            check(keys(target).all { it in setOf("project_id","task_id","workspace_id","decision_id") })
            val project = text(target,"project_id"); check(identifier.matches(project))
            fun optional(key: String): String? = if (!target.has(key)) null else text(target,key).also { check(identifier.matches(it)) }
            val params = o.getJSONObject("params")
            val values = params.keys().asSequence().associateWith { text(params,it) }
            val key = text(o,"idempotency_key"); check(key.length in 8..128 && key.none { it.isISOControl() })
            val revision = text(o,"expected_projection_revision"); check(revision.isNotBlank() && revision.length <= 256)
            val kind = DialDevActionKind.valueOf(text(o,"action"))
            val scope = DialDevActionTarget(project,optional("task_id"),optional("workspace_id"),optional("decision_id"))
            if (kind in setOf(DialDevActionKind.STEER_TASK,DialDevActionKind.PAUSE_TASK_SAFE,DialDevActionKind.RESUME_TASK,
                    DialDevActionKind.REQUEST_CHECKPOINT,DialDevActionKind.REQUEST_REVIEW,DialDevActionKind.REVOKE_TASK))
                check(scope.taskId != null)
            if (kind == DialDevActionKind.DECIDE) check(scope.decisionId != null)
            return DialDevActionRequest.build(kind,
                scope,
                values,revision,key) ?: error("dial_dev_original_history_unreadable")
        }
    }

    private fun read(): List<PendingDialDevOperation> {
        val raw = store.load() ?: return emptyList()
        check(raw.length <= 1024*1024)
        val o = JSONObject(raw)
        check(keys(o) == setOf("schema","operations") && text(o,"schema") == "van.android.dial-dev-originals/1")
        val rows = o.getJSONArray("operations"); check(rows.length() <= 128)
        val result = (0 until rows.length()).map { i ->
            val row = rows.getJSONObject(i)
            check(keys(row) == setOf("device_id","request","action_id"))
            val device = text(row,"device_id"); check(identifier.matches(device))
            val body = text(row,"request"); decodeRequest(body)
            val action = if (row.isNull("action_id")) null else text(row,"action_id").also { check(identifier.matches(it)) }
            PendingDialDevOperation(device,body,action)
        }
        check(result.map { it.deviceId to it.request().idempotencyKey }.toSet().size == result.size)
        return result
    }

    private fun write(rows: List<PendingDialDevOperation>) {
        check(rows.size <= 128)
        val values = JSONArray()
        rows.forEach { p -> values.put(JSONObject().put("device_id",p.deviceId)
            .put("request",p.requestBody).put("action_id",p.actionId ?: JSONObject.NULL)) }
        val body = JSONObject().put("schema","van.android.dial-dev-originals/1").put("operations",values).toString()
        check(body.length <= 1024*1024)
        check(store.save(body)) { "dial_dev_original_not_saved_no_dispatch" }
    }

    fun pending(device: String, target: DialDevActionTarget): List<PendingDialDevOperation> = synchronized(lock) {
        read().filter { it.deviceId == device && sameScope(it.request().target,target) }
    }

    private fun sameScope(a: DialDevActionTarget,b: DialDevActionTarget): Boolean =
        a.copy(workspaceId=null) == b.copy(workspaceId=null)

    fun prepare(device: String, desired: DialDevActionRequest): PendingDialDevOperation = synchronized(lock) {
        check(identifier.matches(device))
        val snapshot = decodeRequest(desired.toJson().toString())
        val rows = read()
        val original = rows.firstOrNull { it.deviceId == device && it.request().kind == snapshot.kind && sameScope(it.request().target,snapshot.target) }
        if (original != null) {
            val prior = original.request()
            check(prior.kind == snapshot.kind && prior.target.copy(workspaceId=null) == snapshot.target.copy(workspaceId=null) && prior.params == snapshot.params) {
                "dial_dev_original_requires_reconciliation"
            }
            return original // Original revision, parameters and key survive every retry and restart.
        }
        check(rows.none { it.deviceId == device && it.request().idempotencyKey == snapshot.idempotencyKey }) {
            "dial_dev_original_key_conflict"
        }
        val value = PendingDialDevOperation(device,snapshot.toJson().toString())
        write(rows + value)
        value
    }

    fun accepted(original: PendingDialDevOperation, response: JSONObject) = synchronized(lock) {
        val id = text(response,"action_id"); check(identifier.matches(id))
        val rows = read(); val key = original.request().idempotencyKey
        val current = rows.single { it.deviceId == original.deviceId && it.request().idempotencyKey == key }
        check(current.requestBody == original.requestBody && (current.actionId == null || current.actionId == id))
        write(rows.map { if (it == current) it.copy(actionId=id) else it })
    }

    fun staleViewNoEffect(original: PendingDialDevOperation) = synchronized(lock) { remove(original) }

    private fun acknowledged(request: DialDevActionRequest, row: JSONObject): Boolean {
        val tool = row.optJSONObject("typed_control")?.opt("tool") as? String ?: return false
        val result = row.optJSONObject("control_result") ?: return false
        fun supplied(key: String) = (result.opt(key) as? String)?.isNotBlank() == true
        return when (request.kind) {
            DialDevActionKind.STEER_TASK -> tool == "dial_owner_steer" && supplied("steer_id") && supplied("steer_state") &&
                (result.opt("sequence").let { it is Int && it >= 0 || it is Long && it >= 0 })
            DialDevActionKind.DECIDE -> tool == (if (request.params["decision"] == "approve") "dial_approve_gate" else "dial_reject_gate") &&
                result.opt("gate_id") == request.target.decisionId &&
                result.opt("decision") == (if (request.params["decision"] == "approve") "APPROVED" else "REJECTED")
            DialDevActionKind.PAUSE_MISSION -> tool == "dial_pause_mission" && supplied("mission_state")
            DialDevActionKind.RESUME_MISSION -> tool == "dial_resume_mission" && supplied("mission_state")
            DialDevActionKind.REPRIORITISE -> tool == "dial_reprioritize" && supplied("mission_state")
            else -> false // These controls need an admitted native acknowledgement contract.
        }
    }

    private fun remove(original: PendingDialDevOperation) {
        val rows = read(); val key = original.request().idempotencyKey
        val current = rows.firstOrNull { it.deviceId == original.deviceId && it.request().idempotencyKey == key }
        if (current != null) {
            check(current.requestBody == original.requestBody)
            write(rows.filterNot { it == current })
        }
    }

    fun observe(original: PendingDialDevOperation, body: String): DialDevActionStatus? = synchronized(lock) {
        val raw = runCatching { JSONObject(body) }.getOrNull() ?: return null
        val age = raw.opt("freshness_ms")
        if (age !is Int && age !is Long) return null
        if (raw.opt("observed_at") !is String || raw.opt("sources") !is JSONObject || raw.opt("degraded") !is JSONArray)
            return null
        val envelope = DialDevEnvelope.parse(body) ?: return null
        if (envelope.freshnessMs !in 0..30000) return null
        val row = envelope.data
        val id = row.opt("action_id") as? String ?: return null
        if (original.actionId == null || id != original.actionId) return null
        val request = original.request()
        if (row.opt("action") != request.kind.name) return null
        val target = row.optJSONObject("target") ?: return null
        for ((key,expected) in listOf("project_id" to request.target.projectId,"task_id" to request.target.taskId,"decision_id" to request.target.decisionId)) {
            val actual = if (target.isNull(key) || !target.has(key)) null else target.opt(key) as? String ?: return null
            if (actual != expected) return null
        }
        val result = when (row.opt("state")) {
            "APPLIED" -> {
                if (!acknowledged(request,row)) return null
                DialDevActionStatus.Applied(id)
            }
            "REJECTED" -> {
                val reason = row.opt("reason") as? String
                if (DialDevActionReducer.uncertainNativeReason(reason))
                    return DialDevActionStatus.Unconfirmed("The native control outcome still needs reconciliation.")
                DialDevActionStatus.Rejected(id,reason?.ifBlank { null } ?: "No reason given.")
            }
            "SUPERSEDED" -> DialDevActionStatus.Superseded(id)
            else -> return null
        }
        remove(original) // Erase private prepared guidance only after bound native outcome.
        result
    }
}
