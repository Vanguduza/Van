"""Operator-qualified first-pass packet transport, separate from the T0 account loop."""
from __future__ import annotations
import json
import time
import re
from urllib.parse import urlsplit
from vati.cognition.fabric import IDENTITIES, FabricError, TriAnalystPlane
from vati.cognition.invokers import resolve_credential, MAX_RESPONSE_BYTES
from vati.core.canonical import canonical_hash


class PacketTransport:
    def __call__(self, *, url, headers, body, timeout_s):
        import httpx
        # Server-owned endpoint; no environment proxy, redirect, retry or unbounded body.
        deadline = time.monotonic() + timeout_s
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=timeout_s) as client:
            with client.stream('POST', url, headers=headers, content=body) as response:
                raw = bytearray()
                for chunk in response.iter_bytes():
                    if time.monotonic() >= deadline:
                        raise FabricError('PACKET_TRANSPORT_DEADLINE')
                    raw.extend(chunk)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise FabricError('PACKET_RESPONSE_TOO_LARGE')
                return response.status_code, bytes(raw)


class PacketProducer:
    def __init__(self, plane: TriAnalystPlane, *, sources: list[dict], clock, transport=None, secrets_dir='', should_stop=None):
        if len(sources) > 3:
            raise FabricError('PACKET_SOURCE_LIMIT')
        self.plane, self.clock = plane, clock
        self.transport = transport or PacketTransport()
        self.secrets_dir = secrets_dir
        self.should_stop = should_stop or (lambda: False)
        self.sources = []
        seen_sources, seen_lineages = set(), set()
        for source in sources:
            allowed = {'enabled', 'provider_product', 'source_id', 'analysis_lineage_id', 'endpoint', 'credential_ref', 'timeout_s'}
            if set(source) - allowed:
                raise FabricError('PACKET_SOURCE_SCHEMA')
            if source.get('enabled') is not True:
                continue
            identity = IDENTITIES.get(source.get('provider_product'))
            if not identity or identity[2] != 'T2':
                raise FabricError('PACKET_SOURCE_NOT_T2')
            if not source.get('source_id') or not source.get('analysis_lineage_id'):
                raise FabricError('PACKET_SOURCE_IDENTITY_REQUIRED')
            if source['source_id'] in seen_sources or source['analysis_lineage_id'] in seen_lineages:
                raise FabricError('PACKET_SOURCE_INDEPENDENCE')
            endpoint = urlsplit(source.get('endpoint', ''))
            if not endpoint.hostname or endpoint.username or endpoint.password or endpoint.fragment or endpoint.query:
                raise FabricError('PACKET_SOURCE_ENDPOINT')
            if endpoint.scheme != 'https' and not (endpoint.scheme == 'http' and endpoint.hostname in ('127.0.0.1', '::1', 'localhost')):
                raise FabricError('PACKET_SOURCE_ENDPOINT')
            timeout = source.get('timeout_s', 5)
            if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 5:
                raise FabricError('PACKET_SOURCE_TIMEOUT')
            seen_sources.add(source['source_id']); seen_lineages.add(source['analysis_lineage_id'])
            self.sources.append({**source, 'timeout_s': timeout})

    def poll(self):
        plane, now = self.plane, self.clock()
        attempted = {r['attempt_id'] for r in plane._rows('PacketTransportAttempt')}
        admissions = {(r['candidate_id'], r['evidence_epoch']) for r in plane._rows('CognitiveAdmissionEnvelope')}
        evidence = plane._rows('MarketEvidenceEnvelope')
        results = []
        calls = 0
        # Bounded work; newest candidate/epoch wins, already attempted sources never repeat.
        for signal in plane._rows('TradeDiscoverySignal')[-10:]:
            if self.should_stop() or calls >= 3:
                break
            epochs = [e for e in evidence if e['symbol'] == signal['symbol'] and now < min(e['freshness_deadline_ms'], signal['expires_at_ms'])]
            if not epochs:
                continue
            ev = epochs[-1]
            if (signal['candidate_id'], ev['evidence_epoch']) in admissions:
                continue
            context = plane.first_pass_context(candidate_id=signal['candidate_id'], evidence_epoch=ev['evidence_epoch'])
            # The cloud boundary exposes only the account runtime's hash/ref projection.
            # Custom/raw evidence state is not silently reclassified as sanitized.
            hashes = {'market_data_hash','state_hash','contract_hash','multi_timeframe_state_hash','strategy_context_hash','portfolio_context_hash'}
            state = ev['state']
            if 'market_data_hash' not in state or not 1 <= len(ev['canonical_source_refs']) <= 30:
                continue
            if 'VTIL_activation_ref' in state and (not isinstance(state['VTIL_activation_ref'],str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}',state['VTIL_activation_ref'])):
                continue
            if set(state) - hashes - {'VTIL_activation_ref'} or not all(isinstance(value,str) and re.fullmatch(r'[a-f0-9]{64}',value) for key,value in state.items() if key in hashes):
                continue
            if not all(isinstance(ref,str) and re.fullmatch(r'[a-f0-9]{64}',ref) for ref in ev['canonical_source_refs']):
                continue
            for source in self.sources:
                if self.should_stop() or calls >= 3:
                    break
                now = self.clock()
                deadline = min(ev['freshness_deadline_ms'], signal['expires_at_ms'])
                if now >= deadline:
                    break
                product = source['provider_product']; qualification = plane.qualified.get(product, {})
                if not (qualification.get('source_id') == source['source_id'] and qualification.get('analysis_lineage_id') == source['analysis_lineage_id'] and qualification.get('qualification_ref') and 'INTERNAL_SANITIZED' in qualification.get('approved_data_classes', []) and qualification.get('model_or_agent_id') and now < qualification.get('expires_at_ms', 0)):
                    continue
                if product == 'muse-glimmer-local' and not all(qualification.get(k) for k in ('artifact_hash', 'placement_ref', 'sandbox_ref', 'capacity_ref')):
                    continue
                attempt = canonical_hash([plane.account_alias, signal['candidate_id'], ev['evidence_epoch'], source['source_id']])
                if attempt in attempted:
                    continue
                focus = plane.focus(candidate_id=signal['candidate_id'], evidence_epoch=ev['evidence_epoch'], reason='qualified packet source', now_ms=now)
                if focus['candidate_id'] != signal['candidate_id']:
                    continue
                audit = {'attempt_id': attempt, 'candidate_id': signal['candidate_id'], 'evidence_epoch': ev['evidence_epoch'], 'source_id': source['source_id'], 'provider_product': product, 'qualification_ref': qualification['qualification_ref'], 'request_context_hash': canonical_hash(context)}
                plane._write('PacketTransportAttempt', {**audit, 'state': 'STARTED'}, now)
                attempted.add(attempt)
                calls += 1
                try:
                    credential = resolve_credential(source.get('credential_ref', ''), secrets_dir=self.secrets_dir)
                    request = {'schema_version': 1, 'contract': 'COGNITIVE_FABRIC_FIRST_PASS_PACKET', 'data_class':'INTERNAL_SANITIZED', 'provider_approval_required':True, 'context': context, 'source_id': source['source_id'], 'provider_product': product, 'model_or_agent_id': qualification['model_or_agent_id'], 'analysis_lineage_id': source['analysis_lineage_id']}
                    headers = {'Content-Type':'application/json', **({'Authorization':'Bearer '+credential} if credential else {})}
                    status, raw = self.transport(url=source['endpoint'], headers=headers, body=json.dumps(request).encode(), timeout_s=min(source['timeout_s'], (deadline-now)/1000))
                    if status != 200 or len(raw) > MAX_RESPONSE_BYTES or (credential and credential.encode() in raw):
                        raise FabricError('PACKET_RESPONSE_REFUSED')
                    packet = json.loads(raw)
                    if not isinstance(packet, dict) or any(packet.get(k) != v for k,v in {'candidate_id':signal['candidate_id'], 'evidence_epoch':ev['evidence_epoch'], 'evidence_hash':ev['content_hash'], 'provider_product':product, 'model_or_agent_id':qualification['model_or_agent_id'], 'analysis_lineage_id':source['analysis_lineage_id']}.items()):
                        raise FabricError('PACKET_RESPONSE_IDENTITY')
                    accepted = plane.packet(packet, now_ms=self.clock())
                    result = plane._write('PacketTransportResult', {**audit, 'state':'ACCEPTED', 'packet_hash':accepted['content_hash']}, self.clock())
                except Exception as exc:
                    # Fixed codes only; transport error text can contain URLs or credentials.
                    reason = str(exc) if isinstance(exc, FabricError) else 'PACKET_TRANSPORT_OR_JSON_REFUSED'
                    result = plane._write('PacketTransportResult', {**audit, 'state':'REFUSED', 'reason':reason}, self.clock())
                results.append(result)
            if any(r['state']=='ACCEPTED' and r['candidate_id']==signal['candidate_id'] for r in results):
                try:
                    plane.admission(candidate_id=signal['candidate_id'], evidence_epoch=ev['evidence_epoch'], now_ms=self.clock())
                except FabricError:
                    pass  # Dissent/absence never bypasses the authoritative two-lineage gate.
        return results
