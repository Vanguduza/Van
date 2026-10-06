"""Local Glimmer qualification evidence, without downloads, activation or paid routes.

Passing local checks produces a candidate receipt. Placement/license/sandbox
admission remain governed external evidence; this module cannot self-admit a host.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import socket
import time
from pathlib import Path
from typing import Callable

from vati.core.canonical import canonical_hash


def file_hash(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def hardware_probe() -> dict:
    mem = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, _, value = line.partition(':')
        mem[key] = int(value.strip().split()[0]) * 1024
    return {'host_id': socket.gethostname(), 'architecture': platform.machine(), 'cpu_count': os.cpu_count(),
            'ram_total_bytes': mem['MemTotal'], 'ram_available_bytes': mem['MemAvailable'],
            'gpu_state': 'NOT_QUALIFIED', 'probe_source': '/proc/meminfo+platform',
            'observed_at_ms': int(time.time() * 1000)}


def benchmark(invoke: Callable[[dict, float], dict], *, model_id: str, artifact_sha256: str,
              samples: int = 20, timeout_seconds: float = 5, model_rss_probe: Callable[[], int] | None = None) -> dict:
    if not 20 <= samples <= 100 or not 0 < timeout_seconds <= 30:
        raise ValueError('BOUNDED_BENCHMARK_BUDGET_REQUIRED')
    rows = []
    for index in range(samples):
        request = {'model': model_id, 'temperature': 0, 'max_tokens': 128,
                   'messages': [{'role': 'user', 'content':
                    'Return only JSON {"abstain":true,"reason":"insufficient evidence"}. '
                    'No broker/risk/order fields. Qualification sample ' + str(index)}]}
        start = time.monotonic_ns()
        error, parsed = None, None
        try:
            result = invoke(request, timeout_seconds)
            if result.get('model') != model_id or result.get('artifact_sha256') != artifact_sha256:
                raise ValueError('MODEL_ARTIFACT_IDENTITY_MISMATCH')
            parsed = json.loads(result['choices'][0]['message']['content'])
            if set(parsed) != {'abstain', 'reason'} or parsed['abstain'] is not True or not isinstance(parsed['reason'], str):
                raise ValueError('BENCHMARK_RESPONSE_SCHEMA')
        except Exception as exc:  # a failed sample is evidence, never a successful fallback
            error = type(exc).__name__ + ':' + str(exc)[:160]
        elapsed = (time.monotonic_ns() - start) / 1_000_000
        if elapsed > timeout_seconds * 1000:
            error = 'DEADLINE_EXCEEDED'
        rss = model_rss_probe() if model_rss_probe else None
        rows.append({'sample': index, 'request_hash': canonical_hash(request), 'response_hash': canonical_hash(parsed) if parsed else None,
                     'latency_ms': round(elapsed, 3), 'error': error, 'sampled_model_rss_bytes': rss})
    ordered = sorted(r['latency_ms'] for r in rows)
    body = {'record_type': 'GlimmerBenchmarkEvidence', 'model_id': model_id,
            'artifact_sha256': artifact_sha256, 'sample_count': samples, 'timeout_ms': timeout_seconds * 1000,
            'success_count': sum(r['error'] is None for r in rows),
            'p95_latency_ms': ordered[math.ceil(.95 * len(ordered)) - 1],
            'sampled_max_model_rss_bytes': max((r['sampled_model_rss_bytes'] or 0 for r in rows), default=0),
            'samples': rows, 'measured_at_ms': int(time.time() * 1000),
            'model_activation_performed': False, 'paid_meta_route_used': False}
    return {**body, 'evidence_hash': canonical_hash(body)}


def qualify(*, artifact_path: str | Path, expected_sha256: str, model_id: str,
            license_receipt: dict, placement_receipt: dict, sandbox_receipt: dict,
            hardware: dict, benchmark_evidence: dict, data_class: str = 'INTERNAL_SANITIZED',
            now_ms: int | None = None) -> dict:
    now = int(time.time() * 1000) if now_ms is None else now_ms
    actual = file_hash(artifact_path)  # actual immutable local bytes, no network/download
    failures = []
    if actual != expected_sha256:
        failures.append('ARTIFACT_SHA256_MISMATCH')
    if not license_receipt.get('approved') or not license_receipt.get('approval_ref') or license_receipt.get('artifact_sha256') != actual:
        failures.append('LICENSE_REVIEW_REQUIRED')
    if placement_receipt.get('state') != 'ADMITTED' or not placement_receipt.get('governor_receipt_ref') or placement_receipt.get('expires_at_ms', 0) <= now:
        failures.append('PLACEMENT_GOVERNOR_ADMISSION_REQUIRED')
    host = placement_receipt.get('host_id')
    if placement_receipt.get('artifact_sha256') != actual:
        failures.append('PLACEMENT_ARTIFACT_IDENTITY_MISMATCH')
    if hardware.get('host_id') != host:
        failures.append('HARDWARE_HOST_IDENTITY_MISMATCH')
    if not host or host == 'oracle-admin':
        failures.append('HOST_EXCLUDED_OR_UNKNOWN')
    if host in ('dial-control', 'van-trading-core', 'vekl-worker') and not placement_receipt.get('owner_capacity_exception_ref'):
        failures.append('PROTECTED_HOST_CAPACITY_GATE')
    reserved = placement_receipt.get('reserved_ram_bytes', 0)
    if reserved <= 0 or hardware.get('ram_available_bytes', 0) < reserved:
        failures.append('INSUFFICIENT_MEASURED_RAM')
    if sandbox_receipt.get('artifact_sha256') != actual:
        failures.append('SANDBOX_ARTIFACT_IDENTITY_MISMATCH')
    if not sandbox_receipt.get('qualified') or not sandbox_receipt.get('evidence_ref') or sandbox_receipt.get('host_id') != host:
        failures.append('HOST_SANDBOX_QUALIFICATION_REQUIRED')
    if not all(sandbox_receipt.get(k) for k in ('non_root', 'credential_isolation', 'retention_policy', 'logging_policy', 'tool_isolation')):
        failures.append('SANDBOX_PRIVACY_CONTROLS_REQUIRED')
    if data_class not in ('PUBLIC', 'INTERNAL_SANITIZED', 'RESTRICTED', 'SECRET_HIGH_SENSITIVITY'):
        failures.append('UNKNOWN_DATA_CLASS')
    if data_class not in sandbox_receipt.get('admitted_data_classes', []):
        failures.append('DATA_CLASS_NOT_ADMITTED')
    body = {k: v for k, v in benchmark_evidence.items() if k != 'evidence_hash'}
    if benchmark_evidence.get('evidence_hash') != canonical_hash(body):
        failures.append('BENCHMARK_EVIDENCE_HASH_MISMATCH')
    if benchmark_evidence.get('model_id') != model_id or benchmark_evidence.get('artifact_sha256') != actual:
        failures.append('BENCHMARK_IDENTITY_MISMATCH')
    samples = benchmark_evidence.get('samples', [])
    if not 20 <= len(samples) <= 100 or benchmark_evidence.get('sample_count') != len(samples) or any(r.get('error') or not r.get('response_hash') for r in samples):
        failures.append('MEASURED_BENCHMARK_REQUIRED')
    if benchmark_evidence.get('success_count') != len(samples) or benchmark_evidence.get('p95_latency_ms', float('inf')) > placement_receipt.get('max_t2_latency_ms', 5000):
        failures.append('T2_LATENCY_OR_RELIABILITY_GATE')
    rss = benchmark_evidence.get('sampled_max_model_rss_bytes', 0)
    if rss <= 0 or rss > reserved:
        failures.append('MODEL_MEMORY_MEASUREMENT_GATE')
    if benchmark_evidence.get('measured_at_ms', 0) > now or now - benchmark_evidence.get('measured_at_ms', 0) > 86400000:
        failures.append('BENCHMARK_STALE_OR_FUTURE')
    result = {'record_type': 'GlimmerQualificationCandidate', 'provider_product': 'muse-glimmer-local',
        'model_or_agent_id': model_id, 'artifact_hash': actual,
        'license_receipt_hash': canonical_hash(license_receipt), 'placement_receipt_hash': canonical_hash(placement_receipt),
        'sandbox_receipt_hash': canonical_hash(sandbox_receipt), 'hardware_evidence_hash': canonical_hash(hardware),
        'benchmark_evidence_hash': benchmark_evidence.get('evidence_hash'), 'data_class': data_class,
        'state': 'LOCAL_CHECKS_PASSED_GOVERNED_ADMISSION_PENDING' if not failures else 'BLOCKED',
        'failures': failures, 'live_qualified': False, 'activation_performed': False,
        'evaluated_at_ms': now, 'authority': 'QUALIFICATION_EVIDENCE_ONLY'}
    return {**result, 'qualification_candidate_hash': canonical_hash(result)}
