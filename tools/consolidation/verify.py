#!/usr/bin/env python3
"""Verify source-consolidation provenance and discovery boundaries; no runtime claims."""
from pathlib import Path
import configparser
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
ALLOWED = {'INTEGRATED', 'INTEGRATED_ANCESTOR', 'ALREADY_IN_MAIN',
           'PRESERVED_CANDIDATE', 'RECONCILED_IN_SOURCE', 'HISTORICAL_EVIDENCE',
           'SUPERSEDED_SPECIFICATION', 'PATCH_EQUIVALENT_SUPERSEDED'}


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()


def main():
    state = json.loads((ROOT / 'CONSOLIDATION_STATE.json').read_text())
    inventory = json.loads((ROOT / state['branch_evaluation']).read_text())
    findings = []
    rows = inventory['branches']
    names = [r['branch'] for r in rows]
    if len(rows) != state['branch_snapshot_count'] or len(set(names)) != len(rows):
        findings.append('Branch inventory count/identity mismatch')
    for row in rows:
        if row['disposition'] not in ALLOWED or not row.get('rationale') or not row.get('evidence_commit'):
            findings.append('Missing branch disposition/evidence: ' + row['branch'])
        if git('rev-parse', 'refs/tags/' + row['archive_tag']) != row['sha']:
            findings.append('Snapshot ref mismatch: ' + row['branch'])
    hooks = subprocess.run(['git', '-C', str(ROOT), 'config', '--get', 'core.hooksPath'],
                           text=True, capture_output=True)
    if hooks.returncode or hooks.stdout.strip() != '.githooks':
        findings.append('Install the repository Project Truth hooks before source work')
    spec = state['blueprint']
    actual_hash = hashlib.sha256((ROOT / spec['archive']).read_bytes()).hexdigest()
    if actual_hash != spec['archive_sha256']:
        findings.append('Blueprint archive differs from admitted delivery')
    if git('rev-parse', spec['delivery_commit'] + ':' + spec['package']) != spec['package_tree']:
        findings.append('Blueprint source tree identity mismatch')
    if subprocess.run(['git', '-C', str(ROOT), 'diff', '--quiet', spec['delivery_commit'], '--', spec['package']]).returncode:
        findings.append('Admitted blueprint package has been changed')
    config = configparser.ConfigParser()
    config.read(ROOT / 'pytest.ini')
    suites = config['pytest'].get('testpaths', '').split()
    expected = {'backend/tests', 'tests', 'services', 'hermes/policy/tests', 'trading/tests'}
    if set(suites) != expected:
        findings.append('Default test roots omit production suites or include evidence copies')
    for path in suites:
        if not (ROOT / path).is_dir():
            findings.append('Missing active test root: ' + path)
    for branch, sha in state['source_inputs'].items():
        if subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor', sha, 'HEAD']).returncode:
            findings.append('Integrated source input is not an ancestor: ' + branch)
    if state['production_deployed'] or state['release_qualified']:
        findings.append('Source-only consolidation cannot issue deployment or release qualification')
    print(json.dumps({'scope': 'SOURCE_CONSOLIDATION_ONLY', 'branches_evaluated': len(rows),
                      'blueprint_archive_sha256': actual_hash, 'findings': findings,
                      'runtime_qualification_issued': False}, indent=2))
    return bool(findings)


if __name__ == '__main__':
    sys.exit(main())
