import json
import time
from copy import deepcopy

import pytest

from vati.cognition.glimmer_qualification import benchmark, file_hash, hardware_probe, qualify


def inputs(tmp_path):
    artifact = tmp_path / 'fixture.gguf'
    artifact.write_bytes(b'qualification-test-artifact-not-model-weights')
    sha = file_hash(artifact)
    def invocation(request, timeout):
        assert request['model'] == 'glimmer-test'
        return {'model': 'glimmer-test', 'artifact_sha256': sha,
                'choices': [{'message': {'content': json.dumps({'abstain': True, 'reason': 'insufficient evidence'})}}]}
    evidence = benchmark(invocation, model_id='glimmer-test', artifact_sha256=sha, model_rss_probe=lambda: 100)
    now = int(time.time() * 1000)
    return {'artifact_path': artifact, 'expected_sha256': sha, 'model_id': 'glimmer-test',
        'license_receipt': {'approved': True, 'approval_ref': 'fixture-license', 'artifact_sha256': sha},
        'placement_receipt': {'state': 'ADMITTED', 'host_id': 'test-gpu-worker', 'governor_receipt_ref': 'fixture-placement',
            'expires_at_ms': now + 100000, 'reserved_ram_bytes': 1000, 'artifact_sha256': sha},
        'sandbox_receipt': {'qualified': True, 'evidence_ref': 'fixture-sandbox', 'host_id': 'test-gpu-worker',
            'artifact_sha256': sha, 'non_root': True, 'credential_isolation': True, 'retention_policy': True,
            'logging_policy': True, 'tool_isolation': True, 'admitted_data_classes': ['PUBLIC', 'INTERNAL_SANITIZED']},
        'hardware': {'host_id': 'test-gpu-worker', 'ram_available_bytes': 2000},
        'benchmark_evidence': evidence}


def test_measured_fixture_benchmark_passes_local_checks_without_live_claim_or_activation(tmp_path):
    data = inputs(tmp_path)
    result = qualify(**data)
    assert result['state'] == 'LOCAL_CHECKS_PASSED_GOVERNED_ADMISSION_PENDING'
    assert result['live_qualified'] is False
    assert result['activation_performed'] is False
    assert data['benchmark_evidence']['sample_count'] == 20
    assert data['benchmark_evidence']['success_count'] == 20
    assert all(row['latency_ms'] >= 0 for row in data['benchmark_evidence']['samples'])
    assert result['artifact_hash'] == file_hash(data['artifact_path'])


@pytest.mark.parametrize('part,change,reason', [
    ('license_receipt', {'approved': False}, 'LICENSE_REVIEW_REQUIRED'),
    ('placement_receipt', {'state': 'PENDING'}, 'PLACEMENT_GOVERNOR_ADMISSION_REQUIRED'),
    ('placement_receipt', {'host_id': 'oracle-admin'}, 'HOST_EXCLUDED_OR_UNKNOWN'),
    ('placement_receipt', {'host_id': 'van-trading-core'}, 'PROTECTED_HOST_CAPACITY_GATE'),
    ('placement_receipt', {'artifact_sha256': 'wrong'}, 'PLACEMENT_ARTIFACT_IDENTITY_MISMATCH'),
    ('sandbox_receipt', {'credential_isolation': False}, 'SANDBOX_PRIVACY_CONTROLS_REQUIRED'),
    ('sandbox_receipt', {'admitted_data_classes': ['PUBLIC']}, 'DATA_CLASS_NOT_ADMITTED'),
    ('hardware', {'ram_available_bytes': 10}, 'INSUFFICIENT_MEASURED_RAM'),
    ('hardware', {'host_id': 'other-machine'}, 'HARDWARE_HOST_IDENTITY_MISMATCH'),
    ('benchmark_evidence', {'success_count': 0}, 'BENCHMARK_EVIDENCE_HASH_MISMATCH'),
])
def test_independent_qualification_gates_fail_closed(tmp_path, part, change, reason):
    data = inputs(tmp_path)
    data[part].update(change)
    result = qualify(**data)
    assert result['state'] == 'BLOCKED'
    assert reason in result['failures']
    assert result['live_qualified'] is False


def test_artifact_pin_mismatch_is_blocked(tmp_path):
    data = inputs(tmp_path)
    data['artifact_path'].write_bytes(b'changed')
    result = qualify(**data)
    assert 'ARTIFACT_SHA256_MISMATCH' in result['failures']
    assert 'BENCHMARK_IDENTITY_MISMATCH' in result['failures']


def test_benchmark_identity_drift_and_failures_are_measured_not_fallbacks():
    def invalid(_request, _deadline):
        return {'model': 'other'}
    result = benchmark(invalid, model_id='expected', artifact_sha256='a' * 64)
    assert result['success_count'] == 0
    assert all('MODEL_ARTIFACT_IDENTITY_MISMATCH' in r['error'] for r in result['samples'])
    assert result['paid_meta_route_used'] is False


def test_hardware_probe_measures_real_local_resources_without_claiming_gpu():
    result = hardware_probe()
    assert result['ram_total_bytes'] > 0
    assert result['ram_available_bytes'] > 0
    assert result['cpu_count'] > 0
    assert result['gpu_state'] == 'NOT_QUALIFIED'


def test_benchmark_budget_is_bounded():
    with pytest.raises(ValueError, match='BOUNDED'):
        benchmark(lambda *_: {}, model_id='test', artifact_sha256='a' * 64, samples=1000)


def test_operator_cli_measures_real_loopback_contract_without_cloud_fallback(tmp_path):
    import os
    import socket
    import subprocess
    import sys
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from pathlib import Path
    data = inputs(tmp_path)
    sha = data['expected_sha256']
    count = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            count.append(request)
            response = json.dumps({'model': 'glimmer-test', 'artifact_sha256': sha,
                'choices': [{'message': {'content': '{"abstain":true,"reason":"fixture only"}'}}]}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response)))
            self.end_headers()
            self.wfile.write(response)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        data['placement_receipt'].update(host_id=socket.gethostname(), reserved_ram_bytes=1024**3)
        # A synthetic receipt for the loopback contract test, never live admission.
        if socket.gethostname() in ('dial-control', 'van-trading-core', 'vekl-worker'):
            data['placement_receipt']['owner_capacity_exception_ref'] = 'fixture-local-contract-only'
        data['sandbox_receipt']['host_id'] = socket.gethostname()
        receipts = []
        for key in ('license_receipt', 'placement_receipt', 'sandbox_receipt'):
            path = tmp_path / (key + '.json')
            path.write_text(json.dumps(data[key]))
            receipts += ['--' + key.replace('_', '-'), str(path)]
        output = tmp_path / 'qualification.json'
        script = Path(__file__).resolve().parents[2] / 'tools/cognitive/qualify_glimmer.py'
        result = subprocess.run([sys.executable, str(script), '--artifact', str(data['artifact_path']),
            '--expected-sha256', sha, '--model-id', 'glimmer-test', *receipts,
            '--loopback-endpoint', f'http://127.0.0.1:{server.server_port}/v1/chat/completions',
            '--model-pid', str(os.getpid()), '--output', str(output)], capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        qualification = json.loads(output.read_text())
        measured = json.loads(Path(str(output) + '.benchmark.json').read_text())
        assert qualification['live_qualified'] is False
        assert qualification['activation_performed'] is False
        assert measured['success_count'] == 20
        assert measured['sampled_max_model_rss_bytes'] > 0
        assert len(count) == 20
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
