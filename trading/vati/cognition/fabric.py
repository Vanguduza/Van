"""Domain-local pre-risk cognition. Evidence only; no order or sizing interface.

First passes are sealed against an identical VATI epoch. Candidates are made
only by the existing InstrumentEvaluator and its admitted capsule registry.
Personal Muse/Dot are T3; they cannot satisfy a live lineage gate.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event

LANES = {'VAN_NATIVE_ANALYST', 'META_ANALYST', 'OPENAI_ANALYST'}
FORBIDDEN = {'approved_size', 'approved_risk_pct', 'requested_risk_pct', 'broker_order',
             'order', 'leverage_override', 'mandate_override', 'risk_multiplier',
             'create_trade_intent', 'widen_stop', 'change_mandate', 'requested_size', 'approved_size_pct',
             'stake', 'lots', 'leverage', 'risk_pct', 'requested_risk', 'order_command',
             'broker_credentials', 'risk_ceiling', 'halt_clear'}
IDENTITIES = {
    'personal-muse-free': ('META_ANALYST', 'META_PERSONAL_MUSE', 'T3'),
    'meta-ai-free-spark-surface': ('META_ANALYST', 'META_FREE_SURFACE', 'T3'),
    'muse-glimmer-local': ('META_ANALYST', 'META_MUSE_LOCAL', 'T2'),
    'van-native': ('VAN_NATIVE_ANALYST', 'VAN_NATIVE', 'T2'),
    'openai-programmatic': ('OPENAI_ANALYST', 'OPENAI_PROGRAMMATIC', 'T2'),
    'openai-dot': ('OPENAI_ANALYST', 'OPENAI_DOT', 'T3'),
}


class FabricError(ValueError):
    pass


def deny_authority(value: Any) -> None:
    if isinstance(value, dict):
        if FORBIDDEN.intersection(value):
            raise FabricError('EXECUTION_AUTHORITY_FIELD')
        for child in value.values():
            deny_authority(child)
    elif isinstance(value, list):
        for child in value:
            deny_authority(child)


def seal(body: dict) -> dict:
    body = deepcopy(body)
    return {**body, 'content_hash': canonical_hash(body)}


def verify(body: dict) -> None:
    if body.get('content_hash') != canonical_hash({k: v for k, v in body.items() if k != 'content_hash'}):
        raise FabricError('CONTENT_HASH_MISMATCH')


class TriAnalystPlane:
    def __init__(self, ledger, *, account_alias: str, qualified_providers: dict | None = None):
        self.ledger = ledger
        self.account_alias = account_alias
        # Only runtime/operator qualification supplies this, never a packet.
        if qualified_providers is None:
            qualified_providers = {}
            for event in ledger.iter(EventKind.COGNITIVE_FABRIC):
                if event.producer == 'vati-account-service' and event.payload.get('record_type') == 'ProviderQualification' and event.payload.get('account_alias') == account_alias:
                    qualified_providers = event.payload.get('providers', {})
        self.qualified = deepcopy(qualified_providers)

    def _rows(self, kind: str) -> list[dict]:
        return [e.payload for e in self.ledger.iter(EventKind.COGNITIVE_FABRIC)
                if e.payload.get('record_type') == kind and e.payload.get('account_alias') == self.account_alias]

    def _write(self, kind: str, body: dict, now_ms: int) -> dict:
        row = seal({**body, 'record_type': kind, 'account_alias': self.account_alias})
        self.ledger.append(make_event(EventKind.COGNITIVE_FABRIC, 'vati-tri-analyst', row,
            event_time_ms=now_ms, received_time_ms=now_ms,
            correlation_id=str(body.get('candidate_id', self.account_alias))))
        return row

    def universe(self, *, instruments: list[dict], broker: str, venue: str, now_ms: int, ttl_ms: int = 60000) -> dict:
        allowed = {'symbol', 'broker_symbol', 'asset_class', 'contract_hash',
                   'market_data_available', 'discovery_allowed', 'execution_supported', 'execution_eligibility_state'}
        if any(set(i) - allowed for i in instruments):
            raise FabricError('UNIVERSE_SCHEMA')
        body = {'snapshot_id': canonical_hash([self.account_alias, instruments, now_ms]),
                'generated_at_ms': now_ms, 'expires_at_ms': now_ms + ttl_ms,
                'broker': broker, 'venue': venue, 'instruments': instruments}
        return self._write('BrokerDiscoveryUniverse', body, now_ms)

    def evidence(self, *, symbol: str, state: dict, source_refs: list[str], now_ms: int, deadline_ms: int) -> dict:
        deny_authority(state)
        if deadline_ms <= now_ms or not source_refs:
            raise FabricError('INVALID_EVIDENCE_BINDING')
        epoch = canonical_hash({'symbol': symbol, 'state': state, 'sources': source_refs, 'captured': now_ms})
        return self._write('MarketEvidenceEnvelope', {'envelope_id': epoch, 'evidence_epoch': epoch,
            'symbol': symbol, 'captured_at_ms': now_ms, 'freshness_deadline_ms': deadline_ms,
            'canonical_source_refs': source_refs, 'state': state}, now_ms)

    def discover(self, signal: dict, *, now_ms: int) -> dict:
        required = {'candidate_id', 'origin_lane', 'provider_product', 'universe_snapshot_id', 'symbol',
                    'venue', 'horizon', 'initial_thesis', 'evidence_refs', 'expires_at_ms'}
        if set(signal) != required or signal['origin_lane'] not in LANES:
            raise FabricError('DISCOVERY_SCHEMA')
        deny_authority(signal)
        if signal['expires_at_ms'] <= now_ms or not signal['initial_thesis'] or not signal['evidence_refs']:
            raise FabricError('INVALID_DISCOVERY')
        identity = IDENTITIES.get(signal['provider_product'])
        if not identity or identity[0] != signal['origin_lane']:
            raise FabricError('PROVIDER_IDENTITY')
        universes = [r for r in self._rows('BrokerDiscoveryUniverse') if r['snapshot_id'] == signal['universe_snapshot_id']]
        if not universes or universes[-1]['expires_at_ms'] <= now_ms:
            raise FabricError('STALE_UNIVERSE')
        universe = universes[-1]
        if signal['venue'] != universe['venue'] or not any(i['symbol'] == signal['symbol'] and i['discovery_allowed'] for i in universe['instruments']):
            raise FabricError('DISCOVERY_NOT_ALLOWED')
        prior = [r for r in self._rows('TradeDiscoverySignal') if r['candidate_id'] == signal['candidate_id']]
        if prior:
            if all(prior[-1].get(k) == v for k, v in signal.items()):
                return prior[-1]
            raise FabricError('CANDIDATE_ID_COLLISION')
        return self._write('TradeDiscoverySignal', signal, now_ms)

    def focus(self, *, candidate_id: str, evidence_epoch: str, reason: str, now_ms: int) -> dict:
        signal = self._signal(candidate_id)
        ev = self._evidence(evidence_epoch)
        if signal['symbol'] != ev['symbol'] or min(signal['expires_at_ms'], ev['freshness_deadline_ms']) <= now_ms:
            raise FabricError('STALE_FOCUS')
        # Same economic setup/epoch never reopens, even after its lease expires.
        key = canonical_hash([signal['symbol'], signal['horizon'], evidence_epoch])
        for row in self._rows('TradeFocusLease'):
            if row['lease_id'] == key:
                return row
        return self._write('TradeFocusLease', {'lease_id': key, 'candidate_id': candidate_id,
            'symbol': signal['symbol'], 'horizon': signal['horizon'], 'evidence_epoch': evidence_epoch,
            'reason_hash': canonical_hash(reason), 'active_lanes': sorted(LANES),
            'expires_at_ms': min(signal['expires_at_ms'], ev['freshness_deadline_ms'])}, now_ms)

    def _signal(self, candidate_id: str) -> dict:
        rows = [r for r in self._rows('TradeDiscoverySignal') if r['candidate_id'] == candidate_id]
        if not rows:
            raise FabricError('UNKNOWN_DISCOVERY')
        return rows[-1]

    def _evidence(self, epoch: str) -> dict:
        rows = [r for r in self._rows('MarketEvidenceEnvelope') if r['evidence_epoch'] == epoch]
        if not rows:
            raise FabricError('UNKNOWN_EVIDENCE')
        verify(rows[-1])
        return rows[-1]

    def first_pass_context(self, *, candidate_id: str, evidence_epoch: str) -> dict:
        # Deliberately no peer output, thesis or discovery narrative.
        signal = self._signal(candidate_id)
        return {'candidate_id': candidate_id, 'symbol': signal['symbol'], 'horizon': signal['horizon'],
                'evidence': deepcopy(self._evidence(evidence_epoch)), 'prior_lane_outputs_seen': []}

    def packet(self, body: dict, *, now_ms: int) -> dict:
        required = {'packet_id', 'candidate_id', 'analyst_lane', 'analysis_lineage_id', 'independence_class',
                    'provider_product', 'model_or_agent_id', 'evidence_epoch', 'evidence_hash',
                    'generated_at_ms', 'expires_at_ms', 'prior_lane_outputs_seen', 'directional_thesis',
                    'supporting_evidence', 'contradicting_evidence', 'missing_inputs', 'uncertainty', 'abstain'}
        optional = {'regime_assessment', 'horizon_assessment', 'strategy_fit', 'feature_interpretation',
            'technical_structure', 'macro_view', 'event_risk', 'liquidity_view', 'execution_quality',
            'cross_asset_view', 'timing_quality', 'setup_quality', 'thesis_health', 'add_on_quality',
            'exit_quality', 'invalidation_conditions', 'confidence'}
        if not isinstance(body, dict) or not required <= set(body) or set(body) - required - optional:
            raise FabricError('PACKET_SCHEMA')
        if 'confidence' in body and (isinstance(body['confidence'], bool) or not isinstance(body['confidence'], (int, float)) or not 0 <= body['confidence'] <= 1):
            raise FabricError('CONFIDENCE_DISPLAY_RANGE')
        deny_authority(body)
        # Validate provider data before lookup, clock comparisons, sealing or persistence.
        # In particular consolidation hashes/compares theses; objects must never enter it.
        identities = {'packet_id','candidate_id','analyst_lane','analysis_lineage_id',
            'independence_class','provider_product','model_or_agent_id','evidence_epoch','evidence_hash'}
        if any(not isinstance(body[key], str) or not 1 <= len(body[key]) <= 200 or not body[key].strip() for key in identities):
            raise FabricError('PACKET_IDENTITY_TYPES')
        text = {'directional_thesis', 'uncertainty'} | (optional - {'confidence','invalidation_conditions'})
        if any(not isinstance(body[key], str) or len(body[key]) > 4000 for key in text if key in body):
            raise FabricError('PACKET_TEXT_TYPES')
        lists = {'prior_lane_outputs_seen','supporting_evidence','contradicting_evidence','missing_inputs','invalidation_conditions'}
        if any(not isinstance(body[key], list) or len(body[key]) > 30 or
               any(not isinstance(item, str) or not 1 <= len(item) <= 2000 or not item.strip() for item in body[key])
               for key in lists if key in body):
            raise FabricError('PACKET_LIST_TYPES')
        if any(type(body[key]) is not int or not 0 <= body[key] <= 9_000_000_000_000_000
               for key in ('generated_at_ms','expires_at_ms')) or type(body['abstain']) is not bool:
            raise FabricError('PACKET_SCALAR_TYPES')
        identity = IDENTITIES.get(body['provider_product'])
        if not identity or identity[:2] != (body['analyst_lane'], body['independence_class']):
            raise FabricError('PROVIDER_IDENTITY')
        if not body['analysis_lineage_id'] or not body['model_or_agent_id']:
            raise FabricError('MISSING_LINEAGE')
        ev = self._evidence(body['evidence_epoch'])
        signal = self._signal(body['candidate_id'])
        if ev['symbol'] != signal['symbol'] or body['evidence_hash'] != ev['content_hash']:
            raise FabricError('EVIDENCE_MISMATCH')
        if not ev['captured_at_ms'] <= body['generated_at_ms'] <= now_ms < body['expires_at_ms']:
            raise FabricError('PACKET_CLOCK')
        if not isinstance(body['abstain'], bool) or not isinstance(body['supporting_evidence'], list) or not isinstance(body['contradicting_evidence'], list) or not isinstance(body['missing_inputs'], list):
            raise FabricError('PACKET_TYPES')
        if body['prior_lane_outputs_seen']:
            raise FabricError('FIRST_PASS_CONTAMINATED')
        if not body['abstain'] and (not body['directional_thesis'] or not body['supporting_evidence']):
            raise FabricError('NOT_SUBSTANTIVE')
        prior = [r for r in self._rows('TradeAnalysisPacket') if r['packet_id'] == body['packet_id']]
        if prior:
            if all(prior[-1].get(k) == v for k, v in body.items()):
                return prior[-1]
            raise FabricError('PACKET_ID_COLLISION')
        # Late T3 observations remain research; they never become live by backdating.
        live = identity[2] == 'T2' and now_ms < min(ev['freshness_deadline_ms'], signal['expires_at_ms'])
        qualification = self.qualified.get(body['provider_product'], {})
        live = live and qualification.get('model_or_agent_id') == body['model_or_agent_id'] and now_ms < qualification.get('expires_at_ms', 0)
        live = live and bool(qualification.get('qualification_ref'))
        if body['provider_product'] == 'muse-glimmer-local':
            live = live and all(qualification.get(k) for k in ('artifact_hash', 'placement_ref', 'sandbox_ref', 'capacity_ref'))
        return self._write('TradeAnalysisPacket', {**{k: 'UNKNOWN' for k in optional - {'confidence', 'invalidation_conditions'}},
            'invalidation_conditions': [], 'confidence': None, **body,
            'provider': 'meta' if body['analyst_lane'] == 'META_ANALYST' else 'openai' if body['analyst_lane'] == 'OPENAI_ANALYST' else 'van',
            'response_hash': canonical_hash(body), 'authority': 'ADVISORY_CANDIDATE', 'live_eligible': bool(live),
            'shared_source_set_hash': canonical_hash(ev['canonical_source_refs']),
            'qualification_ref': qualification.get('qualification_ref')}, now_ms)

    def consolidate(self, *, candidate_id: str, evidence_epoch: str, now_ms: int) -> dict:
        ev = self._evidence(evidence_epoch)
        signal = self._signal(candidate_id)
        packets = [r for r in self._rows('TradeAnalysisPacket') if r['candidate_id'] == candidate_id and r['evidence_epoch'] == evidence_epoch]
        live = [r for r in packets if r['live_eligible'] and not r['abstain'] and now_ms < r['expires_at_ms']
                and now_ms < self.qualified.get(r['provider_product'], {}).get('expires_at_ms', 0)]
        # Distinct identities, logical arms and independently sealed lineages.
        eligible = []
        for p in live:
            if all(p['analyst_lane'] != q['analyst_lane'] and p['analysis_lineage_id'] != q['analysis_lineage_id']
                   and p['independence_class'] != q['independence_class'] for q in eligible):
                eligible.append(p)
        fresh = now_ms < min(ev['freshness_deadline_ms'], signal['expires_at_ms'])
        passed = len(eligible) >= 2 and fresh
        directions = {p['analyst_lane']: p['directional_thesis'] for p in eligible}
        return self._write('ConsolidatedTradeAssessment', {'assessment_id': canonical_hash([candidate_id, evidence_epoch, [p['content_hash'] for p in packets]]),
            'candidate_id': candidate_id, 'evidence_epoch': evidence_epoch,
            'independence_gate_passed': passed, 'contribution_count': len(eligible),
            'contributing_lanes': [p['analyst_lane'] for p in eligible],
            'agreement_map': directions if len(set(directions.values())) == 1 else {},
            'disagreement_map': directions if len(set(directions.values())) > 1 else {},
            'supporting_evidence': [p['supporting_evidence'] for p in packets],
            'contradicting_evidence': [p['contradicting_evidence'] for p in packets],
            'unresolved_questions': [p['missing_inputs'] for p in packets],
            'uncertainty': [p['uncertainty'] for p in packets],
            'provenance': [p['content_hash'] for p in packets],
            'consolidation_checks': {'mode': 'DETERMINISTIC', 'fresh': fresh, 'epoch_matching': True,
                    'disagreement': len(set(directions.values())) > 1},
            'disposition': 'VATI_EVALUATE' if passed else 'WATCH',
            'expires_at_ms': min(ev['freshness_deadline_ms'], signal['expires_at_ms'])}, now_ms)

    def admission(self, *, candidate_id: str, evidence_epoch: str, now_ms: int) -> dict:
        assessment = self.consolidate(candidate_id=candidate_id, evidence_epoch=evidence_epoch, now_ms=now_ms)
        if not assessment['independence_gate_passed']:
            raise FabricError('TWO_LINEAGE_GATE_FAILED')
        return self._write('CognitiveAdmissionEnvelope', {'admission_id': assessment['content_hash'],
            'candidate_id': candidate_id, 'evidence_epoch': evidence_epoch,
            'consolidated_assessment_hash': assessment['content_hash'], 'independence_gate_passed': True,
            'requested_disposition': 'VATI_EVALUATE',
            'allowed_effects': ['REQUEST_DETERMINISTIC_CANDIDATE_EVALUATION'],
            'forbidden_effects': ['CREATE_TRADE_INTENT', 'SET_RISK', 'CREATE_ORDER', 'WIDEN_STOP', 'CHANGE_MANDATE'],
            'expires_at_ms': assessment['expires_at_ms']}, now_ms)

    def evaluate_pending(self, *, evaluators: dict, bars_by_symbol: dict, now_ms: int, candidate_sink=None) -> list[dict]:
        completed = {r['admission_id'] for r in self._rows('VATIDeterministicEvaluation')}
        results = []
        for request in self._rows('CognitiveAdmissionEnvelope'):
            if request['admission_id'] in completed:
                continue
            verify(request)
            signal = self._signal(request['candidate_id'])
            evaluator = evaluators.get(signal['symbol'])
            candidates = ()
            ev = self._evidence(request['evidence_epoch'])
            bars = bars_by_symbol.get(signal['symbol'], ())
            market_hash = canonical_hash([b.as_dict() if hasattr(b, 'as_dict') else str(b) for b in bars])
            same_market = market_hash == ev['state'].get('market_data_hash')
            if now_ms < request['expires_at_ms'] and evaluator is not None and same_market:
                # Existing deterministic strategy/capsule/feature engine only.
                candidates = evaluator.evaluate(bars_by_symbol.get(signal['symbol'], ()), now_ms=now_ms)
                candidates = tuple(c for c in candidates if c.horizon == signal['horizon'] and c.fresh_at(now_ms))
            if candidate_sink is not None:
                for candidate in candidates:
                    candidate_sink(candidate, now_ms=now_ms)
            result = self._write('VATIDeterministicEvaluation', {'admission_id': request['admission_id'],
                'candidate_id': signal['candidate_id'], 'evidence_epoch': request['evidence_epoch'],
                'disposition': 'DETERMINISTIC_CANDIDATE' if candidates else 'WATCH_RESEARCH',
                'reason': 'ADMITTED_STRATEGY_MATCH' if candidates else 'NO_COMPATIBLE_ADMITTED_STRATEGY_OR_STALE',
                'vati_candidate_ids': [c.candidate_id for c in candidates]}, now_ms)
            if any(r.get('admission_id') == request['admission_id'] for r in self._rows('TradeLearningEpisode')):
                completed.add(request['admission_id'])
                results.append(result)
                continue
            self._write('TradeLearningEpisode', {'episode_id': request['admission_id'],
                'admission_id': request['admission_id'], 'candidate_id': signal['candidate_id'],
                'evidence_epoch': request['evidence_epoch'], 'discovery_origin': signal['origin_lane'],
                'consolidation': request['consolidated_assessment_hash'],
                'ex_ante_evidence_hash': ev['content_hash'],
                'analyst_packets': [r['content_hash'] for r in self._rows('TradeAnalysisPacket') if r['candidate_id'] == signal['candidate_id'] and r['evidence_epoch'] == request['evidence_epoch']],
                'VATI_decision': result, 'ex_ante_validity_frozen': True,
                'process_outcome_class': 'UNKNOWN', 'realized_outcome': None,
                'outcome_state': 'PENDING' if candidates else 'NO_TRADE',
                'risk_authority_changed': False}, now_ms)
            completed.add(request['admission_id'])
            results.append(result)
        return results

    def bind_intent(self, candidate, intent, now_ms: int) -> None:
        self._write('CandidateIntentBinding', {'vati_candidate_id': candidate.candidate_id,
            'trade_intent_id': intent.trade_intent_id, 'candidate_hash': candidate.candidate_hash}, now_ms)

    def join_outcomes(self, *, now_ms: int) -> None:
        """Join actual allocator/risk/receipt/review events, never model outcome claims."""
        rows = list(self.ledger.iter())
        bindings = {r['vati_candidate_id']: r['trade_intent_id'] for r in self._rows('CandidateIntentBinding')}
        evaluations = {r['admission_id']: r for r in self._rows('VATIDeterministicEvaluation')}
        previous = {r['episode_id']: r.get('outcome_evidence_hash') for r in self._rows('TradeLearningOutcome')}
        for episode in self._rows('TradeLearningEpisode'):
            evaluation = evaluations.get(episode.get('admission_id'), {})
            candidate_ids = evaluation.get('vati_candidate_ids', [])
            intents = {bindings[c] for c in candidate_ids if c in bindings}
            selected = [e for e in rows if (e.kind == EventKind.ALLOCATION_DECISION and e.payload.get('candidate_id') in candidate_ids)
                or (e.kind in (EventKind.RISK_DECISION, EventKind.EXECUTION_RECEIPT, EventKind.TRADE_REVIEW, EventKind.TCA_RECORD, EventKind.TRADE_EXPERIENCE_ARTIFACT)
                    and e.correlation_id in intents)]
            identity = canonical_hash([e.hash for e in selected])
            if not selected or previous.get(episode['episode_id']) == identity:
                continue
            reviews = [e.payload for e in selected if e.kind == EventKind.TRADE_REVIEW]
            receipts = [e.hash for e in selected if e.kind == EventKind.EXECUTION_RECEIPT]
            from vati.execution.review import Outcome
            observed_classes = {r.get('outcome') for r in reviews}
            process_class = next(iter(observed_classes)) if len(observed_classes) == 1 and observed_classes <= {v.value for v in Outcome} else 'UNKNOWN'
            self._write('TradeLearningOutcome', {'episode_id': episode['episode_id'],
                'candidate_id': episode['candidate_id'], 'evidence_epoch': episode['evidence_epoch'],
                'outcome_evidence_hash': identity, 'evidence_refs': [e.hash for e in selected],
                'risk_decisions': [e.hash for e in selected if e.kind == EventKind.RISK_DECISION],
                'execution_receipts': receipts, 'realized_outcomes': reviews,
                'state': 'REVIEWED' if reviews else 'EXECUTED' if receipts else 'WAITED_OR_REJECTED',
                'process_outcome_class': process_class, 'ex_ante_validity_frozen': True,
                'learning_artifact_refs': [e.hash for e in selected if e.kind == EventKind.TRADE_EXPERIENCE_ARTIFACT],
                'tca_refs': [e.hash for e in selected if e.kind == EventKind.TCA_RECORD],
                'routing_weight_allowed': False, 'risk_multiplier_allowed': False}, now_ms)
        episodes = {r['candidate_id'] for r in self._rows('TradeLearningEpisode')}
        for signal in self._rows('TradeDiscoverySignal'):
            if signal['candidate_id'] not in episodes and signal['expires_at_ms'] <= now_ms:
                admissions = [r for r in self._rows('CognitiveAdmissionEnvelope') if r['candidate_id'] == signal['candidate_id']]
                request = admissions[-1] if admissions else None
                self._write('TradeLearningEpisode', {'episode_id': request['admission_id'] if request else signal['content_hash'],
                    'admission_id': request['admission_id'] if request else None,
                    'candidate_id': signal['candidate_id'], 'evidence_epoch': request['evidence_epoch'] if request else None,
                    'consolidation': request['consolidated_assessment_hash'] if request else None,
                    'discovery_origin': signal['origin_lane'], 'outcome_state': 'EXPIRED_NO_TRADE',
                    'ex_ante_validity_frozen': True, 'realized_outcome': None,
                    'process_outcome_class': 'UNKNOWN'}, now_ms)
                episodes.add(signal['candidate_id'])

    def projection(self) -> dict:
        rows = [e.payload for e in self.ledger.iter(EventKind.COGNITIVE_FABRIC) if e.payload.get('account_alias') == self.account_alias]
        return {'account_alias': self.account_alias, 'authority': 'ADVISORY_CANDIDATE',
                'dispatch_class': 'DOMAIN_LOCAL_ANALYST', 'records': rows[-100:],
                'counts': {k: sum(r['record_type'] == k for r in rows) for k in sorted({r['record_type'] for r in rows})},
                'meta_t2': 'QUALIFICATION_REQUIRED', 'paid_meta': 'DISABLED'}
