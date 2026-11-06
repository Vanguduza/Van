"""Explicit-input finalizer under the root-approved recovery policy. Do not execute until both original runs are terminal and source integrated.

No tests, source edits, commits, pushes or acceptance issuance. Refuses duplicate output.
"""
from pathlib import Path
import datetime
import argparse
import hashlib
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path('/workspace/van-review-2026-10-18/publish')
WORK = Path('/workspace')
SNAPSHOT = WORK / 'van-lanes-20261101/successor'
RECEIPT_REL = 'docs/rebuild/rev118/receipts/FAMILY_SESSION_RECOVERY_SOURCE_20261101.json'
DOC_REL = 'docs/rebuild/rev118/backend/BE-002_003_009_010_012_013_FAMILY_SESSION_RECOVERY.md'
RAW_REL = 'docs/rebuild/rev118/ci/family_session_recovery_20261101'
UNITS = ['BE-002', 'BE-003', 'BE-009', 'BE-010', 'BE-012', 'BE-013']


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def junit(path):
    cases = ET.parse(path).findall('.//testcase')
    failed = [t for t in cases if t.find('failure') is not None]
    errors = [t for t in cases if t.find('error') is not None]
    skipped = [t for t in cases if t.find('skipped') is not None]
    return {'tests': len(cases), 'passed': len(cases)-len(failed)-len(errors)-len(skipped),
            'failures': len(failed), 'errors': len(errors), 'skipped': len(skipped),
            'failure_cases': [{'name': t.get('classname', '')+'.'+t.get('name', ''),
                               'messages': [c.get('message', '') for c in t if c.tag in ('failure', 'error')]}
                              for t in failed+errors]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boundary-run-dir', type=Path, required=True)
    parser.add_argument('--full-run-dir', type=Path, required=True)
    parser.add_argument('--full-recovery-run-dir', type=Path, help='Explicit exact-node storage recovery; original full run remains failed')
    parser.add_argument('--family-handoff', type=Path, default=WORK/'van-family-lane-handoff-r1-20261101.json')
    parser.add_argument('--family-review', type=Path, default=WORK/'van-family-verification-20261101/final-review.json')
    parser.add_argument('--session-handoff', type=Path, default=WORK/'van-session-expiry-successor-20261101.json')
    args = parser.parse_args()
    # All semantic/source/terminal checks precede repository mutation.
    for rel in (RECEIPT_REL, DOC_REL, RAW_REL):
        require(not (ROOT/rel).exists(), 'Refuse duplicate or partial previous finalization: '+rel)
    parent = git('rev-parse', 'HEAD').decode().strip()
    require(parent != '1b53cf9199dc3b8ec01cbc4a6125cc90afad2ae6', 'Auth predecessor must be committed first')
    predecessor_rel = 'docs/rebuild/rev118/receipts/AUTH_COMMIT_EXPIRY_SOURCE_20261101.json'
    predecessor = json.loads(git('show', f'HEAD:{predecessor_rel}'))
    session = read(args.session_handoff)
    family = read(args.family_handoff)
    review = read(args.family_review)
    require(review['handoff_manifest_sha256'] == sha(args.family_handoff), 'Reviewed family handoff differs')
    require(review['before_after_pins_match'] is True, 'Family review input drift')
    require(all(x.get('asserted_expected_result', x.get('exit_code') == 0) for x in review['results']), 'Family review contains unresolved result')
    files = {x['path']: x['sha256'] for x in family['files']}
    require(len(files) == 8, 'Unexpected family handoff scope')
    require({x['path']: x['sha256'] for x in review['verified_files']} == files, 'Reviewed files differ')
    # The first handoff/review remain historical evidence for the pre-repair files.
    correction_path = WORK/'van-family-committed-reader-r2-20261101-hashes.json'
    correction_review_path = WORK/'van-family-verification-20261101/committed-reader-review-r2.json'
    correction = read(correction_path)
    correction_review = read(correction_review_path)
    require(set(correction) == {'trading/vati/core/ledger_pg.py', 'trading/vati/execution/recovery_scope.py', 'trading/tests/test_family_committed_recovery_postgres.py'}, 'Unexpected committed-reader repair scope')
    require(correction_review['remaining_review_blockers'] == [] and correction_review['pins_match_test_receipt'] is True, 'Committed-reader review unresolved')
    require(correction_review['source_pins'] == {f: h['after_sha256'] for f,h in correction.items()}, 'Committed-reader review pins differ')
    for f, h in correction.items():
        if f in files:
            before = files[f]
        else:
            result = subprocess.run(['git', 'show', family['base']+':'+f], cwd=ROOT, capture_output=True)
            before = hashlib.sha256(result.stdout).hexdigest() if result.returncode == 0 else None
            require(result.returncode == 0 or h['before_sha256'] is None, 'Missing repair base input: '+f)
        require(before == h['before_sha256'], 'Committed-reader repair before hash differs: '+f)
        require(sha(SNAPSHOT/f) == h['after_sha256'], 'Committed-reader repair snapshot differs: '+f)
        files[f] = h['after_sha256']
    repair_dir = WORK/'van-family-committed-reader-pg-r2-20261101'
    repair_terminal = read(repair_dir/'receipt.json')
    require(repair_terminal.get('completed') is True and repair_terminal.get('exit') == 0 and repair_terminal.get('cleaned') is True and repair_terminal.get('owned_fixture_independently_absent') is True, 'Committed-reader focused run/cleanup incomplete')
    require(read(repair_dir/'storage-audit.json')['forbidden_events'] == [], 'Committed-reader focused audit violation')
    for f,h in correction.items():
        require(repair_terminal['source_sha256'][f] == h['after_sha256'], 'Committed-reader focused source differs: '+f)
    repair_result = junit(repair_dir/'full-trading.xml')
    require(repair_result['passed'] == 66 and repair_result['failures'] == repair_result['errors'] == repair_result['skipped'] == 0, 'Committed-reader focused result differs')
    files.update(session['files'])
    pg_test = 'trading/tests/test_family_durable_projection_postgres.py'
    files[pg_test] = sha(SNAPSHOT/pg_test)
    require(len(files) == 16, 'Expected corrected family10 + PG1 + session5')
    # The original session handoff predates the auth lookup repair. Its auth pins are historical only.
    # Bind successor to the actual committed corrected predecessor instead.
    for f, h in predecessor['source_sha256'].items():
        require(sha(ROOT/f) == h == sha(SNAPSHOT/f) == hashlib.sha256(git('show', f'HEAD:{f}')).hexdigest(), 'Committed corrected auth predecessor drift: '+f)
    original_path = WORK/'van-parallel-inherited-tests-20261101.json'
    original = read(original_path)
    require(len(original['files']) == 663, 'Unexpected inherited test inventory')
    for f, h in original['files'].items():
        require(sha(ROOT/f) == h, 'Inherited test changed: '+f)
    runs = {}
    pin_sets = []
    copy_files = [(correction_path, Path('repair')/correction_path.name),
                  (correction_review_path, Path('repair')/correction_review_path.name),
                  (WORK/'van-family-committed-reader-r2-20261101.patch', Path('repair')/'source.patch')]
    for name in ('receipt.json', 'source-start.json', 'storage-audit.json', 'full-trading.xml', 'full-trading.log', 'targets.txt'):
        copy_files.append((repair_dir/name, Path('repair')/'focused'/name))
    copy_files.append((WORK/'van-family-committed-reader-pg-r2-20261101.py', Path('repair')/'focused'/'controller.py'))
    for label, directory in [('boundary', args.boundary_run_dir), ('full_regression', args.full_run_dir)]:
        directory = directory.resolve()
        dirname = directory.name
        terminal = read(directory/'receipt.json')
        start = read(directory/'source-start.json')
        composite = None
        if label == 'full_regression' and args.full_recovery_run_dir is not None:
            from van_source_composite_coverage_20261101 import successor
            composite = successor(directory, args.full_recovery_run_dir)
            require(composite['unresolved_bad_or_unexecuted_cases'] == 0 and composite['exact_expected_identity_union_verified'], 'Successor composite coverage unresolved')
        require(terminal.get('completed') is True and (terminal.get('exit') == 0 or composite is not None), label+' not completed successfully and no verified composite recovery')
        require(terminal.get('cleaned') is True and terminal.get('owned_fixture_independently_absent') is True, label+' PG cleanup unproven')
        require(start['source_sha256'] == terminal['source_sha256'], label+' start/final pins differ')
        for field in ('source_sha256', 'reference_fixtures_sha256'):
            for f, h in terminal[field].items():
                require(sha(ROOT/f) == h == sha(SNAPSHOT/f), label+' integrated/frozen input mismatch: '+f)
        for f, h in files.items():
            require(terminal['source_sha256'].get(f) == h, label+' changed file absent or changed: '+f)
        audit = read(directory/'storage-audit.json')
        require(audit['forbidden_events'] == [], label+' storage audit violation')
        result = ({k:v for k,v in composite.items() if k in ['tests','passed','failures','errors','skipped','skip_cases']} if composite is not None else junit(directory/'full-trading.xml'))
        require(result['tests'] > 0 and result['failures'] == result['errors'] == result['skipped'] == 0, label+' JUnit is not all-pass')
        runs[label] = {'junit': result, 'terminal_receipt': f'{RAW_REL}/{label}/receipt.json',
                       'source_pins': len(terminal['source_sha256']), 'source_storage_audit_violations': 0, 'original_terminal_exit': terminal.get('exit'), 'composite_coverage': composite,
                       'owned_postgres_independently_absent': True}
        pin_sets.append(terminal['source_sha256'])
        for name in ('receipt.json', 'source-start.json', 'storage-audit.json', 'full-trading.xml', 'full-trading.log', 'targets.txt'):
            copy_files.append((directory/name, Path(label)/name))
        copy_files.append((WORK/(dirname+'.py'), Path(label)/'controller.py'))
    if args.full_recovery_run_dir is not None:
        for path in sorted(args.full_recovery_run_dir.iterdir()):
            if path.is_file():copy_files.append((path,Path('storage-recovery')/path.name))
        for src,dest in [(WORK/'van_source_composite_coverage_20261101.py','composite-coverage-verifier.py'),
                         (WORK/'van_owned_basetemp_20261101.py','owned-basetemp-helper.py'),
                         (WORK/'van-successor-storage-recovery-pg-r3-20261101.py','storage-recovery/controller.py'),
                         (WORK/'van-storage-recovery-sets-20261101/successor.json','storage-recovery/recovery-plan.json'),
                         (WORK/'van-storage-exhaustion-recovery-20261101.json','storage-recovery/exhaustion-and-cleanup.json')]:
            copy_files.append((src,Path(dest)))
    require(pin_sets[0] == pin_sets[1], 'Boundary/full source inputs differ')
    # Original first integrated regression is a failed/interrupted attempt, never silently replaced.
    original_failed = WORK/'van-successor-regression-pg-r1-20261101'
    failed_terminal = read(original_failed/'receipt.json')
    require(failed_terminal.get('completed') is True, 'Original failed run must be reconciled to terminal state')
    require(failed_terminal.get('exit') != 0, 'Original r1 failure classification changed; review required')
    failed_attempt = {'classification': 'Actual integrated PostgreSQL account-recovery failures: committed snapshot read inside atomic writer; later source repair requires fresh qualification',
                      'terminal_receipt': f'{RAW_REL}/failed-regression-r1/receipt.json',
                      'exit': failed_terminal['exit']}
    if (original_failed/'full-trading.xml').is_file():
        failed_attempt['junit'] = junit(original_failed/'full-trading.xml')
    for name in ('receipt.json', 'source-start.json', 'full-trading.log', 'test-events.jsonl'):
        copy_files.append((original_failed/name, Path('failed-regression-r1')/name))
    for name in ('full-trading.xml', 'storage-audit.json'):
        if (original_failed/name).is_file():
            copy_files.append((original_failed/name, Path('failed-regression-r1')/name))
    # Preserve actual failures separately from corrected new-fixture errors; never relabel failures as passes.
    history_names = ['van-family-original-before-20261030', 'van-family-lane-focused-r3-20261101',
                     'van-family-lane-focused-r5-20261101', 'van-family-lane-focused-r7-20261101',
                     'van-family-lane-focused-final-r2-20261101', 'van-session-expiry-before-20261101',
                     'van-session-retention-before-20261101', 'van-session-expiry-final-r2-20261101']
    historical = {}
    classifications = {
        'van-family-original-before-20261030': 'Original production accounting/context/recovery regressions',
        'van-family-lane-focused-r3-20261101': 'Intermediate production recovery regressions against inherited tests',
        'van-family-lane-focused-r5-20261101': 'New fixture error: Ledger used as unsupported context manager',
        'van-family-lane-focused-r7-20261101': 'Intermediate observation-count assertion; original failure retained without claiming native effects',
        'van-session-expiry-before-20261101': 'Original production writer-expiry/result-recovery/original-deadline failures',
        'van-session-retention-before-20261101': 'Production retention omission for durable original message expiry',
    }
    for name in history_names:
        historical[name] = {'classification': classifications.get(name, 'Focused final source run; overlaps integrated suites'),
                            'junit': junit(WORK/(name+'.xml'))}
        for ext in ('xml', 'log'):
            copy_files.append((WORK/(name+'.'+ext), Path('history')/(name+'.'+ext)))
    for name in ('baseline-review.json', 'intermediate-review.json', 'final-targeted.xml'):
        copy_files.append((WORK/'van-family-verification-20261101'/name, Path('review')/name))
    copy_files.append((args.family_review, Path('review')/'selected-final-review.json'))
    for p in (original_path, args.family_handoff, args.session_handoff):
        copy_files.append((p, Path(p.name)))
    copy_files.append((Path(__file__), Path('evidence-builder.py')))
    require(len({str(dest) for _, dest in copy_files}) == len(copy_files), 'Duplicate evidence destination')
    require(all(src.is_file() for src, _ in copy_files), 'Required evidence file missing')
    progress_path = ROOT/'docs/rebuild/rev118/CANDIDATE_SOURCE_PROGRESS.json'
    progress = read(progress_path)
    for uid in UNITS:
        require(uid in progress['units'], 'Missing canonical unit '+uid)
        require(not any(RECEIPT_REL.split('/')[-1] in json.dumps(m) for m in progress['units'][uid]['milestones']), 'Duplicate milestone '+uid)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    data = {'schema': 'van.rebuild.family-session-recovery-source/1', 'at_utc': now,
            'source_parent': parent, 'tested_snapshot_base': family['base'], 'tested_snapshot': str(SNAPSHOT),
            'source_sha256': files, 'canonical_units': UNITS,
            'effective_acceptance_registry': 'docs/review-inputs/van-rev115/package/verification/EFFECTIVE_TEST_CONTRACTS_REV118.json',
            'evidence_meaning': 'Source support for family accounting/durable recovery/actual consumers and original session expiry/result readback subpaths; not complete unit acceptance',
            'runs': runs, 'committed_reader_repair': {'delta': correction, 'review': correction_review, 'focused': repair_result, 'original_family_review_meaning': 'Historical pre-repair eight-file review; corrected three-file review and actual PostgreSQL qualification are bound separately'}, 'historical_results': historical, 'original_integrated_failure': failed_attempt, 'suites_overlap': True,
            'inherited_test_files_byte_identical': len(original['files']), 'source_pins_matching': len(pin_sets[0]),
            'auth_predecessor_receipt': predecessor_rel, 'auth_predecessor_source_sha256': predecessor['source_sha256'], 'session_handoff_historical_auth_pins': session.get('auth_predecessor_unchanged', {}), 'unit_acceptance': 'NOT_ISSUED',
            'native_provider_production_device_acceptance': False, 'mutation_execution_claimed': False,
            'limitations': ['Full hedged multi-position execution/protection dispatch and multi-entry review remain OPEN; scoped new-risk hold is not completion of those required effects.',
                           'Expired unresolved cancellation/decision effects require original operation-specific domain receipts; coincident current state does not prove original completion.',
                           'Native economic finality, all full-unit obligations, independent admission, providers, production signing and physical S24 acceptance remain open.',
                           'Python storage audit is scoped diagnostic evidence, not an OS sandbox.'],
            'raw_files': {str(Path(RAW_REL)/dest): sha(src) for src, dest in copy_files}}
    b, f = runs['boundary']['junit'], runs['full_regression']['junit']
    summary = f"Family remaining basis and lifetime recovery use exact original evidence and actual risk consumers; original session expiry is bound and checked at writer admission while durable original results remain readable. Boundary{b['passed']} and exact affected composite coverage{f['passed']} passed with zero failures/errors/skips/audit violations; suites overlap. All{len(original['files'])} inherited tests byte-identical. Full hedged execution/review and unresolved expired cancel/decision outcomes remain OPEN. No full-unit or native acceptance."
    doc = '# Original family accounting and session authority recovery\n\n'+summary+'\n\nFamily source restores original members and lifetime counters, preserves legacy evidence, and retains divergence/provenance holds through actual consumers. Session source separates new-effect admission from original durable result recovery and removes original expiry records with their message retention lifecycle.\n\nThe original broad regression remains failed after storage exhaustion from retained owned test fixtures; exact original fully passed identities plus actual recovery of every failed case provide composite source coverage, without claiming a single successful full-suite run. Owned temporary space is checked before recovery and inventoried/cleaned after terminal execution. Original production failures, intermediate production regressions and new-fixture errors remain separately recorded in [the receipt](../receipts/FAMILY_SESSION_RECOVERY_SOURCE_20261101.json). Parallel engineering review is source analysis, not independent native certification.\n\n'+'\n'.join('- '+x for x in data['limitations'])+'\n'
    # Mutation starts only after every precondition and evidence input has passed.
    raw = ROOT/RAW_REL
    raw.mkdir(exist_ok=False)
    for src, dest in copy_files:
        target = raw/dest
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        require(sha(target) == data['raw_files'][str(Path(RAW_REL)/dest)], 'Evidence copy mismatch')
    (ROOT/RECEIPT_REL).write_text(json.dumps(data, indent=2)+'\n')
    (ROOT/DOC_REL).write_text(doc)
    for uid in UNITS:
        progress['units'][uid]['milestones'].append({'description': summary, 'evidence': DOC_REL.removeprefix('docs/rebuild/rev118/')+';'+RECEIPT_REL.removeprefix('docs/rebuild/rev118/')})
    progress['updated_at_utc'] = now
    progress_path.write_text(json.dumps(progress, indent=2)+'\n')
    print(json.dumps({'receipt': RECEIPT_REL, 'source_parent': parent, 'runs': runs, 'raw_files': len(copy_files), 'acceptance_issued': False}))


if __name__ == '__main__':
    main()
