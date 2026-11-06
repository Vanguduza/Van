from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from van_gateway.context.models import OwnerFactCandidate, EpistemicState, SourceTrust
from van_gateway.context.service import ContextAdmissionError


def digest(body: dict) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class CognitiveCandidate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_context_revision: int = Field(ge=0)
    candidate_id: str = Field(min_length=1, max_length=100)
    provider_product: Literal['personal-muse-free', 'meta-ai-free-spark-surface', 'openai-dot', 'van-native']
    candidate_type: Literal['GUARDIAN_OBSERVATION', 'DOCTOR_FINDING', 'RESEARCH_ARTIFACT',
                            'OWNER_PATTERN', 'ATTENTION_CALIBRATION', 'MISSION_CANDIDATE', 'TRADING_RESEARCH']
    observed_at_ms: int
    expires_at_ms: int
    source_refs: list[str] = Field(min_length=1, max_length=30)
    evidence_hashes: list[str] = Field(min_length=1, max_length=30)
    confidence_permille: int = Field(ge=0, le=1000)
    affected_scopes: list[str] = Field(min_length=1, max_length=10)
    summary: str = Field(min_length=1, max_length=4000)
    proposed_follow_up: str = Field(default='', max_length=2000)
    data_class: Literal['PUBLIC', 'INTERNAL_SANITIZED']
    response_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    sensitive_inference: Literal[False] = False
    counterexamples: list[str] = Field(default_factory=list, max_length=30)
    observed_instances: list[str] = Field(default_factory=list, max_length=30)
    attention_dimensions: dict[str, float] = Field(default_factory=dict)
    supersedes_candidate_id: str | None = None

    @field_validator('data_class', mode='before')
    @classmethod
    def normalize_data_class(cls, value):
        return 'INTERNAL_SANITIZED' if value == 'INTERNAL_SAFE_FOR_APPROVED_PROVIDER' else value



class CognitiveService:
    def __init__(self, store, context):
        self.store, self.context = store, context

    def providers(self) -> dict:
        path = Path(__file__).resolve().parents[3] / 'registries' / 'cognitive_providers.json'
        return json.loads(path.read_text())

    async def candidates(self, *, now_ms: int | None = None) -> list[dict]:
        stamp = int(time.time() * 1000) if now_ms is None else now_ms
        rows = await self.store.fetchall("SELECT value FROM runtime_meta WHERE key LIKE 'cognitive_candidate:%'", ())
        candidates = [json.loads(r['value']) for r in rows]
        superseded = {r['supersedes_candidate_id'] for r in candidates if r.get('supersedes_candidate_id')}
        owner_supersessions = await self.store.fetchall("SELECT supersedes_fact_id FROM owner_facts WHERE authority = 'CANONICAL_OWNER' AND supersedes_fact_id LIKE 'cognitive:%'", ())
        owner_corrected = {r['supersedes_fact_id'].removeprefix('cognitive:') for r in owner_supersessions}
        for row in candidates:
            row['state'] = 'SUPERSEDED' if row['candidate_id'] in superseded or row['candidate_id'] in owner_corrected else 'EXPIRED' if row['expires_at_ms'] <= stamp else 'INFERRED'
        for row in candidates:
            if row['candidate_type'] == 'OWNER_PATTERN' and row['state'] == 'INFERRED':
                fact = await self.store.fetchone('SELECT fact_id FROM owner_facts WHERE fact_id = ?', ('cognitive:' + row['candidate_id'],))
                if not fact:
                    row['state'] = 'PENDING_CONTEXT_ADMISSION'
        return sorted(candidates, key=lambda r: r['observed_at_ms'], reverse=True)[:100]

    async def ingest(self, body: CognitiveCandidate, *, now_ms: int | None = None, trusted_ingress: str = 'EXPLICIT_OWNER_IMPORT') -> dict:
        stamp = int(time.time() * 1000) if now_ms is None else now_ms
        if not body.observed_at_ms <= stamp < body.expires_at_ms:
            raise ContextAdmissionError('STALE_OR_FUTURE_CANDIDATE')
        if body.candidate_type == 'OWNER_PATTERN' and not body.observed_instances:
            raise ContextAdmissionError('OWNER_PATTERN_REQUIRES_OBSERVED_INSTANCES')
        dimensions = {'importance', 'urgency', 'actionability', 'novelty', 'owner_relevance', 'confidence', 'interruption_cost'}
        if set(body.attention_dimensions) - dimensions or any(not 0 <= v <= 1 for v in body.attention_dimensions.values()):
            raise ContextAdmissionError('ATTENTION_DIMENSIONS_INVALID')
        if body.candidate_type == 'ATTENTION_CALIBRATION' and not body.attention_dimensions:
            raise ContextAdmissionError('ATTENTION_DIMENSIONS_REQUIRED')
        data = body.model_dump()
        data.update(authority='ADVISORY_CANDIDATE', source_trust='MODEL_DERIVED',
                    transport=trusted_ingress, untrusted_content=True,
                    provider_approval_required=body.data_class != 'PUBLIC')
        data['content_hash'] = digest(data)
        key = 'cognitive_candidate:' + body.candidate_id
        previous = await self.store.fetchone('SELECT value FROM runtime_meta WHERE key = ?', (key,))
        if previous:
            previous = json.loads(previous['value'])
            if previous['content_hash'] != data['content_hash']:
                raise ContextAdmissionError('CANDIDATE_ID_COLLISION')
            await self._ensure_owner_fact(body, key)
            return previous
        if body.expected_context_revision != await self.context.kernel_revision():
            raise ContextAdmissionError('STALE_CONTEXT_REVISION')
        async with self.store.connection() as db:
            await db.execute('BEGIN IMMEDIATE')
            prior = await (await db.execute('SELECT value FROM runtime_meta WHERE key = ?', (key,))).fetchone()
            if prior:
                previous = json.loads(prior['value'])
                if previous['content_hash'] != data['content_hash']:
                    raise ContextAdmissionError('CANDIDATE_ID_COLLISION')
                return previous
            if body.supersedes_candidate_id:
                old = await (await db.execute('SELECT value FROM runtime_meta WHERE key = ?', ('cognitive_candidate:' + body.supersedes_candidate_id,))).fetchone()
                if not old:
                    raise ContextAdmissionError('UNKNOWN_SUPERSEDED_CANDIDATE')
                old_body = json.loads(old['value'])
                if (old_body['candidate_type'], old_body['affected_scopes']) != (body.candidate_type, body.affected_scopes):
                    raise ContextAdmissionError('SUPERSESSION_SCOPE_MISMATCH')
                if old_body['observed_at_ms'] >= body.observed_at_ms:
                    raise ContextAdmissionError('SUPERSESSION_MUST_ADVANCE')
            await db.execute('INSERT INTO runtime_meta(key, value, updated_at_unix_ms) VALUES (?, ?, ?)', (key, json.dumps(data), stamp))
            await db.commit()
        await self._ensure_owner_fact(body, key)
        return data

    async def _ensure_owner_fact(self, body, key):
        if body.candidate_type == 'OWNER_PATTERN':
            existing = await self.store.fetchone('SELECT fact_id FROM owner_facts WHERE fact_id = ?', ('cognitive:' + body.candidate_id,))
            if existing:
                return
            # Reuse VAN's actual inferred context admission, never owner authority.
            # This deliberately has no inferred->canonical promotion operation.
            fact = OwnerFactCandidate(fact_id='cognitive:' + body.candidate_id, subject='OWNER',
                predicate='pattern', value={'pattern': body.summary, 'counterexamples': body.counterexamples,
                'observed_instances': body.observed_instances}, authority=EpistemicState.INFERRED,
                source_trust=SourceTrust.MODEL_DERIVED, source_ref=key,
                confidence_permille=body.confidence_permille, scope=body.affected_scopes[0],
                valid_from_ms=body.observed_at_ms, valid_until_ms=body.expires_at_ms,
                observed_at_ms=body.observed_at_ms,
                supersedes_fact_id=('cognitive:' + body.supersedes_candidate_id) if body.supersedes_candidate_id else None)
            await self.context.admit_fact(fact)

    async def slice(self, operation: str, trading) -> dict:
        stamp = int(time.time() * 1000)
        revision = await self.context.kernel_revision()
        envelope = {'schema_version': 1, 'project_id': 'van', 'domain': 'trading' if operation in
            ('trading-market', 'strategy-health', 'performance', 'tca', 'learning-episodes') else 'owner',
            'operation': operation, 'data_class': 'INTERNAL_SANITIZED', 'provider_approval_required': True,
            'authority': 'DERIVED_READ_ONLY', 'source_revision': revision, 'context_revision': revision,
            'generated_at_ms': stamp, 'expires_at_ms': stamp + 60000}
        if operation == 'missions':
            rows = await self.store.fetchall('SELECT mission_id, project_id, state, verification_state, updated_at_ms, deadline_ms FROM missions ORDER BY updated_at_ms DESC LIMIT 30', ())
            payload = {'missions': [dict(r) for r in rows], 'private_goal_text_excluded': True}
        elif operation == 'attention':
            rows = await self.store.fetchall('SELECT id, severity, state, project_id, updated_at_unix FROM attention ORDER BY updated_at_unix DESC LIMIT 30', ())
            payload = {'attention': [dict(r) for r in rows], 'private_summary_text_excluded': True}
        elif operation == 'owner-context':
            rows = await self.store.fetchall('SELECT authority, source_trust, COUNT(*) AS n FROM owner_facts GROUP BY authority, source_trust', ())
            public = await self.store.fetchall("SELECT fact_id, subject, predicate, value_json, authority, source_ref, scope, valid_until_ms FROM owner_facts WHERE sensitivity = 'PUBLIC' ORDER BY observed_at_ms DESC LIMIT 20", ())
            payload = {'authority_summary': [dict(r) for r in rows],
                'public_facts': [{**dict(r), 'value': json.loads(r['value_json'])} for r in public],
                'owner_private_raw_context_excluded': True}
            for row in payload['public_facts']:
                row.pop('value_json', None)
        elif operation == 'capability-utilization':
            rows = await self.store.fetchall('SELECT capability_id, readiness_source, declaration_json FROM capability_registry WHERE withdrawn_at_ms IS NULL ORDER BY capability_id LIMIT 100', ())
            usage = await self.store.fetchall("SELECT a.capability_id, COUNT(*) AS n, MAX(a.started_at_ms) AS last_used, SUM(CASE WHEN a.state = 'COMPLETED' AND m.state = 'VERIFIED_SUCCESS' THEN 1 ELSE 0 END) AS verified FROM mission_activities a JOIN missions m ON m.mission_id = a.mission_id GROUP BY a.capability_id", ())
            by_id = {r['capability_id']: dict(r) for r in usage}
            items = []
            for row in rows:
                declaration = json.loads(row['declaration_json'])
                actual = by_id.get(row['capability_id'], {})
                items.append({'capability_id': row['capability_id'], 'implemented': True,
                    'runtime_ready': True if row['readiness_source'] == 'STATIC' else None,
                    'readiness_source': row['readiness_source'],
                    'owner_visible': declaration.get('owner_visible'), 'configured': None,
                    'last_used': actual.get('last_used'), 'usage_count': actual.get('n', 0),
                    'verified_outcome_count': actual.get('verified', 0),
                    'value_signal': None, 'friction_signal': None,
                    'unmeasured_fields_are_unknown': True})
            payload = {'capabilities': items, 'usage_source': 'mission_activities'}
        elif operation in ('trading-market', 'strategy-health', 'performance', 'tca', 'learning-episodes'):
            payload = trading.cognitive_slice(operation)
        else:
            raise ContextAdmissionError('UNKNOWN_COGNITIVE_READ_OPERATION')
        envelope['state'] = payload.pop('state', 'AVAILABLE')
        envelope['payload'] = payload
        envelope['projection_revision'] = digest(envelope)
        return envelope

    async def guardian_projection(self, trading, *, now_ms: int | None = None) -> dict:
        stamp = int(time.time() * 1000) if now_ms is None else now_ms
        # Whitelist-only aggregation. No raw logs, context, customer or broker rows.
        status = trading.status()
        missions = await self.store.fetchall("SELECT mission_id, project_id, state, verification_state FROM missions ORDER BY updated_at_ms DESC LIMIT 20", ())
        projects = await self.store.fetchall("SELECT project_id, truth_sha, repo_sha, stale FROM project_truth_cache ORDER BY project_id LIMIT 20", ())
        attention = await self.store.fetchall("SELECT severity, state, COUNT(*) AS n FROM attention GROUP BY severity, state", ())

        body = {'generated_at_ms': stamp, 'expires_at_ms': stamp + 300000,
                'data_class': 'INTERNAL_SANITIZED', 'provider_approval_required': True,
                'projects': [dict(r) for r in projects],
                'current_missions': [dict(r) for r in missions],
                'owner_attention_summary': [dict(r) for r in attention],
                'deployment_summary': {'state': 'UNAVAILABLE_NO_QUALIFIED_PROJECTION'},
                'CI_summary': {'state': 'UNAVAILABLE_NO_QUALIFIED_PROJECTION'},
                'business_KPI_summary': {'state': 'UNAVAILABLE_NO_QUALIFIED_PROJECTION'},
                'current_hypotheses': [],
                'health_summary': {'trading_ledger_available': bool(status.get('ledger_available')),
                                   'trading_ledger_stale': bool(status.get('ledger_stale', True))},
                'trading_research_summary': {'execution_authority': 'VATI_ONLY',
                                            'live_provider_use': 'NOT_CLAIMED'},
                'known_incidents': [{'candidate_id': c['candidate_id'], 'state': c['state'],
                                     'type': c['candidate_type']} for c in await self.candidates(now_ms=stamp)
                                    if c['candidate_type'] in ('GUARDIAN_OBSERVATION', 'DOCTOR_FINDING')],
                'allowed_external_links': [], 'authority': 'DERIVED_READ_ONLY',
                'runtime_dependency': False}
        body['context_revision'] = await self.context.kernel_revision()
        body['projection_id'] = digest(body)
        return body
