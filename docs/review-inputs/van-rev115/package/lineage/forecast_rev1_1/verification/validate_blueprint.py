#!/usr/bin/env python3
"""Validate this blueprint's DOCUMENTS ONLY. Never grants authority or runs VAN.

Requires Python >=3.10 and jsonschema. No network, provider, model or project-runtime
calls are made. --readiness deliberately exits 2 while implementation is unperformed.
"""
from __future__ import annotations
import argparse
import copy
import datetime as dt
import hashlib
import json
import math
import platform
import importlib.metadata
import re
import zipfile
from prediction_market_contract_checks import fixture_errors, mutation_checks
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError as exc:
    raise SystemExit('Document validation needs jsonschema. No application test was run.') from exc

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> Any:
    return json.loads((ROOT/path).read_text(encoding='utf-8'))


def iso(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00'))


def plan_errors(plan: dict, reqs: list, tests: list, parent: dict) -> list[str]:
    errors: list[str] = []
    packets = plan.get('packets', [])
    ids = [p['id'] for p in packets]
    reqids = [r['id'] for r in reqs]
    testids = [t['id'] for t in tests]
    for kind, values in [('packet', ids), ('requirement', reqids), ('test', testids)]:
        if len(values) != len(set(values)):
            errors.append(f'duplicate {kind} id')
    pmap = {p['id']:p for p in packets}
    rmap = {r['id']:r for r in reqs}
    tmap = {t['id']:t for t in tests}
    if len(packets) != 48 or len(reqs) != 90 or len(tests) != 180:
        errors.append('declared 48/90/180 inventory mismatch; update reviewed scope, not counts alone')
    parent_ids = {x['unit_id'] for x in parent['parent_nodes']}
    if len(parent['parent_nodes']) != 76:
        errors.append('read-only parent inventory mismatch')
    invariant_values = {
        'single_order_sender':'VATI.ExecutionRouter',
        'single_risk_authority':'VATI.RiskAuthority',
        'forecast_authority_effect':'NONE',
        'qlib_execution_allowed':False,
        'freqtrade_live_runtime_allowed':False,
        'automatic_live_model_promotion':False,
        'frontend_requires_parent_BG001':True,
        'all_mandatory_backend_before_frontend':True,
        'document_checker_can_issue_gate':False,
        'prediction_market_order_sender_allowed':False,
        'licence_procurement_required_for_document_or_code':False,
        'procurement_in_this_phase':False,
        'host_location_proves_operator_eligibility':False,
        'prediction_market_source_access_granted_by_blueprint':False,
        'prediction_market_unknown_source_may_not_be_marked_ready':True,
        'event_probability_is_trade_win_probability':False,
        'source_consensus_is_independent_evidence':False,
        'prediction_market_research_labs_mandatory':True,
    }
    for key,val in invariant_values.items():
        if plan.get('invariants',{}).get(key) != val:
            errors.append(f'invariant mismatch: {key}')
    for p in packets:
        if p.get('status') != 'NOT_STARTED' or p.get('implementation_evidence'):
            errors.append(f'unsupported implementation claim: {p["id"]}')
        if not p.get('full_deliverables') or not p.get('exit_evidence'):
            errors.append(f'missing packet duty or exit contract: {p["id"]}')
        if not set(p['parent_units']).issubset(parent_ids):
            errors.append(f'unknown parent unit in {p["id"]}')
        if any(x not in pmap for x in p['depends_on']):
            errors.append(f'unknown dependency in {p["id"]}')
        expected_r = {r['id'] for r in reqs if r['packet_id']==p['id']}
        if not expected_r or set(p.get('requirement_ids',[])) != expected_r:
            errors.append(f'packet requirement coverage mismatch: {p["id"]}')
        expected_t = {t['id'] for t in tests if t['packet_id']==p['id']}
        if set(p.get('test_ids',[])) != expected_t:
            errors.append(f'packet test coverage mismatch: {p["id"]}')
    active: set[str] = set()
    finished: set[str] = set()
    def visit(pid: str) -> None:
        if pid in active:
            errors.append('dependency cycle'); return
        if pid in finished or pid not in pmap:
            return
        active.add(pid)
        for dep in pmap[pid]['depends_on']:
            visit(dep)
        active.remove(pid); finished.add(pid)
    for pid in ids:
        visit(pid)
    def ancestors(pid: str, seen: set[str] | None = None) -> set[str]:
        seen = set() if seen is None else seen
        for dep in pmap.get(pid,{}).get('depends_on',[]):
            if dep not in seen:
                seen.add(dep); ancestors(dep,seen)
        return seen
    f15='VAN-ML-PKT-003'
    for p in packets:
        n=int(p['id'].rsplit('-',1)[1])
        if n>=4 and f15 not in ancestors(p['id']):
            errors.append(f'code can precede F15: {p["id"]}')
        if n in (34,35,36) and 'VAN-ML-PKT-033' not in ancestors(p['id']):
            errors.append(f'post-backend packet bypasses integration gate: {p["id"]}')
    if pmap.get('VAN-ML-PKT-034',{}).get('stage') != 'FRONTEND':
        errors.append('frontend packet misclassified as backend')
    external=' '.join(pmap.get('VAN-ML-PKT-034',{}).get('external_entry_requirements',[]))
    if 'BG-001' not in external:
        errors.append('parent BG-001 external gate missing')
    direct=set(pmap.get('VAN-ML-PKT-032',{}).get('depends_on',[]))
    mandatory={f'VAN-ML-PKT-{i:03d}' for i in list(range(4,32))+list(range(37,49))}
    if direct != mandatory:
        errors.append('independent backend review must enumerate all mandatory implementation/verification packets')
    index={pid:i for i,pid in enumerate(ids)}
    if any(dep in index and index[dep]>=index[p['id']] for p in packets for dep in p['depends_on']):
        errors.append('packet array is not topologically ordered')
    for pid in ('VAN-ML-PKT-047','VAN-ML-PKT-048'):
        if pid not in ancestors('VAN-ML-PKT-030'):
            errors.append('scientific reports omit mandatory prediction-market integration')
    for r in reqs:
        if r['packet_id'] not in pmap:
            errors.append(f'unknown requirement packet: {r["id"]}')
        if r.get('status') != 'SPECIFIED_NOT_IMPLEMENTED':
            errors.append(f'unsupported requirement status: {r["id"]}')
        ts=[tmap.get(i) for i in r.get('test_ids',[])]
        if len(ts)!=2 or any(t is None for t in ts) or {t['kind'] for t in ts if t} != {'POSITIVE','ADVERSARIAL'}:
            errors.append(f'positive/adversarial test coverage missing: {r["id"]}')
        for t in ts:
            if t and (t['requirement_id']!=r['id'] or t['packet_id']!=r['packet_id']):
                errors.append(f'test linkage mismatch: {r["id"]}')
    for t in tests:
        if t['requirement_id'] not in rmap:
            errors.append(f'unknown test requirement: {t["id"]}')
        if t.get('status')!='NOT_RUN' or t.get('receipt_refs'):
            errors.append(f'unexecuted application test misreported: {t["id"]}')
        if not t.get('contract') or not t.get('expected_evidence'):
            errors.append(f'empty test contract: {t["id"]}')
    return errors


def forecast_errors(obj: dict, schema: dict) -> list[str]:
    errors=[f'schema: {e.message}' for e in Draft202012Validator(schema,format_checker=FormatChecker()).iter_errors(obj)]
    if errors:
        return errors
    def finite(x: Any) -> bool:
        if isinstance(x,float) and not math.isfinite(x): return False
        if isinstance(x,dict): return all(finite(v) for v in x.values())
        if isinstance(x,list): return all(finite(v) for v in x)
        return True
    if not finite(obj): errors.append('nonfinite predictive value')
    if obj['scope']['environment']!='FIXTURE':
        errors.append('portable example must stay FIXTURE; no live evidence is present')
    if not (iso(obj['train_label_available_cutoff']) <= iso(obj['input_cutoff']) <= iso(obj['generated_at']) < iso(obj['expires_at'])):
        errors.append('forecast temporal order invalid')
    if iso(obj['max_input_available_at'])>iso(obj['input_cutoff']):
        errors.append('future-available input')
    p=obj['payload']
    if p is not None:
        qs=p['quantiles']; alphas=[v['alpha'] for v in qs]; values=[v['value'] for v in qs]
        if alphas != sorted(set(alphas)) or values!=sorted(values):
            errors.append('quantile order/crossing')
        has_output=any(p.get(k) is not None for k in ['mean','event_probability','rank_score','raw_event_probability','scenario_artifact']) or bool(qs)
        if not has_output: errors.append('ready packet has no predictive output')
        if p['event_probability'] is not None:
            if obj['calibration_state']!='CALIBRATED' or not obj['calibration_artifact_digest'] or not p['event_definition_id'] or not obj['evidence_refs']:
                errors.append('calibrated event probability lacks necessary metadata; actual trusted evidence still requires production verification')
        if p['raw_event_probability'] is not None and not p['event_definition_id']:
            errors.append('raw event score lacks event identity')
        if (p['scenario_artifact'] is None) != (p['scenario_count']==0):
            errors.append('scenario count/artifact mismatch')
        if p['scenario_artifact'] is not None and not obj['sampling_policy_digest']:
            errors.append('scenario sampling identity missing')
        if p['dependency_scope']=='JOINT_COHORT' and (p['scenario_artifact'] is None or not any('joint-dependence' in x for x in obj['evidence_refs'])):
            errors.append('joint scenario assertion without even required provenance reference; truth is not established by references')
    return errors


def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--readiness',action='store_true',help='Report actual NOT_IMPLEMENTED/NOT_ISSUED and exit2; never issues permission.')
    args=ap.parse_args()
    if args.readiness:
        print(json.dumps({'document_id':'VAN-FORECAST-ADOPTION-REV1.1-20261017','readiness':'BLOCKED_NOT_IMPLEMENTED','application_tests':'NOT_RUN','independent_semantic_review':'NOT_PERFORMED','parent_F15':'NOT_ISSUED_BY_THIS_PACK','parent_BG001':'NOT_ISSUED_BY_THIS_PACK','live_permission':'NONE','reason':'Document validation cannot certify implementation, independent evidence, authority or economic edge.'},indent=2))
        return 2
    plan=read('plan/IMPLEMENTATION_PLAN.json'); reqs=read('plan/REQUIREMENTS.json')['requirements']; tests=read('plan/ACCEPTANCE_TEST_CONTRACTS.json')['tests']; parent=read('references/PARENT_PLAN_SNAPSHOT.json')
    checks=[]
    def record(name: str, errors: list[str]) -> None:
        checks.append({'name':name,'result':'PASS' if not errors else 'FAIL','findings':errors})
    record('plan DAG, ownership references, coverage and authority declarations',plan_errors(plan,reqs,tests,parent))
    all_json=list(ROOT.rglob('*.json')); parse_errors=[]
    for p in all_json:
        if p.name=='DOCUMENT_CHECK_REPORT.json': continue
        try:json.loads(p.read_text(),parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f'Nonstandard numeric constant {value}')))
        except Exception as e:parse_errors.append(f'{p.relative_to(ROOT)}: {e}')
    record('all JSON documents parse without nonstandard NaN/Infinity',parse_errors)
    schemas=list((ROOT/'contracts').glob('*.schema.json'))
    for s in schemas:
        try: Draft202012Validator.check_schema(json.loads(s.read_text())); errors=[]
        except Exception as e: errors=[str(e)]
        record('Draft2020-12 schema shape: '+s.stem,errors)
    fs=read('contracts/ForecastPacket.schema.json')
    ready=read('contracts/examples/ForecastPacket.fixture.ready.json')
    abstain=read('contracts/examples/ForecastPacket.fixture.abstained.json')
    record('synthetic READY forecast example shape/local semantics',forecast_errors(ready,fs))
    record('synthetic ABSTAINED forecast example shape/local semantics',forecast_errors(abstain,fs))
    sources=read('references/SOURCE_REGISTER.json')['sources']
    master=(ROOT/'VAN_FORECAST_ADOPTION_BLUEPRINT_REV1_1_20261017.md').read_text()
    actual={s['id'] for s in sources}; used=set(re.findall(r'S\d{2}',master))
    record('master source IDs resolve',[] if used<=actual and len(actual)==42 and len(sources)==42 else ['missing/duplicate source ID'])
    plan_md=(ROOT/'plan/IMPLEMENTATION_PLAN.md').read_text()
    record('human plan includes all packet exit sections',[] if all('### '+p['id']+' — '+p['title'] in plan_md for p in plan['packets']) else ['packet section missing from rendered plan'])
    req_md=(ROOT/'plan/REQUIREMENTS_AND_TESTS.md').read_text()
    record('human requirement/test contracts include every exact ID',[] if all(t['id'] in req_md for t in tests) and all(r['id'] in req_md for r in reqs) else ['contract ID missing'])
    profile=read('config/RESEARCH_STARTING_PROFILE.json')
    record('research example has no resolved live/paid/market permission',[] if profile['live_enabled'] is False and profile['paid_compute_budget'] is None and not profile['instrument_ids'] and profile['retraining']['automatic_live_promotion'] is False else ['example contains permission-like state'])
    # The original materialized parent bytes are not shipped. Verify the two actually
    # observed fingerprints against the copied read-only record, not an absent file.
    fingerprints={p['name']:p['sha256'] for p in parent['parent_files']}
    record('parent fingerprint references agree with retrieved material record',[] if fingerprints.get('VAN_NEXT_MASTER_BLUEPRINT_REV1_10_20261017.md')=='dba347b9f02831d1a3a2d9570b4434f6a8b4b98f6f47862c830ff6784cb56f51' and fingerprints.get('VAN_NEXT_DEVELOPMENT_PLAN_REV1_10.md')=='1b367e7507f2d371230891458ca1efc05c6fbb343b712d97ca170cecebbbc6e2' else ['parent identities differ'])
    # Reconcile exact inherited obligations; package lineage is not an authority grant.
    lineage=read('lineage/REVISION_LINEAGE.json')
    archive=ROOT/'lineage/REV1_ORIGINAL_PACK.zip'
    preserve=[]
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=lineage['original_zip_sha256']:
        preserve.append('embedded original ZIP identity differs')
    prefix='VAN_FORECAST_ADOPTION_BLUEPRINT_REV1_20261017/'
    with zipfile.ZipFile(archive) as z:
        original_req=json.loads(z.read(prefix+'plan/REQUIREMENTS.json'))['requirements']
        original_tests=json.loads(z.read(prefix+'plan/ACCEPTANCE_TEST_CONTRACTS.json'))['tests']
        if reqs[:60]!=original_req: preserve.append('original requirement objects changed')
        if tests[:120]!=original_tests: preserve.append('original test objects changed')
        original_plan=json.loads(z.read(prefix+'plan/IMPLEMENTATION_PLAN.json'))
        pmap={x['id']:x for x in plan['packets']}
        for old in original_plan['packets']:
            new=pmap.get(old['id'],{})
            if not new or not set(old['full_deliverables']).issubset(set(new.get('full_deliverables',[]))):
                preserve.append('original packet deliverable missing: '+old['id'])
        for name in z.namelist():
            rel=name.removeprefix(prefix)
            if rel.endswith('.schema.json') or rel=='references/PARENT_PLAN_SNAPSHOT.json':
                if not (ROOT/rel).exists() or (ROOT/rel).read_bytes()!=z.read(name):
                    preserve.append('inherited schema/parent snapshot changed: '+rel)
        for rel,digest in lineage['original_files'].items():
            if hashlib.sha256(z.read(prefix+rel)).hexdigest()!=digest:
                preserve.append('original lineage member mismatch: '+rel)
    record('original obligations, schemas and parent lineage preserved',preserve)
    pp=read('config/PREDICTION_MARKET_PROFILE.json')
    good=(pp['licence_procurement_required'] is False and pp['procurement_in_this_phase'] is False
          and pp['new_external_purchase_budget_usd']=='0.00' and pp['live_event_contract_execution_enabled'] is False
          and pp['deployment']['operator_eligibility_inferred_from_host'] is False
          and set(pp['deployment']['providers'])=={'NETCUP','ORACLE'}
          and pp['real_source_use']['status']=='NOT_ESTABLISHED_BY_THIS_PACK')
    record('hosted research profile separates procurement, source use and authority',[] if good else ['prediction profile contradicts owner scope'])
    studies=read('research/PREDICTION_MARKET_STUDIES.json')['studies']
    good=(len(studies)==4 and {x['study_id'] for x in studies}==set(pp['studies'])
          and all(x['application_result']=='NOT_RUN' and x['whole_account_replay'] and x['exposure_matched_control'] and x['all_trials_preserved'] for x in studies))
    record('four study templates align with research profile and no result is asserted',[] if good else ['study template mismatch'])
    delta=read('plan/PARENT_INTEGRATION_DELTA.json')
    good=(delta['parent_signed_files_modified'] is False and delta['status']=='SPECIFIED_NOT_APPLIED_TO_PARENT'
          and delta['no_procurement_requirement'] is True and delta['preserve_original_parent_nodes']==76
          and set(delta['new_requirement_ids'])=={x['id'] for x in reqs[60:]}
          and set(delta['new_packet_ids'])=={f'VAN-ML-PKT-{i:03}' for i in range(37,49)})
    record('parent delta preserves authority boundary and exact new IDs',[] if good else ['parent delta inconsistent'])
    pm_fixtures={};pm_schemas={}
    for path in sorted((ROOT/'contracts/prediction_market_examples').glob('*.fixture.json')):
        kind=path.name.removesuffix('.fixture.json')
        obj=read(str(path.relative_to(ROOT))); schema=read('contracts/'+kind+'.schema.json')
        pm_fixtures[kind]=obj;pm_schemas[kind]=schema
        record('synthetic PM fixture shape/local semantics: '+kind,fixture_errors(kind,obj,schema))
    record('all 18 principal schemas and 12 synthetic examples present',[] if len(schemas)==18 and len(pm_fixtures)==10 else ['contract inventory mismatch'])
    mutations=[]
    def p_mut(name,mut):
        p=copy.deepcopy(plan);r=copy.deepcopy(reqs);t=copy.deepcopy(tests)
        mut(p,r,t);found=plan_errors(p,r,t,parent)
        mutations.append({'name':name,'result':'DETECTED' if found else 'MISSED','finding_count':len(found)})
    def pkt(p,n): return next(x for x in p['packets'] if x['id']==f'VAN-ML-PKT-{n:03}')
    p_mut('dependency cycle',lambda p,r,t:p['packets'][0]['depends_on'].append('VAN-ML-PKT-032'))
    p_mut('code detached from F15',lambda p,r,t:pkt(p,4).update(depends_on=[]))
    p_mut('second order sender',lambda p,r,t:p['invariants'].update(single_order_sender='ForecastService'))
    p_mut('automatic live promotion',lambda p,r,t:p['invariants'].update(automatic_live_model_promotion=True))
    p_mut('frontend disguised as backend',lambda p,r,t:pkt(p,34).update(stage='BACKEND'))
    p_mut('missing adversarial test',lambda p,r,t:r[0]['test_ids'].pop())
    p_mut('duplicate requirement ID',lambda p,r,t:r[1].update(id=r[0]['id']))
    p_mut('application test falsely reported PASS',lambda p,r,t:t[0].update(status='PASS'))
    p_mut('incomplete independent backend inventory',lambda p,r,t:pkt(p,32)['depends_on'].pop())
    p_mut('missing parent global barrier',lambda p,r,t:pkt(p,34).update(external_entry_requirements=[]))
    p_mut('unknown parent unit',lambda p,r,t:p['packets'][10]['parent_units'].append('BE-999'))
    p_mut('procurement incorrectly gates document/code',lambda p,r,t:p['invariants'].update(licence_procurement_required_for_document_or_code=True))
    p_mut('event market given order-sender authority',lambda p,r,t:p['invariants'].update(prediction_market_order_sender_allowed=True))
    p_mut('hosting asserted to prove operator eligibility',lambda p,r,t:p['invariants'].update(host_location_proves_operator_eligibility=True))
    p_mut('event research labs made optional',lambda p,r,t:p['invariants'].update(prediction_market_research_labs_mandatory=False))
    def f_mut(name,mut,obj=ready):
        f=copy.deepcopy(obj);mut(f);found=forecast_errors(f,fs)
        mutations.append({'name':name,'result':'DETECTED' if found else 'MISSED','finding_count':len(found)})
    f_mut('uncalibrated score advertised as calibrated probability',lambda f:f['payload'].update(event_probability=0.8,event_definition_id='fixture-event'))
    f_mut('NaN output',lambda f:f['payload'].update(mean=float('nan')))
    f_mut('future input availability',lambda f:f.update(max_input_available_at='2026-10-17T09:00:00Z'))
    f_mut('expiry before generation',lambda f:f.update(expires_at='2026-10-17T07:00:00Z'))
    f_mut('crossed quantiles',lambda f:f['payload']['quantiles'][0].update(value=0.5))
    f_mut('ready without output',lambda f:f['payload'].update(mean=None,quantiles=[]))
    f_mut('abstention contains forecast payload',lambda f:f.update(status='ABSTAINED',reason_codes=['DATA_STALE']))
    f_mut('fixture relabelled live',lambda f:f['scope'].update(environment='LIVE_ADVISORY'))
    f_mut('forecast injected order quantity',lambda f:f.update(order_quantity=1))
    f_mut('scenario count without actual artifact',lambda f:f['payload'].update(scenario_count=100))
    f_mut('joint claim without joint artifact',lambda f:f['payload'].update(dependency_scope='JOINT_COHORT'))
    mutations.extend(mutation_checks(pm_fixtures,pm_schemas))
    record('all deliberate document/fixture mutations detected',[] if all(m['result']=='DETECTED' for m in mutations) else [m['name'] for m in mutations if m['result']=='MISSED'])
    ok=all(c['result']=='PASS' for c in checks)
    report={'document_id':'VAN-FORECAST-ADOPTION-REV1.1-20261017','report_type':'DOCUMENT_CONSISTENCY_ONLY','generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'result':'PASS' if ok else 'FAIL','execution_environment':'ChatGPT artifact-packaging container; not a DIAL VM or VAN application environment','document_check_toolchain':{'python':platform.python_version(),'jsonschema':importlib.metadata.version('jsonschema')},'checked_counts':{'child_packets':len(plan['packets']),'parent_lineage_packets':len(parent['parent_nodes']),'requirements':len(reqs),'unexecuted_application_test_contracts':len(tests),'principal_schemas':len(schemas),'fixture_examples':2+len(pm_fixtures),'source_entries':len(sources),'document_check_groups':len(checks),'deliberate_document_fixture_mutations':len(mutations)},'checks':checks,'mutations':mutations,'claims_not_made':['Licence procurement or source-use permission','Operator eligibility','Actual provider capture or event-contract trading','Application implementation','Runtime model/service integration','Dataset or model training','Statistical/economic validation','Independent semantic review','Expanded parent DAG qualification','Cryptographic authority validation','Parent F15 or BG-001 issuance','Device acceptance','Live financial permission'],'application_test_state':'NOT_RUN','independent_qualification':'NOT_ISSUED','execution_or_trading_authority':'NONE'}
    target=ROOT/'verification/DOCUMENT_CHECK_REPORT.json'
    target.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    md='# Document consistency report — Rev1.1\n\n**Result: '+report['result']+'** · '+report['generated_at']+'\n\n'
    md+='Environment: '+report['execution_environment']+'. These are document/schema/synthetic-reference checks, not VAN application tests.\n\n'
    md+='| Inventory | Count |\n|---|---:|\n'+''.join('| '+k.replace('_',' ')+' | '+str(v)+' |\n' for k,v in report['checked_counts'].items())
    md+='\n## Checked properties\n\n'+''.join('- '+c['result']+' — '+c['name']+(' — '+str(c['findings']) if c['findings'] else '')+'\n' for c in checks)
    md+='\n## Deliberate faulty documents/fixtures\n\n'+''.join('- '+m['result']+' — '+m['name']+'\n' for m in mutations)
    md+='\n## Claims not made\n\n'+', '.join(report['claims_not_made'])+'. All180 application acceptance contracts remain NOT_RUN. No independent gate or financial authority is issued.\n'
    (ROOT/'verification/DOCUMENT_CHECK_REPORT.md').write_text(md)
    print(json.dumps({'result':report['result'],'checked_counts':report['checked_counts'],'report':str(target),'application_tests':'NOT_RUN','authority':'NONE'},indent=2))
    return 0 if ok else 1

if __name__=='__main__':
    raise SystemExit(main())
