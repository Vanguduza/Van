#!/usr/bin/env python3
"""Render one deterministic plan. Never issues a gate or modifies application code."""
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def pairs(items):
 d={}
 for k,v in items:
  if k in d:raise ValueError(f'DUPLICATE_JSON_KEY: {k}')
  d[k]=v
 return d
def read(p):return json.loads((ROOT/p).read_text(),object_pairs_hook=pairs)
def cell(x):return str(x).replace('|','\\|').replace('\n',' ')
def acceptance_index(plan,tests):
 """Derived references only; TEST_CONTRACTS remains the owner of test objects."""
 result={u['id']:[] for u in plan['units']};seen=set()
 for t in tests:
  if t['id'] in seen:raise ValueError('DUPLICATE_ACCEPTANCE_TEST:'+t['id'])
  seen.add(t['id'])
  for uid in dict.fromkeys([t['unit'],*t.get('additional_units',[]),*plan.get('acceptance_owner_extensions',{}).get(t['id'],[])]):
   if uid not in result:raise ValueError('UNKNOWN_ACCEPTANCE_UNIT:'+uid)
   result[uid].append(t['id'])
 return result
def scope_summary(plan,requirements,tests,surfaces,actions):
 return f'{len(requirements)} requirements; {len(tests)} planned test contracts; all {len(surfaces)} contexts and {len(actions)} inherited actions; all new loops before BG; no claim of new all-branch semantic certification'
def binding_errors(plan,tests,summary):
 expected=acceptance_index(plan,tests);errors=[]
 if plan.get('acceptance_contract_source')!='verification/TEST_CONTRACTS.json':errors.append('WRONG_ACCEPTANCE_SOURCE')
 if plan.get('preservation_invariant')!=summary:errors.append('STALE_SCOPE_SUMMARY')
 for u in plan['units']:
  if u.get('acceptance_test_ids')!=expected[u['id']]:errors.append('STALE_UNIT_ACCEPTANCE:'+u['id'])
 return errors
def current_scope(plan,requirements,tests):
 return scope_summary(plan,requirements,tests,read('design/ALL_SURFACE_CONTRACTS.json')['surfaces'],read('traceability/LEGACY_349_ACTIONS.json')['actions'])
def sync_acceptance():
 plan=read('plan/DEVELOPMENT_PLAN.json');tests=read('verification/TEST_CONTRACTS.json')['tests'];requirements=read('traceability/REQUIREMENTS_AND_DU_MAPPING.json')['requirements']
 index=acceptance_index(plan,tests)
 for u in plan['units']:u['acceptance_test_ids']=index[u['id']]
 plan['acceptance_contract_source']='verification/TEST_CONTRACTS.json'
 plan['acceptance_binding_rule']='Generated from inherited owners plus mandatory Rev1.18 owner extensions; effective registry governs execution assertions; no execution results fabricated.'
 plan['preservation_invariant']=current_scope(plan,requirements,tests)
 (ROOT/'plan/DEVELOPMENT_PLAN.json').write_text(json.dumps(plan,indent=2,sort_keys=True)+'\n')
 print('Generated unit acceptance references and scope summary; refresh unsigned scope lock, then render the plan.')
def render():
 plan=read('plan/DEVELOPMENT_PLAN.json');req=read('traceability/REQUIREMENTS_AND_DU_MAPPING.json')['requirements'];tests=read('verification/TEST_CONTRACTS.json')['tests'];aliases=read('traceability/FORECAST_PACKET_CROSSWALK.json')['mappings']
 errors=binding_errors(plan,tests,current_scope(plan,req,tests))
 if errors:raise ValueError(';'.join(errors))
 units=plan['units'];by={u['id']:u for u in units};rq={r['id']:r for r in req};testby={t['id']:t for t in read(plan['effective_test_registry'])['tests']}
 inputs=['contracts/whole_product/ARCHITECTURE_REV118.md','contracts/whole_product/ACCEPTANCE_REFINEMENTS.json','contracts/whole_product/ACTION_CONTRACTS.json','contracts/whole_product/DOMAIN_SCENARIOS.json','contracts/whole_product/PROTOCOLS.json','contracts/whole_product/RECORDS.schema.json','verification/EFFECTIVE_TEST_CONTRACTS_REV118.json','plan/compile_rev118.py','design/DARK_THEME_READABILITY_AMENDMENT_20261021.md','design/THEME_READABILITY_CONTEXT_BINDINGS.json','traceability/REV117_REQUIREMENTS.json','verification/REV117_ACCEPTANCE_CONTRACTS.json','contracts/self_optimization/MODEL_USE_CONTRACT.json','contracts/self_optimization/MODEL_USE_RECORDS.schema.json','research/PROFITABILITY_EXPERIMENTS.json','design/MODEL_HARDENING_CONTEXT_BINDINGS.json','traceability/REV116_REQUIREMENTS.json','verification/REV116_ACCEPTANCE_CONTRACTS.json','contracts/self_optimization/EXPERIENCE_LEARNING_CONTRACT.json','contracts/self_optimization/EXPERIENCE_LEARNING_RECORDS.schema.json','design/EXPERIENCE_LEARNING_CONTEXT_BINDINGS.json','CANONICAL_AUTHORITY.json','plan/DEVELOPMENT_PLAN.json','traceability/REQUIREMENTS_AND_DU_MAPPING.json','contracts/BACKEND_SERVICE_CATALOG.json','verification/TEST_CONTRACTS.json','design/ALL_SURFACE_CONTRACTS.json','traceability/LEGACY_349_ACTIONS.json','traceability/FORECAST_PACKET_CROSSWALK.json','plan/PROPOSED_SCOPE_LOCK.json','plan/render_plan.py','VATI_SELF_OPTIMIZING_EXECUTION_AND_CRYPTO_BLUEPRINT_REV5_20261018.md','contracts/self_optimization/STATE_MACHINES.json','contracts/self_optimization/PROOF_PREDICATES.json','contracts/self_optimization/SEMANTIC_INVARIANTS.json','contracts/self_optimization/AUTHORITY_MATRIX.json','contracts/self_optimization/SELF_OPTIMIZATION_RECORDS.schema.json','ASTRA_CODEX_REVIEW_AND_OPTIMIZATION_PROMPT.md','traceability/REV115_REQUIREMENTS.json','verification/REV115_ACCEPTANCE_CONTRACTS.json','review/DESIGN_CHANGE_PROPOSALS.json','review/SOURCE_ADMISSION_CROSSWALK.json']
 hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs}
 digest=hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 lines=['# VAN Next — One Deterministic Backend-First Development Plan, Rev 1.18','',f'**Project:** `{plan["project_id"]}` · **Source baseline:** `{plan["source_commit"]}`','**Status:** prepared consolidation candidate. No owner signature, F15, Backend Complete or release authority is issued by this plan. Every unit is FULL and NOT_STARTED until a valid scoped receipt establishes its actual state.','',f'**Active graph:** {len(units)} packets; {len(plan["required_backend_ids"])} backend capabilities; {len(plan["required_backend_verification_ids"])} backend-verification units. **BG-001:** {by["BG-001"]["packet_id"]}; **first new UX:** {by["UX-001"]["packet_id"]}.','', '## 1. Execution rules','', '1. Predevelopment PRE-001 → PRE-002 → independent PRE-003 F15 precedes any code-bearing source consolidation or implementation. The current documentary reconciliation is not a claimed signed packet exit.','2. Complete all backend operations, integration and negative/recovery evidence; then independently close BG-001. No new frontend, visual prototype, native design golden, chart/orb renderer, theme or app shell starts beforehand. Old five UI flows are eventual integration scenarios, not early work authorization.','3. Prefer one packet at a time in the generated sequence. Parallel work requires explicit assigned ownership, isolated worktrees and all dependency exits; it never changes stage or gate order.','4. Each packet has its own approved acceptance contract binding exact source/configuration, complete operations, caller/authority/readback, test commands, negative cases, rollback and reviewer. A row in this plan is not itself that signed executable contract.','5. PRE-001–003 use no-application-change preservation inventory checks. BE-001 builds and qualifies the actual parity checker, including an induced failure. Every subsequent implementation exit requires no feature loss, on top of each unit’s own acceptance.','6. Preserve all inherited owner actions, source functions and new feature contracts. A completed showcase, test count or registered URL never substitutes for full effect/recovery proof. Changes to the lock require a new explicit owner-reviewed amendment; no default retirement.','7. Research automation uses standing bounded research grants. Evaluator BE-035 must qualify before economic claims or BE-036 research-loop promotion; all failed experiments remain inspectable. Owner-signed financial/live transitions remain separate.','8. A missing required provider integration or backend defect keeps its gate blocked; unrelated backend work may proceed if dependencies allow. New design revealing a backend omission reopens BG and pauses affected frontend work.','9. F15, BG, native-device qualification and live financial authority are independent evidence states. The plan checker verifies obligations and order; a real receipt verifier must validate issuer, signature, scope, freshness and revocation.','', '10. Automatic operational optimization selects within qualified algorithms/parameter domains. Governed policy evolution changes consequential bindings only through authorized independent qualification/promotion. Both full lifecycles feed BG-001; research training or a graph PASS grants neither authority nor profit.', '11. Actual CEX spot trading is mandatory new software scope. Preserve other markets and read-only chain/event research. Product/venue qualifications are real target gates; static mocks cannot prove matching or settlement. No wallet signing, derivatives or withdrawal authority is inferred.', '', '## 2. Immutable inputs for this rendered plan','', '| Input | SHA-256 |','|---|---|']
 lines += [f'| `{p}` | `{h}` |' for p,h in hashes.items()]
 lines += ['',f'**Aggregate input digest:** `{digest}`. Deterministic canonical JSON of the filename→SHA-256 map, UTF-8; no timestamps in generated output.','', '## 3. Entire packet sequence','', '| Packet | Unit | Kind | Complete outcome | Prerequisites |','|---|---|---|---|']
 for u in units:lines.append(f'| {u["packet_id"]} | {u["id"]} | {u["kind"]} | {cell(u["title"])} | {", ".join(by[x]["packet_id"] for x in u["dependencies"]) or "—"} |')
 lines += ['', '## 4. Source-plan reconciliation','', 'The 76 parent Rev1.10 units and all 48 forecast packet obligations are preserved or explicitly merged. Old packet IDs are lookup aliases only. There is one F15, one global frontend-opening BG and one release chain. No child closure can authorize UI.','', '| Source forecast packet | Canonical unit | Current packet | Disposition |','|---|---|---|---|']
 for a in aliases:lines.append(f'| {a["source_id"]} | {a["canonical_unit"]} | {by[a["canonical_unit"]]["packet_id"]} | {a["disposition"]} |')
 lines += ['', '## 5. Exact per-packet completion contracts','']
 for u in units:
  ids=plan['requirement_ownership'].get(u['id'],[])
  lines += [f'### {u["packet_id"]} — {u["id"]}: {u["title"]}',f'**Kind/stage:** {u["kind"]} / {u["stage"]}. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.',f'**Entry prerequisites:** {", ".join(u["dependencies"]) or "read-only source access and approved packet scope"}.',f'**Requirement owners:** {", ".join(ids) or "integration/qualification evidence for every dependent required capability"}.','', '**Exit contract:** '+u['exit_contract'],'']
  if u.get('full_deliverables'):lines+=['**All deliverables:**']+[f'- {x}' for x in u['full_deliverables']]+['']
  for ob in u.get('merged_obligations',[]):lines += [f'**Merged obligation {ob["source_packet"]}:**']+[f'- {x}' for x in ob['deliverables']]+[f'- Evidence: {x}' for x in ob['exit_evidence']]+['']
  ts=[testby[tid] for tid in u['acceptance_test_ids']]
  if ts:lines+=['**Planned test obligations (all NOT_RUN):**']+[f'- `{t["id"]}` — {t.get("expectation",t.get("contract","Explicit source test contract"))}' for t in ts]+['']
  for t in ts:
   for scenario in t.get('whole_product_scenarios',[]):
    lines += [f"- Rev1.18 scenario `{scenario['id']}` ({scenario['kind']}): {scenario['oracle']}"]
  lines += ['**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.','']
 lines += ['## 6. Owner decisions and signed activation','', 'OQ-21 values are accepted by OD-39 and are not reopened. Their runtime policy binding and activation still require the exact signed mandate. Current owner questions remain in the source record until resolved; unavailable or stale signatures cannot be replaced by code defaults.','', '| ID | State | Question |','|---|---|---|']
 for q in plan['owner_questions']:lines.append(f'| {q["id"]} | {cell(q.get("status","UNRESOLVED"))} | {cell(q.get("text",q.get("question","See exact owner decision record")))} |')
 lines+=['','## 7. Completion does not imply profitability','', 'A properly functioning strategy/model evaluator may find no qualified live candidate. Retain that truthful result; it is not grounds to thin the required research software or promote a weak strategy. No live financial action, new provider subscription or network change is authorized by this specification.','']
 return '\n'.join(lines),hashes,digest

def main():
 ap=argparse.ArgumentParser();mode=ap.add_mutually_exclusive_group();mode.add_argument('--check',action='store_true');mode.add_argument('--sync-acceptance',action='store_true');args=ap.parse_args()
 if args.sync_acceptance:sync_acceptance();return 0
 text,hashes,digest=render();p=ROOT/'plan/VAN_NEXT_DETERMINISTIC_PLAN_REV1_18.md';prov=ROOT/'plan/PLAN_INPUT_PROVENANCE.json'
 info=json.dumps({'schema':'van.canonical.plan.provenance/1.0','inputs':hashes,'aggregate_input_digest':digest,'rendered_plan_sha256':hashlib.sha256(text.encode()).hexdigest(),'scope':'Deterministic document identity only; not owner signature or F15'},indent=2,sort_keys=True)+'\n'
 if args.check:
  errors=[]
  if not p.exists() or p.read_text()!=text:errors.append('STALE_RENDERED_PLAN')
  if not prov.exists() or prov.read_text()!=info:errors.append('STALE_PLAN_PROVENANCE')
  print('\n'.join(errors) if errors else '0 findings: rendered plan and input provenance match')
  return 1 if errors else 0
 p.write_text(text);prov.write_text(info);print(f'Rendered {p.name}, {len(text.splitlines())} lines; digest {digest}');return 0
if __name__=='__main__':
 try:raise SystemExit(main())
 except (ValueError,OSError,KeyError) as e:print(str(e),file=sys.stderr);raise SystemExit(2)
