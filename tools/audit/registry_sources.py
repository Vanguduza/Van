"""Prepare a source-bound owner registry refresh after the implementation freeze.

The caller supplies the freeze manifest and reviewed citation anchors. This tool
never silently re-labels old unlocatable evidence as current. Frozen baseline
objects and historical receipts are not modified. Output defaults to a separate
candidate directory; applying it to VAN is an explicit final operation.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
GATEWAY = 'android/app/src/main/java/com/dial/van/gateway/VanGatewayClient.kt'


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text())


def save(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def endpoint_frontend_access(authentication: str) -> str:
    if authentication.startswith('ATTESTED_ARTIFACT_PROVIDER:'):
        return 'ATTESTED_ARTIFACT_PROVIDER_SERVICE_ONLY'
    if authentication.startswith('INTERNAL_CONTROL:'):
        return 'HERMES_SERVICE_ONLY'
    return 'DIRECT_OWNER_ROUTE'


def service_endpoint(authentication: str) -> bool:
    return endpoint_frontend_access(authentication).endswith('SERVICE_ONLY')


def freeze_files(document):
    files = document.get('files', document)
    if isinstance(files, list):
        return {v.get('path', v.get('file')): v['sha256'] for v in files}
    if isinstance(files, dict):
        return {k: v.get('sha256') if isinstance(v, dict) else v for k, v in files.items()}
    raise ValueError('Unsupported source freeze manifest')


def verify_freeze(files):
    changed = [file for file, sha in files.items()
               if not file or not (ROOT / file).is_file() or digest(ROOT / file) != sha]
    if changed:
        raise RuntimeError('Source freeze is not stable: ' + ', '.join(changed[:12]))


class Refresh:
    def __init__(self, anchors):
        self.anchors = anchors
        self.cache = {}
        self.unresolved = {}
        self.refreshed = 0
        self.calls = {}

    def scan_calls(self, rows):
        """Conservative receiver scan; ambiguous short variable names are excluded.

        Previously reviewed receivers provide namespace seeds only. Every output
        still has to be an actual current invocation, and explicit current type
        declarations take precedence. The final registry receives a static-source
        qualifier rather than any runtime claim.
        """
        seeds = {}
        for row in rows:
            for ref in row['endpoint_refs']:
                for call in ref['android_callsites']:
                    if call['invocation_kind'] == 'direct_client_method':
                        key = (call['file'], call['receiver'])
                        seeds.setdefault(key, set()).add(call['namespace'])
        symbols = {(ref.get('client_namespace'), ref.get('client_symbol'))
                   for row in rows for ref in row['endpoint_refs']
                   if ref.get('client_namespace') and ref.get('client_symbol')}
        app_file = 'android/app/src/main/java/com/dial/van/VanApplication.kt'
        gateway_type = self.matches(app_file, r'\bgatewayClient\s*:\s*VanGatewayClient\b')
        if len(gateway_type) != 1:
            raise RuntimeError('VanApplication gatewayClient type declaration is ambiguous')
        app_type_citation = {'file': app_file, 'line': gateway_type[0], 'ref': 'WORKSPACE_PATCH',
                             'sha256': self.source(app_file)[1]}
        for path in sorted((ROOT / 'android/app/src/main/java').rglob('*.kt')):
            file = str(path.relative_to(ROOT))
            lines, sha = self.source(file)
            receiver_types, type_citations = {}, {}
            if file == GATEWAY:
                # Self-invocations carry the enclosing production class type.
                # Nested DialDevClient methods have their own explicit namespace
                # and are not inferred from this outer declaration.
                declarations = self.matches(file, r'^class VanGatewayClient\(')
                receiver_types['this'] = {'VanGatewayClient'}
                type_citations[('this', 'VanGatewayClient')] = {
                    'file': file, 'line': declarations[0], 'ref': 'WORKSPACE_PATCH', 'sha256': sha}
            for i, line in enumerate(lines, 1):
                if line.lstrip().startswith(('//', '*')):
                    continue
                for match in re.finditer(r'\b(\w+)\s*:\s*(VanGatewayClient(?:\.DialDevClient)?)\b', line):
                    name, namespace = match.groups()
                    receiver_types.setdefault(name, set()).add(namespace)
                    type_citations[(name, namespace)] = {'file': file, 'line': i,
                        'ref': 'WORKSPACE_PATCH', 'sha256': sha}
            # Qualified app property calls carry the production property type.
            app_names = set()
            for line in lines:
                app_names.update(re.findall(r'\b(\w+)\s*:\s*VanApplication\b', line))
            for app_name in app_names:
                receiver_types[app_name + '.gatewayClient'] = {'VanGatewayClient'}
                type_citations[(app_name + '.gatewayClient', 'VanGatewayClient')] = app_type_citation
                receiver_types[app_name + '.gatewayClient.dialDev'] = {'VanGatewayClient.DialDevClient'}
                type_citations[(app_name + '.gatewayClient.dialDev', 'VanGatewayClient.DialDevClient')] = app_type_citation
            for (seed_file, receiver), namespaces in seeds.items():
                if seed_file == file and receiver not in receiver_types and len(namespaces) == 1:
                    receiver_types[receiver] = namespaces
                    # Reviewers must locate changed/inferred receiver declarations.
                    for row in rows:
                        for ref in row['endpoint_refs']:
                            for call in ref['android_callsites']:
                                if (call['file'], call['receiver']) == (file, receiver):
                                    cite = copy.deepcopy(call['receiver_type_citation'])
                                    self.citation(cite)
                                    type_citations[(receiver, call['namespace'])] = cite
                                    break
            for i, line in enumerate(lines, 1):
                if line.lstrip().startswith(('//', '*')):
                    continue
                for match in re.finditer(r'\b([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\.([A-Za-z_]\w*)\s*\(', line):
                    receiver, symbol = match.groups()
                    namespace_options = receiver_types.get(receiver, set())
                    if len(namespace_options) != 1:
                        continue
                    namespace = next(iter(namespace_options))
                    if (namespace, symbol) not in symbols:
                        continue
                    cite = type_citations.get((receiver, namespace))
                    if not cite:
                        continue
                    self.calls.setdefault((namespace, symbol), []).append({
                        'file': file, 'line': i, 'ref': 'WORKSPACE_PATCH', 'sha256': sha,
                        'receiver': receiver, 'symbol': symbol, 'namespace': namespace,
                        'invocation_kind': 'direct_client_method',
                        'receiver_type_citation': copy.deepcopy(cite)})

    def source(self, file):
        if file not in self.cache:
            path = ROOT / file
            self.cache[file] = (path.read_text().splitlines(), digest(path))
        return self.cache[file]

    def matches(self, file, pattern):
        lines, _ = self.source(file)
        return [i + 1 for i, line in enumerate(lines)
                if not line.lstrip().startswith(('//', '*')) and re.search(pattern, line)]

    def line_for(self, citation, pattern=None):
        file = citation['file']
        lines, sha = self.source(file)
        if citation.get('sha256') == sha and 0 < citation['line'] <= len(lines):
            if not pattern or re.search(pattern, lines[citation['line'] - 1]):
                return citation['line']
        key = f"{file}:{citation['line']}"
        anchor = self.anchors.get(key)
        if anchor and (not pattern or all(re.search(pattern, lines[i-1]) for i in self.matches(file, anchor['pattern']))):
            pattern = anchor['pattern']
        else:
            anchor = None
        if pattern:
            matches = self.matches(file, pattern)
            if anchor and anchor.get('occurrence'):
                occurrence = anchor['occurrence']
                return matches[occurrence - 1] if 0 < occurrence <= len(matches) else None
            if len(matches) == 1:
                return matches[0]
            # An unchanged citation at an exact invocation remains unambiguous.
            if citation.get('sha256') == sha and citation['line'] in matches:
                return citation['line']
            return None
        if citation.get('sha256') == sha and 0 < citation['line'] <= len(lines):
            return citation['line']
        return None

    def citation(self, citation, pattern=None):
        if citation.get('ref') != 'WORKSPACE_PATCH':
            return citation
        line = self.line_for(citation, pattern)
        if line is None:
            key = f"{citation['file']}:{citation['line']}"
            self.unresolved[key] = {'file': citation['file'], 'old_line': citation['line'],
                                    'pattern_hint': pattern,
                                    'reason': 'Changed source requires a reviewed unique anchor'}
            return citation
        citation['line'] = line
        citation['sha256'] = self.source(citation['file'])[1]
        self.refreshed += 1
        return citation

    def walk(self, value, preserve=False):
        if isinstance(value, dict):
            # A baseline or historical snapshot remains byte-for-byte semantic evidence.
            if preserve:
                return
            if {'file', 'line', 'ref'} <= set(value):
                pattern = None
                if value.get('receiver') and value.get('symbol'):
                    expression = value['symbol'] if value['receiver'] == 'this' else value['receiver'] + '.' + value['symbol']
                    pattern = re.escape(expression) + r'\s*\('
                self.citation(value, pattern)
            for key, child in value.items():
                self.walk(child, preserve=key.startswith('baseline') or key.startswith('historical'))
        elif isinstance(value, list) and not preserve:
            for child in value:
                self.walk(child)

    def declaration(self, namespace, symbol):
        if not namespace or not symbol:
            return []
        indentation = 8 if namespace == 'VanGatewayClient.DialDevClient' else 4
        pattern = '^' + ' ' * indentation + r'(?:(?:private|public|internal|protected|override|suspend)\s+)*fun\s+' + re.escape(symbol) + r'\s*\('
        matches = self.matches(GATEWAY, pattern)
        if not matches:
            raise RuntimeError(f'Client declaration is missing: {namespace}.{symbol}')
        # A Kotlin method can intentionally expose overloads. Preserve every
        # exact declaration in its already-known lexical client namespace.
        return [{'file': GATEWAY, 'line': line, 'ref': 'WORKSPACE_PATCH',
                 'sha256': self.source(GATEWAY)[1]} for line in matches]


def demote_verification(row):
    implementation = row['current_implementation']
    old = implementation.get('verification')
    if old:
        history = implementation.setdefault('historical_validation', {})
        history.setdefault('pre_wiring_closure', copy.deepcopy(old))
    implementation['verification'] = {
        'android_compile': 'PENDING_FINAL_SOURCE_BOUND_VALIDATION',
        'jvm_behavior_tests': 'PENDING_FINAL_SOURCE_BOUND_VALIDATION',
        'device_live': 'DEFERRED_UNTIL_WIRING_COMPLETE_UNVERIFIED',
        'scope': 'Prior validation is historical. Source wiring status is not device, deployment or provider qualification.'}


def refresh_endpoints(row, endpoints, refresher):
    for ref in row['endpoint_refs']:
        real = endpoints[ref['endpoint_id']]
        for key in ['authentication', 'registration', 'device_proof_required_when_bound']:
            ref[key] = real[key]
        ref['frontend_access'] = endpoint_frontend_access(real['authentication'])
        ref['source_ref'] = real.get('source')
        namespace, symbol = ref.get('client_namespace'), ref.get('client_symbol')
        ref['client_citations'] = refresher.declaration(namespace, symbol)
        if symbol:
            ref['client_source_status'] = 'declared'
        indirect = [call for call in ref['android_callsites']
                    if call['invocation_kind'] != 'direct_client_method']
        for call in indirect:
            expression = call['symbol'] if call['receiver'] == 'this' else call['receiver'] + '.' + call['symbol']
            refresher.citation(call, re.escape(expression) + r'\s*\(')
        ref['android_callsites'] = copy.deepcopy(refresher.calls.get((namespace, symbol), [])) + indirect
        ref['callsite_validation'] = 'REVIEWED_EXACT_RECEIVER_AND_METHOD_SOURCE_NO_LIVE_CLAIM'
    calls = []
    seen = set()
    for ref in row['endpoint_refs']:
        for kind, source in [('gateway_client_declaration', ref['client_citations'])]:
            for cite in source:
                item = {**copy.deepcopy(cite), 'endpoint_id': ref['endpoint_id'], 'kind': kind,
                        'symbol': ref.get('client_symbol')}
                key = (item['endpoint_id'], item['file'], item['line'], kind, item['symbol'])
                if key not in seen:
                    seen.add(key); calls.append(item)
        for cite in ref['android_callsites']:
            item = {**copy.deepcopy(cite), 'endpoint_id': ref['endpoint_id'], 'kind': cite['invocation_kind']}
            key = (item['endpoint_id'], item['file'], item['line'], item['kind'], item['symbol'])
            if key not in seen:
                seen.add(key); calls.append(item)
    row['android_callsites'] = calls

