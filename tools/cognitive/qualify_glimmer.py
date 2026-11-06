#!/usr/bin/env python3
"""Measure an already-installed loopback local model; never install/activate it."""
import argparse
import json
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'trading'))
from vati.cognition.glimmer_qualification import benchmark, file_hash, hardware_probe, qualify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifact', required=True)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--model-id', required=True)
    parser.add_argument('--license-receipt', required=True)
    parser.add_argument('--placement-receipt', required=True)
    parser.add_argument('--sandbox-receipt', required=True)
    parser.add_argument('--benchmark-evidence')
    parser.add_argument('--loopback-endpoint')
    parser.add_argument('--model-pid', type=int)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    actual = file_hash(args.artifact)
    if actual != args.expected_sha256:
        raise SystemExit('ARTIFACT_SHA256_MISMATCH')
    if bool(args.benchmark_evidence) == bool(args.loopback_endpoint):
        raise SystemExit('Supply existing benchmark evidence or an already running loopback endpoint')
    if args.loopback_endpoint:
        endpoint = urlparse(args.loopback_endpoint)
        if endpoint.scheme != 'http' or endpoint.hostname not in ('127.0.0.1', '::1') or endpoint.username or endpoint.password or endpoint.query:
            raise SystemExit('ONLY_EXPLICIT_LOOPBACK_LOCAL_MODEL_ENDPOINT_ALLOWED')
        if not args.model_pid or args.model_pid <= 0:
            raise SystemExit('LOCAL_MODEL_PID_REQUIRED_FOR_RSS_MEASUREMENT')
        # Disable proxy dispatch entirely: this may never fall back to a cloud route.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                raise ValueError('LOCAL_MODEL_REDIRECT_FORBIDDEN')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        def invoke(request, timeout):
            encoded = json.dumps(request).encode()
            request = urllib.request.Request(args.loopback_endpoint, data=encoded, headers={'Content-Type': 'application/json'}, method='POST')
            with opener.open(request, timeout=timeout) as response:
                data = response.read(1024 * 1024 + 1)
            if len(data) > 1024 * 1024:
                raise ValueError('BOUNDED_RESPONSE_EXCEEDED')
            return json.loads(data)
        def rss():
            for line in Path(f'/proc/{args.model_pid}/status').read_text().splitlines():
                if line.startswith('VmRSS:'):
                    return int(line.split()[1]) * 1024
            return 0
        evidence = benchmark(invoke, model_id=args.model_id, artifact_sha256=actual, model_rss_probe=rss)
        Path(args.output + '.benchmark.json').write_text(json.dumps(evidence, indent=2)+'\n')
    else:
        evidence = json.loads(Path(args.benchmark_evidence).read_text())
    result = qualify(artifact_path=args.artifact, expected_sha256=args.expected_sha256, model_id=args.model_id,
        license_receipt=json.loads(Path(args.license_receipt).read_text()),
        placement_receipt=json.loads(Path(args.placement_receipt).read_text()),
        sandbox_receipt=json.loads(Path(args.sandbox_receipt).read_text()), hardware=hardware_probe(),
        benchmark_evidence=evidence)
    Path(args.output).write_text(json.dumps(result, indent=2)+'\n')
    print(result['state'])
    return 0 if not result['failures'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
