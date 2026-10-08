"""Evidence-bound, advisory producers over observed decisions and external claims.

No reasons, psychology, causal effects, permissions or truth are inferred here.
Candidates describe repeated observed choices; external disagreements preserve
both the owner's declaration and the source's claim without choosing a winner.
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from typing import Any

from van_gateway.owner_privacy import _reference, _text
from van_gateway.storage.db import Store

MAX_ROWS = 200
MIN_OBSERVATIONS = 3
MAX_AGE_MS = 90 * 24 * 60 * 60 * 1000


def _digest(value: Any) -> str:
    return hashlib.sha256(Store.dumps(value).encode()).hexdigest()


def structured_claim(content: Any) -> dict | None:
    """Accept an actual scalar source claim, never extract semantics from prose."""
    if isinstance(content, str):
        if len(content) > 16000:
            return None
        try:
            content = json.loads(content)
        except (ValueError, TypeError):
            return None
    if not isinstance(content, dict) or set(content) - {"subject", "predicate", "value", "scope"}:
        return None
    if not {"subject", "predicate", "value"} <= set(content):
        return None
    if not isinstance(content["value"], (str, bool, int, float, type(None))):
        return None
    claim = {**content, "scope": content.get("scope", "global")}
    if any(not isinstance(claim[key], str) or not 1 <= len(claim[key]) <= 128
           for key in ("subject", "predicate", "scope")):
        return None
    if isinstance(claim["value"], str) and len(claim["value"]) > 4000:
        return None
    from van_gateway.owner_privacy import _SECRET
    if _SECRET.search(claim["predicate"] + "=") or _SECRET.search(Store.dumps(claim)):
        return None
    try:
        json.dumps(claim, allow_nan=False)
    except (ValueError, TypeError):
        return None
    return claim


async def record_external_claim(store: Store, *, evidence_id: str, content: Any, db: Any | None = None) -> str | None:
    """Use the provider's persisted evidence; callers cannot invent citation authority."""
    claim = structured_claim(content)
    if claim is None:
        return None
    if db is None:
        async with store.connection() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            try:
                result = await record_external_claim(store, evidence_id=evidence_id, content=content, db=connection)
                await connection.commit()
                return result
            except BaseException:
                await connection.rollback()
                raise
    row = await (await db.execute("SELECT * FROM knowledge_evidence WHERE evidence_id=?", (evidence_id,))).fetchone()
    if row is None or not _reference(row["source_ref"]):
        return None
    # KnowledgeEvidenceStore uses these exact digest rules. Re-reading checks the
    # actual provider event in the same transaction, not a self-reported success
    # or arbitrary reference. Its evidence and projection commit together.
    raw = content if isinstance(content, str) else json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if hashlib.sha256(raw.encode()).hexdigest() != row["content_digest"]:
        raise ValueError("external_claim_evidence_content_mismatch")
    observation_id = "ext_structured_" + _digest({"evidence_id": evidence_id, "digest": row["content_digest"]})[:32]
    wrapped = {"schema_version": 1, "claim": claim, "evidence_id": evidence_id,
               "content_digest": row["content_digest"], "source_trust": row["source_trust"],
               "source_content": raw}
    await db.execute("INSERT INTO external_reality(observation_id,subject,claim,source_kind,source_ref,observed_at_ms,confidence,superseded_by,contradicts_owner_belief) VALUES(?,?,?,'structured_provider_claim',?,?,0.0,NULL,0) ON CONFLICT(observation_id) DO NOTHING",
        (observation_id, claim["subject"], Store.dumps(wrapped), row["source_ref"], row["retrieved_at_unix_ms"]))
    return observation_id


async def record_owner_decision_fingerprint(db: Any, *, decision_id: str, mission_id: str | None,
                                           choice_id: str, owner_note: str | None,
                                           evidence_refs: list[str], now_ms: int,
                                           options_considered: list[str] | None = None) -> str | None:
    """Called inside the authenticated owner-answer transaction; never reconstruct erased events."""
    fingerprint_id = "dfp_owner_" + _digest(decision_id)[:32]
    identity = _digest({"table": "decision_fingerprints", "key": {"decision_id": fingerprint_id}})
    erased = await (await db.execute("SELECT 1 FROM runtime_meta m,json_each(CASE WHEN json_valid(m.value) THEN m.value ELSE '{}' END,'$.tables.decision_fingerprints.before_ids') ids WHERE m.key GLOB 'memory_erasure_witness:*' AND ids.value=? LIMIT 1", (identity,))).fetchone()
    if erased:
        return None
    context = Store.dumps({"source_decision_id": decision_id, "source_class": "OWNER_DECLARED"})
    previous = await (await db.execute("SELECT * FROM decision_fingerprints WHERE decision_id=?", (fingerprint_id,))).fetchone()
    if previous:
        if (previous["mission_id"] != mission_id or previous["owner_choice"] != choice_id
                or previous["owner_stated_reason"] != owner_note or previous["context_json"] != context):
            raise ValueError("owner_decision_fingerprint_source_conflict")
        return fingerprint_id
    await db.execute("INSERT INTO decision_fingerprints(decision_id,mission_id,context_json,options_considered_json,owner_choice,owner_stated_reason,inferred_reason,tradeoffs_json,evidence_used_json,rejected_alternatives_json,created_at_ms,updated_at_ms) VALUES(?,?,?,?,?,?,NULL,'[]',?,'[]',?,?)",
        (fingerprint_id, mission_id, context, Store.dumps(options_considered or [choice_id]), choice_id,
         owner_note, Store.dumps(sorted(set(evidence_refs))[:64]), now_ms, now_ms))
    return fingerprint_id


class ObservedLearning:
    def __init__(self, store: Store) -> None:
        self.store = store

    @staticmethod
    def _producer(kind: str, rows: list, *, measured: int, unmeasured: int, evidence: list,
                  snapshot: dict, now: int, why: str) -> dict:
        status = "NO_DATA" if not rows else "PARTIAL" if unmeasured or len(rows) > MAX_ROWS else "READY"
        return {"id": kind, "active": True, "status": status, "observations": min(len(rows), MAX_ROWS),
                "comparisons": measured, "unmeasured": unmeasured, "truncated": len(rows) > MAX_ROWS,
                "evidence_refs": sorted(set(evidence))[:200], "observed_at_ms": now,
                "snapshot_sha256": _digest(snapshot), "why": why, "execution_grant": False}

    async def decisions(self, *, now_ms: int | None = None) -> dict:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        async with self.store.connection() as db:
            await db.execute("BEGIN")
            rows = await (await db.execute("""SELECT f.*, m.owner_principal_id AS mission_owner,
                m.origin AS mission_origin, m.project_id AS mission_project, m.mission_class AS typed_class,
                m.authority_envelope_json, m.state AS mission_state, m.verification_state AS mission_verification,
                a.value AS sealed_authority, x.decision_id AS source_owner_decision,
                x.selected_choice_id AS observed_choice, x.answer_note AS observed_note,
                x.answered_at_unix AS observed_answered_at, x.mission_id AS observed_mission_id,
                d.status AS observed_decision_status
                FROM decision_fingerprints f LEFT JOIN missions m ON m.mission_id=f.mission_id
                LEFT JOIN runtime_meta a ON a.key='command_authority:' || json_extract(
                    CASE WHEN json_valid(m.authority_envelope_json) THEN m.authority_envelope_json ELSE '{}' END,'$.source_command_id')
                LEFT JOIN decision_details x ON x.decision_id=json_extract(
                    CASE WHEN json_valid(f.context_json) THEN f.context_json ELSE '{}' END,'$.source_decision_id')
                LEFT JOIN decisions d ON d.id=x.decision_id
                ORDER BY f.created_at_ms DESC, f.decision_id LIMIT ?""", (MAX_ROWS+1,))).fetchall()
        groups = defaultdict(list)
        seen = set()
        unmeasured = 0
        inputs = []
        for row in rows[:MAX_ROWS]:
            data = dict(row)
            inputs.append(_digest(data))
            if (data["mission_owner"] != "owner"
                    or data["created_at_ms"] > now or now-data["created_at_ms"] > MAX_AGE_MS
                    or data["typed_class"] in {None, "GENERAL_OWNER_INTENT"}):
                unmeasured += 1
                continue
            try:
                envelope = json.loads(data["authority_envelope_json"])
                if not isinstance(envelope, dict):
                    raise ValueError
                context = json.loads(data["context_json"])
                if not isinstance(context, dict):
                    raise ValueError
                if context.get("source_class") == "OWNER_DECLARED" and context.get("source_decision_id"):
                    if (data["source_owner_decision"] != context["source_decision_id"]
                            or data["observed_choice"] != data["owner_choice"]
                            or data["observed_note"] != data["owner_stated_reason"]
                            or data["observed_mission_id"] != data["mission_id"]
                            or data["observed_answered_at"] is None
                            or data["observed_answered_at"] * 1000 != data["created_at_ms"]
                            or data["observed_decision_status"] not in {"APPROVED", "REJECTED", "ANSWERED"}):
                        raise ValueError
                    event_id = "owner-decision:" + context["source_decision_id"]
                else:
                    sealed = json.loads(data["sealed_authority"] or "null")
                    if (not isinstance(sealed, dict) or sealed.get("authority_source") != "OWNER_COMMAND"
                            or sealed.get("principal_type") != "OWNER_DEVICE" or sealed.get("owner_approved") is not True
                            or sealed.get("command_id") != envelope.get("source_command_id")
                            or sealed.get("effective_action_class") != envelope.get("max_action_class")
                            or data["mission_origin"] not in {"OWNER_VOICE", "OWNER_TEXT", "OWNER_UI"}
                            or not envelope.get("requires_owner_presence")
                            or not data["owner_choice"].startswith("approved: ")):
                        raise ValueError
                    event_id = "mission-approval:" + data["mission_id"]
                if event_id in seen:
                    raise ValueError
            except (ValueError, TypeError):
                unmeasured += 1
                continue
            seen.add(event_id)
            key = (data["typed_class"], envelope.get("max_action_class"), data["mission_project"])
            groups[key].append(data)
        patterns = []
        evidence = []
        for key, group in sorted(groups.items(), key=lambda pair: str(pair[0])):
            if len(group) < MIN_OBSERVATIONS:
                unmeasured += len(group)
                continue
            choices = defaultdict(list)
            for item in group:
                # Mission approval text includes a goal; the recorded approve/decline
                # choice alone is the hypothesis, not a guessed psychological reason.
                choice = "approve" if item["owner_choice"].startswith("approved: ") else item["owner_choice"]
                choices[choice].append(item)
            candidate = sorted(choices, key=lambda choice: (-len(choices[choice]), choice))[0]
            support = choices[candidate]
            if len(support) < MIN_OBSERVATIONS:
                unmeasured += len(group)
                continue
            counterexamples = [item for item in group if item not in support]
            verified = [item for item in group if item["outcome"] == "verified_success" and item["mission_state"] == "VERIFIED_SUCCESS" and item["mission_verification"] == "VERIFIED_SUCCESS"]
            failed = [item for item in group if item["outcome"] == "failed" and item["mission_state"] == "FAILED"]
            refs = ["decision-fingerprint:" + item["decision_id"] for item in group]
            evidence.extend(refs)
            patterns.append({"pattern_id": "dp_" + _digest(key)[:24], "epistemic_state": "INFERRED",
                "mission_class": key[0], "action_class": key[1], "project_id": key[2],
                "hypothesis": f"In this observed task context, the owner repeatedly chose {_text(candidate, 256)}.",
                "choice": _text(candidate, 256), "distinct_owner_observations": len(group),
                "support_count": len(support), "counterexample_count": len(counterexamples),
                "state": "COUNTEREXAMPLES_PRESENT" if counterexamples else "CANDIDATE",
                "first_observed_ms": min(item["created_at_ms"] for item in group),
                "last_observed_ms": max(item["created_at_ms"] for item in group),
                "confidence_ceiling": min(0.75, len(support)/len(group)),
                "observed_outcomes": {"independently_verified_success": len(verified), "failed": len(failed),
                    "unknown_or_inconclusive": len(group)-len(verified)-len(failed)},
                "evidence_refs": refs, "owner_stated_reasons": [_text(item["owner_stated_reason"], 4000) for item in group if item["owner_stated_reason"]],
                "inferred_reason": None, "execution_grant": False,
                "scope": "bounded observed choices; outcome correlation does not establish a causal reason"})
        producer = self._producer("decision-patterns", rows, measured=sum(pattern["distinct_owner_observations"] for pattern in patterns),
            unmeasured=unmeasured, evidence=evidence, snapshot={"inputs": inputs, "patterns": patterns}, now=now,
            why="Only distinct owner decisions in an exact typed task context contribute. Reasons are never guessed; counterexamples and unknown outcomes remain visible.")
        return {**producer, "patterns": patterns, "minimum_distinct_observations": MIN_OBSERVATIONS,
                "stale_after_ms": MAX_AGE_MS}

    async def external(self, *, now_ms: int | None = None) -> dict:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        comparisons, contradictions, evidence, inputs = [], [], [], []
        unmeasured = 0
        comparison_truncated = False
        async with self.store.connection() as db:
            await db.execute("BEGIN")
            rows = await (await db.execute("SELECT * FROM external_reality WHERE superseded_by IS NULL ORDER BY observed_at_ms DESC,observation_id LIMIT ?", (MAX_ROWS+1,))).fetchall()
            for row in rows[:MAX_ROWS]:
                inputs.append(_digest(dict(row)))
                try:
                    wrapped = json.loads(row["claim"])
                    claim = structured_claim(wrapped["claim"])
                    if row["source_kind"] != "structured_provider_claim" or claim is None or wrapped["schema_version"] != 1:
                        raise ValueError
                    source = await (await db.execute("SELECT content_digest,source_ref,source_trust FROM knowledge_evidence WHERE evidence_id=?", (wrapped["evidence_id"],))).fetchone()
                    if (not source or source["content_digest"] != wrapped["content_digest"] or source["source_ref"] != row["source_ref"]
                            or source["source_trust"] != wrapped["source_trust"] or row["observed_at_ms"] > now
                            or now-row["observed_at_ms"] > MAX_AGE_MS):
                        raise ValueError
                    raw = wrapped["source_content"]
                    if (not isinstance(raw, str) or hashlib.sha256(raw.encode()).hexdigest() != source["content_digest"]
                            or structured_claim(raw) != claim):
                        raise ValueError
                    owners = await (await db.execute("SELECT * FROM owner_facts WHERE subject=? AND predicate=? AND scope=? AND authority='CANONICAL_OWNER' AND source_trust='OWNER_EXPLICIT' AND sensitivity!='SECRET' AND valid_from_ms<=? AND (valid_until_ms IS NULL OR valid_until_ms>?) ORDER BY fact_id LIMIT ?", (claim["subject"], claim["predicate"], claim["scope"], now, now, MAX_ROWS+1))).fetchall()
                    if not owners:
                        raise ValueError
                except (ValueError, TypeError, KeyError):
                    unmeasured += 1
                    continue
                remaining = MAX_ROWS-len(comparisons)
                if len(owners) > remaining:
                    comparison_truncated = True
                if not remaining:
                    unmeasured += 1
                    continue
                for owner in owners[:remaining]:
                    inputs.append(_digest(dict(owner)))
                    try:
                        declared = json.loads(owner["value_json"])
                    except (ValueError, TypeError):
                        unmeasured += 1
                        continue
                    disagreement = Store.dumps(declared) != Store.dumps(claim["value"])
                    ref = "knowledge:" + wrapped["evidence_id"]
                    comparison = {"comparison_id": "cmp_" + _digest([row["observation_id"], owner["fact_id"], owner["content_digest"]])[:24],
                        "observation_id": row["observation_id"], "owner_fact_id": owner["fact_id"],
                        "subject": _text(claim["subject"]), "predicate": _text(claim["predicate"]), "scope": _text(claim["scope"]),
                        "owner_value": _text(json.dumps(declared, ensure_ascii=False), 4000), "external_value": _text(json.dumps(claim["value"], ensure_ascii=False), 4000),
                        "state": "DISAGREEMENT" if disagreement else "MATCHED_CLAIM", "source_class": "OBSERVED_EXTERNAL_CLAIM",
                        "source_trust": source["source_trust"], "source_ref": _reference(row["source_ref"]),
                        "observed_at_ms": row["observed_at_ms"], "owner_declared_at_ms": owner["valid_from_ms"],
                        "source_age_ms": now-row["observed_at_ms"],
                        "evidence_refs": [ref, "owner-fact:" + owner["fact_id"]], "external_confidence": 0.0,
                        "resolution": "owner_review; source claim is not verified truth", "execution_grant": False}
                    comparisons.append(comparison)
                    evidence.extend(comparison["evidence_refs"])
                    if disagreement:
                        contradictions.append(comparison)
        producer = self._producer("external-contradictions", rows, measured=len(comparisons), unmeasured=unmeasured,
            evidence=evidence, snapshot={"inputs": inputs, "comparisons": comparisons}, now=now,
            why="Exact structured source claims are compared with current owner declarations. Prose, absent citations, stale sources and unmatched scope remain unmeasured; disagreement never overwrites either side.")
        if comparison_truncated:
            producer.update(truncated=True, status="PARTIAL")
        return {**producer, "comparisons": comparisons, "contradictions": contradictions,
                "comparison_count": len(comparisons), "contradiction_count": len(contradictions)}
