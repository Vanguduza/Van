#!/usr/bin/env python3
"""Reproducibly integrate the reviewed HVA specification into a copied Rev1.11 pack.
No application source is changed and no authority certificate is issued.
"""
from __future__ import annotations
import argparse
import copy,hashlib,importlib.util,json,pathlib,re,shutil,subprocess,sys,zipfile
from hva_spec import ROWS,UNITS,REV,PROJECT,SOURCE_SHA
from hva_contracts import P,schema,example
WORK=pathlib.Path(__file__).resolve().parent
PARENT=WORK/'parent'
OUT=pathlib.Path('/mnt/data/VAN_NEXT_UNIFIED_REBUILD_REV1_12_20261017')
OLDMASTER='VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_11_20261017.md'
MASTER='VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_12_20261017.md'
PARENT_ZIP=pathlib.Path('/mnt/data/files/VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_PACK_REV1_11_20261017.zip')
SOURCE_BLUEPRINT=pathlib.Path('/mnt/data/VAN_HIGH_VALUE_TRADING_ADOPTIONS_BLUEPRINT_REV1_2026-10-17.md')
REVIEW_PACK=pathlib.Path('/mnt/data/VAN_HIGH_VALUE_ADOPTIONS_REVIEW_PACK_REV1_20261017.zip')
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def sha(b):return hashlib.sha256(b).hexdigest()
def load(p):return json.loads((OUT/p).read_text())
def write(p,x):
 q=OUT/p;q.parent.mkdir(parents=True,exist_ok=True)
 q.write_text(json.dumps(x,indent=2,sort_keys=True,ensure_ascii=False)+'\n' if not isinstance(x,str) else x)
def loadmod(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def build():
 if OUT.exists():shutil.rmtree(OUT)
 shutil.copytree(PARENT,OUT)
 # Old delivery receipts are historical. Move all old evidence out of the current-evidence directory.
 for p in list((OUT/'evidence').glob('*')):
  if p.is_file():
   d=OUT/'lineage/rev1_11/evidence'/p.name;d.parent.mkdir(parents=True,exist_ok=True);p.rename(d)
 oldplan=load('plan/DEVELOPMENT_PLAN.json');plan=copy.deepcopy(oldplan);units={u['id']:u for u in plan['units']}
 reqs=load('traceability/REQUIREMENTS_AND_DU_MAPPING.json');tests=load('verification/TEST_CONTRACTS.json');services=load('contracts/BACKEND_SERVICE_CATALOG.json');surfaces=load('design/ALL_SURFACE_CONTRACTS.json')
 # Preserve each old full exit contract; reviewed extensions are additive.
 for uid,title,deps,deliverables,owner,models,seam,negative in UNITS:
  units[uid]={'id':uid,'title':title,'kind':'BACKEND','stage':1,'dependencies':deps,'completion':'FULL','status':'NOT_STARTED','implementation_evidence':[],'receipt_required':True,'source_origin':'OWNER_DIRECTED_REVIEWED_HIGH_VALUE_INTEGRATION_REV1.12','full_deliverables':deliverables,
   'exit_contract':f'Complete all stated operations in the existing owners. {seam}. Verify a real registered positive caller/readback, negative and recovery paths under exact source/provider scope. {negative} No fixture substitutes for required real provider integration, and no research result grants financial authority.'}
  services['services'].append({'id':uid,'title':title,'dependencies':deps,'operations':deliverables,'authority':owner+'; read-only additive; no new financial authority','models':models,'producer_store_consumer':seam,'adversarial_acceptance':negative,'completion':'FULL_REQUIRED_BEFORE_BG001','implementation_status':'SPECIFIED_NOT_IMPLEMENTED','status':'NOT_BUILT_BY_THIS_BLUEPRINT','target_source_head':SOURCE_SHA,'logical_boundary':'Extend existing service owners; not a mandatory separate microservice.'})
 for uid,title,ds,deliverables in [
  ('BQ-008','Independent chain-provider, security and finality qualification',[f'BE-{i:03}' for i in range(37,45)],['Verify documented permitted read-only provider calls and source state, all chain analyzers and versioned histories.','Prove end-to-end identity, complete cohort, security/sellability and invalidation behavior with no signing/custody path.','Reproduce meaningful failure, restart, quota, source-revocation and reorg cases on actual qualified DIAL topology; absent mandatory external integration remains blocked.']),
  ('BQ-009','Independent economics, cohort, evidence and advisory-authority qualification',['BE-044','BE-035','BE-036','VAN-ML-PKT-030','VAN-ML-PKT-031'],['Independently verify fact/forecast/edge separation, nonlinear account replay, target calibration and statistical policy.','Reconcile all discovery outcomes and false-positive costs; prove no simulated result is promoted to a realized venue fact.','Exercise existing Jev/evidence/allocator contracts, decline cases and mandatory exits; no new order authority or early frontend.'])]:
  units[uid]={'id':uid,'title':title,'kind':'BACKEND_VERIFICATION','stage':2,'dependencies':ds,'completion':'FULL','status':'NOT_STARTED','implementation_evidence':[],'receipt_required':True,'source_origin':'REVIEWED_HIGH_VALUE_INTEGRATION_REV1.12','full_deliverables':deliverables,'exit_contract':'Independent source-bound review of all listed obligations and actual positive/adversarial/recovery receipts. No author self-certification, document-only substitution, waived provider capability, automatic economic promotion or new financial permission.'}
 for consumer,ds in {'BE-032':['BE-044'],'VAN-ML-PKT-030':['BE-044'],'BQ-006':['BQ-008','BQ-009']}.items():
  units[consumer]['dependencies']=sorted(set(units[consumer]['dependencies']+ds))
 for uid in ['BQ-001','BQ-002','BQ-003','BQ-004','BQ-005']:
  units[uid]['dependencies']=sorted(set(units[uid]['dependencies']+['BE-044']))
 # Existing consumers gain explicit deliverables, not new independent control planes.
 extra={
  'PRE-001':'Revalidate the 66-head inventory and exact feature-bearing blobs; inspect changes since the sealed review rather than assume a branch name implies code.',
  'PRE-002':'Independently admit HVA R01–R12 mappings, separate research-source and implementation evidence namespaces, and all retained requirements before F15.',
  'BE-001':'Reconcile the five account coordinator/service variants by function and contract, preserving PR101 fixes, canon Jev/evidence and signed temperament work. Never wholesale-select the most populated branch.',
  'BE-010':'Retain PR101 pending-order progress; close worse-than-limit fills, expiry-policy propagation, pending-stop protection and terminal-order semantics before economic use.',
  'BE-013':'Do not equate existing AllocatorV1 with calibrated model-weighted ranking. Specify a separately reviewed policy version without adding sizing/reservation authority.',
  'BE-021':'Extend registered trading evidence questions through the existing shared dial-jev consumer; answer quality is not a profitable-trade probability.',
  'BE-032':'Include every new read-only domain capability and actual unavailable/provider/runtime states in the existing capability catalogue.',
  'BE-035':'Preserve all current evaluator corrections: directional intrabar ambiguity, executable timing, limit prices, full cash charges, post-liquidation equity and account-coordinator parity.',
  'VAN-ML-PKT-005':'Domain datasets retain all discovered/rejected/missing/migrated candidates through BE-038/044 joins, without blocking generic dataset development on an unavailable crypto source.',
  'VAN-ML-PKT-007':'Separate terminal return, strategy outcome, adverse excursion, stop touch and fill targets; distinguish observed quotes from modeled cost distributions.',
  'VAN-ML-PKT-010':'Replay both whole-policy accounts independently, with nonlinear fees/liquidity, changed trade paths, cash and margin; retain size-only attribution as its separately labelled existing view.',
  'VAN-ML-PKT-020':'Apply one existing calibration policy with distinct target/model/horizon/state bindings; no source grade or judgment confidence can substitute.',
  'VAN-ML-PKT-027':'Retain full discovery cohorts, delayed/censored outcomes and transitive invalidation lineage; no synthetic receipt may enter realized performance.',
  'VAN-ML-PKT-030':'Require domain-cohort studies and dependence-aware materiality/sample/multiple-testing analysis; no unversioned competing 95-percent policy gate.',
  'FE-023':'After BG-001 only, implement the six new context/detail projections within existing navigation, in both locked themes. No new global tab, wallet or trade button.'}
 for uid,text in extra.items():units[uid].setdefault('full_deliverables',[]).append(text)
 for s in services['services']:
  if s['id'] in extra:s['operations'].append(extra[s['id']]);s.setdefault('reviewed_extensions',[]).append('HVA-REV1.12')
  s['dependencies']=units[s['id']]['dependencies']
 backend=sorted(i for i,u in units.items() if u['kind']=='BACKEND');bv=sorted(i for i,u in units.items() if u['kind']=='BACKEND_VERIFICATION')
 units['BG-001']['dependencies']=sorted(backend+bv)
 remaining=set(units);done=[]
 while remaining:
  ready=[units[i] for i in remaining if set(units[i]['dependencies'])<=set(done)]
  if not ready:raise ValueError('CYCLE_OR_MISSING:'+str(remaining))
  u=min(ready,key=lambda u:(u['stage'],u.get('lane_order',0),u['id']));done.append(u['id']);remaining.remove(u['id'])
 for n,i in enumerate(done,1):units[i]['packet_id']=f'VAN-PKT-{n:03}';units[i]['sequence']=n
 plan.update(revision=REV,units=[units[i] for i in done],required_backend_ids=backend,required_backend_verification_ids=bv)
 # Requirement/test records from the parent remain byte-equivalent as canonical objects.
 for n,title,bs,fs,other,review,text,pos,neg,rec in ROWS:
  rid=f'VAN-HVA-{n:03}';b=[i for i in bs if units[i]['kind']=='BACKEND'];o=list(dict.fromkeys(other+[i for i in bs if units[i]['kind']!='BACKEND']))
  reqs['requirements'].append({'id':rid,'title':title,'text':text,'acceptance':{'positive':pos,'adversarial':neg,'recovery':rec},'backend_units':b,'frontend_units':fs,'other_units':o,'review_findings':review.split('/'),'status':'SPECIFIED_NOT_IMPLEMENTED','mapping_grade':'OWNER_DIRECTED_INTEGRATION_PENDING_INDEPENDENT_SEMANTIC_ADMISSION','test_id':f'T-HVA-{n:03}-POS','source_adoption_ids':[]})
  owners=list(dict.fromkeys(b+o))
  for suffix,expectation in [('POS',pos),('NEG',neg),('REC',rec)]:
   tests['tests'].append({'id':f'T-HVA-{n:03}-{suffix}','unit':owners[0],'additional_units':owners[1:],'environment':'QUALIFIED_DIAL_TEST_TOPOLOGY_WITH_REAL_BOUND_PROVIDER_WHERE_REQUIRED','execution_state':'NOT_RUN','expectation':expectation,'receipt_required':True,'scope_revision':REV,'requirement_id':rid,'evidence_boundary':'Test contract only; not the document checker or a synthetic provider receipt.'})
 reqs.update(total=len(reqs['requirements']),high_value_addition_requirements=len(ROWS))
 contexts=[
  ('DISCOVERY','Candidate discovery and rejection funnel',['BE-038','BE-044'],[12,13,14,31],'Show observed/rejected/unknown/research-eligible counts with source age; unfold candidate evidence, no trading CTA.'),
  ('SECURITY','Chain security and capability findings',['BE-039','BE-040','BE-043'],[15,16,19],'Show REJECT/INVESTIGATE/NO_HARD_BLOCK, affected state and concrete reasons. No safe-to-buy badge.'),
  ('WALLET','Temporal wallet and concentration evidence',['BE-042','BE-043'],[20,21,22,23],'Show raw versus adjusted holdings, time interval, source roles and uncertainty; no ownership certainty from heuristics.'),
  ('SELLABILITY','State-bound route and executable economics',['BE-041','BE-043'],[5,17,18],'Show buy/sell simulation distinction, quote size/state/expiry and observed versus modeled costs.'),
  ('COHORT','Whole-policy experiment and missing-outcome review',['BE-044','VAN-ML-PKT-010','VAN-ML-PKT-027'],[6,24,25,26],'Show same-universe arms, distinct cash paths, uncertainty, rejected/censored cases and cost assumptions; never simulated as realized.'),
  ('JUDGMENT','Typed judgment provenance and contribution',['BE-021','BE-044'],[27,28,29,30],'Show registered question, supplied evidence, abstention and answer-quality semantics, with no hard-filter or exit override.')]
 for key,title,bs,ns,fold in contexts:
  rid=f'CTX-HVA-{key}';tid=f'T-CTX-HVA-{key}'
  surfaces['surfaces'].append({'id':rid,'title':title,'domain':'Trading / Intelligence / Research — existing contextual navigation','backend_units':bs,'frontend_units':['FE-023'],'first_fold':fold,'dark_light':'Both original locked tactile themes, measured native goldens only after BG-001; semantic labels and accessible detail.','states':['SYNTHETIC','OBSERVED','DELAYED','UNKNOWN','STALE','REVOKED','UNAVAILABLE'],'van_requirements':[f'VAN-HVA-{i:03}' for i in ns],'test_id':tid,'authority_rule':'Read-only navigation and evidence inspection. No wallet, new order sender, signing or new financial permission.','presentation':'CONTEXT_OR_DETAIL_NOT_NEW_GLOBAL_TAB','route_candidate':None,'binding_status':'SPECIFIED_PENDING_NATIVE_ACCEPTANCE','control_contracts':[{'owner_goal':title,'presentation_rule':fold,'backend_operations_source':'contracts/BACKEND_SERVICE_CATALOG.json'}],'evidence_grade':'CONTRACT_ONLY_NOT_RENDERED'})
  tests['tests'].append({'id':tid,'unit':'FE-023','additional_units':['QA-004','QA-005'],'environment':'ACTUAL_OWNER_ANDROID_DEVICE_AFTER_BG001','execution_state':'NOT_RUN','expectation':fold+' Exercise both themes, accessible labels, unavailable/reorg states, navigation/restoration and prove no financial action from this read-only context.','receipt_required':True,'scope_revision':REV})
 surfaces.update(total_context_obligations=len(surfaces['surfaces']),high_value_context_additive_count=6)
 tests['count']=len(tests['tests'])
 plan['requirement_ownership']={i:sorted(r['id'] for r in reqs['requirements'] if i in r.get('backend_units',[])+r.get('frontend_units',[])+r.get('other_units',[])) for i in done}
 write('plan/DEVELOPMENT_PLAN.json',plan);write('contracts/BACKEND_SERVICE_CATALOG.json',services);write('traceability/REQUIREMENTS_AND_DU_MAPPING.json',reqs);write('verification/TEST_CONTRACTS.json',tests);write('design/ALL_SURFACE_CONTRACTS.json',surfaces)
 counts={'requirements':reqs['total'],'nodes':len(done),'backend':len(backend),'backend_verification':len(bv),'surfaces':len(surfaces['surfaces']),'actions':349,'atoms':171,'features':93,'truth':18,'forecast_aliases':48,'tests':tests['count']}
 assert counts=={'requirements':237,'nodes':131,'backend':82,'backend_verification':12,'surfaces':234,'actions':349,'atoms':171,'features':93,'truth':18,'forecast_aliases':48,'tests':1287},counts
 # Update active selector, never repository-level or issued authority.
 authority=load('CANONICAL_AUTHORITY.json');authority.update(revision=REV,master=MASTER,rendered_plan='plan/VAN_NEXT_DETERMINISTIC_PLAN_REV1_12.md',status='OWNER_DIRECTED_SCOPE_INTEGRATION_CANDIDATE_INDEPENDENT_ADMISSION_PENDING')
 authority['superseded_schedules'].append('Rev1.11 plan: preserved as lineage, replaced in this delivered candidate only')
 write('CANONICAL_AUTHORITY.json',authority)
 cross=load('traceability/REV110_PACKET_CROSSWALK.json')
 for a in cross['mappings']:a['canonical_packet_id']=units[a['canonical_unit']]['packet_id']
 write('traceability/REV110_PACKET_CROSSWALK.json',cross)
 write('traceability/REV111_PACKET_CROSSWALK.json',{'schema':'van.revision-qualified.packet-crosswalk/1.0','source_revision':'1.11','target_revision':REV,'stable_unit_ids_preserved':True,'mappings':[{'unit_id':u['id'],'source_packet_id':u['packet_id'],'target_packet_id':units[u['id']]['packet_id'],'source_revision':'1.11','target_revision':REV,'all_original_deliverables_preserved':True} for u in oldplan['units']]})
 runtime=load('verification/RUNTIME_EXTERNAL_QUALIFICATION_MATRIX.json')
 for uid,*_ in UNITS:
  runtime['capabilities'].append({'id':uid,'environment':'Actual qualified Netcup/Oracle DIAL test topology; existing permitted read-only provider access; no on-chain transaction.','financial_activation':'NONE from additive. Existing financial paths remain sovereign.','gate':'BG-001','source_state':'SPECIFIED_NOT_IMPLEMENTED','source_head':SOURCE_SHA,'required_receipts':['exact source/schema/provider version','real registered producer/store/consumer and independent readback','positive and negative semantics','interruption/reorg/revocation recovery','permitted source scope and actual integration proof'],'invalidate_on':['state revision/reorg','source permission expiry','schema/policy/model change','evidence expiry'],'no_procurement':'No purchase/account task. Required unverified source remains not qualified; unrelated work may proceed.'})
 write('verification/RUNTIME_EXTERNAL_QUALIFICATION_MATRIX.json',runtime)
 # Documentary adoption/correction crosswalk; no existing IDs or correction text is removed.
 adopt={1:[1,5,17,18],2:[1,7,29,30],3:[6,12,23,24,25,26],4:[8,9,10,11,12,13,14],5:[15,16,17,19,20,21,22],6:[3,27,28,30],7:[1,7,10,26],8:[2,4,31,32]}
 xwalk=[]
 for n,ns in adopt.items():
  rs=[r for r in reqs['requirements'] if r['id'] in [f'VAN-HVA-{i:03}' for i in ns]]
  xwalk.append({'adoption_id':f'VAN-A{n:02}','disposition':'ADD_READ_ONLY_DOMAIN_CAPABILITY' if n in [4,5] else 'EXTEND_EXISTING_OWNER_AND_RETAIN_FULL_SCOPE','requirement_ids':[r['id'] for r in rs],'units':sorted({u for r in rs for k in ['backend_units','frontend_units','other_units'] for u in r[k]}),'test_contract_ids':[t['id'] for t in tests['tests'] if t.get('requirement_id') in {r['id'] for r in rs}]})
 write('traceability/HIGH_VALUE_ADOPTION_CROSSWALK.json',{'schema':'van.hva.crosswalk/1.0','active_plan':'plan/DEVELOPMENT_PLAN.json','adoptions':xwalk})
 review=[]
 for n in range(1,13):
  key=f'R{n:02}';rs=[r for r in reqs['requirements'] if key in r.get('review_findings',[])]
  review.append({'id':key,'documentary_disposition':'INTEGRATED_IN_REV1.12','implementation_state':'NOT_IMPLEMENTED_BY_THIS_PACK','requirements':[r['id'] for r in rs],'units':sorted({i for r in rs for k in ['backend_units','frontend_units','other_units'] for i in r[k]}),'acceptance_contracts':[t['id'] for t in tests['tests'] if t.get('requirement_id') in {r['id'] for r in rs}]})
 write('traceability/REVIEW_FINDINGS_DISPOSITION.json',{'schema':'van.hva.review-disposition/1.0','findings':review})
 gaps=load('verification/GAP_CLOSURE_REGISTER.json')
 for r in review:gaps['items'].append({'id':'GAP-HVA-'+r['id'],'requirement_ids':r['requirements'],'owner_units':r['units'],'first_gate':'PRE-003' if r['id'] in ['R01','R02','R03','R04','R05','R06'] else 'BG-001','state':'SPECIFICATION_INTEGRATED_APPLICATION_EVIDENCE_NOT_RUN','waiver_allowed':False,'required_evidence':r['acceptance_contracts']})
 write('verification/GAP_CLOSURE_REGISTER.json',gaps)
 register=load('consolidation/IMPLEMENTATION_ADMISSION_REGISTER.json')
 for a in xwalk:register['items'].append({'id':'ADP-HVA-'+a['adoption_id'],'capability':a['adoption_id'],'canonical_units':a['units'],'disposition':a['disposition'],'source_paths_or_refs':['lineage/high_value_rev1_0/SOURCE_BLUEPRINT.md','consolidation/review/VAN_HIGH_VALUE_ADOPTIONS_COMPARATIVE_REVIEW_REV1_20261017.md'],'implementation_acceptance':'NOT_GRANTED_BY_DOCUMENT','implementation_evidence_level':'SPEC_ONLY','research_source_class':'NOT_APPLICABLE','requirement_ids':a['requirement_ids']})
 write('consolidation/IMPLEMENTATION_ADMISSION_REGISTER.json',register)
 # Retain reviewed sources, not copied source implementations.
 upload=SOURCE_BLUEPRINT.read_bytes();write('lineage/high_value_rev1_0/SOURCE_BLUEPRINT.md',upload.decode())
 rz=zipfile.ZipFile(REVIEW_PACK)
 for n in rz.namelist():
  if n.endswith('/'):continue
  rel=pathlib.PurePosixPath(n).name
  dest=OUT/'consolidation/review'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(rz.read(n))
 source=load('consolidation/SOURCE_REGISTER.json');source['sources'].extend([
  {'id':'HVA_SOURCE_REV1.0','path':'lineage/high_value_rev1_0/SOURCE_BLUEPRINT.md','sha256':sha(upload),'scope':'Owner-provided source; corrected by current integrated specification, not a second roadmap.'},
  {'id':'HVA_ALL_BRANCH_REVIEW','path':'consolidation/review','zip_sha256':'04789cac604de8c0225a04175eb0eba47722a2291e661ce2566f014b74dc4a06','scope':'66 heads /63 unique commits, 4634 union paths,3680 UTF8 blobs; selective semantic review, not full semantic certification.'},
  {'id':'HVA_REF_REFRESH','request_id':'van-hva-integrate-discover-run-20261017-01','observed_at':'2026-10-17T18:17:00Z','time_semantics':'Approximate minute of this turn; raw typed receipt remains authoritative.','head_count':66,'changed_refs':{},'scope':'Fresh advertised refs match the sealed review; no source tests rerun.'}])
 write('consolidation/SOURCE_REGISTER.json',source)
 write('consolidation/OWNER_SCOPE_DIRECTION_REV1_12.json',{'schema':'van.owner-requested.specification-direction/1.0','project_id':PROJECT,'owner_message':'Proceed according to your recommendations','basis':'Comparative review R01–R12 and explicit current user message','scope':'Integrate reviewed additions into the complete single unified blueprint and its plan; read-only crypto domain engineering scope included.','not_granted':['application implementation certification','F15','BG-001','live trading mandate','wallet custody/signing','procurement','blanket branch merge'],'signature':None,'formal_admission':'PENDING_INDEPENDENT_SEMANTIC_AND_EXISTING_OWNER_SIGNATURE_PROCESS','record_kind':'SOURCE_OF_SPECIFICATION_DIRECTION_NOT_CRYPTOGRAPHIC_APPROVAL'})
 for n in P:
  write(f'contracts/high_value/{n}.schema.json',schema(n));write(f'contracts/high_value/examples/{n}.fixture.json',example(n))
 shutil.copy2(WORK/'verify_hva_contracts.py',OUT/'verification/verify_hva_contracts.py')
 # Retained parent checker, same negative suite, expanded exact scope.
 v=(OUT/'verification/verify_unified.py').read_text();v=re.sub(r'EXPECTED_COUNTS=\{[^\n]+\}',lambda m:'EXPECTED_COUNTS='+repr(counts),v,count=1);v=v.replace(OLDMASTER,MASTER);write('verification/verify_unified.py',v)
 v=(OUT/'plan/render_plan.py').read_text().replace('Rev 1.11','Rev 1.12').replace('REV1_11','REV1_12');write('plan/render_plan.py',v)
 for f in ['verification/F15_CERTIFICATE.json','verification/BACKEND_COMPLETE_CERTIFICATE.json']:
  d=load(f)
  for k in d:
   if 'revision' in k and d[k]=='1.11':d[k]=REV
  write(f,d)
 # Master source in full; only active summaries revised. Historical audit and product text retained.
 text=(OUT/OLDMASTER).read_text()
 text=text.replace('VAN-NEXT-UNIFIED-REV1.11-20261017','VAN-NEXT-UNIFIED-REV1.12-20261017').replace('**Revision:** 1.11 — one consolidated specification and deterministic development plan','**Revision:** 1.12 — reviewed high-value adoptions integrated into the single full-scope plan')
 text=text.replace('**205 active requirements**','**237 active requirements** (the 205 inherited objects preserved, plus 32 VAN-HVA requirements)')
 text=text.replace('**228 context obligations** (216 inherited plus 12 consolidated additions)','**234 context obligations** (228 retained plus six new read-only context/detail obligations)')
 text=text.replace('**121 full-scope packets**: 3 predevelopment; 74 backend; 10 backend-verification','**131 full-scope packets**: 3 predevelopment; 82 backend; 12 backend-verification')
 text=text.replace('**205 requirements; 121 FULL-scope units/packets.**','**237 requirements; 131 FULL-scope units/packets.**')
 text=text.replace('the 74 backend IDs and 10 backend-verification IDs','the 82 backend IDs and 12 backend-verification IDs')
 text=text.replace('## What was actually verified during consolidation','## Historical Rev1.11 verification (retained, not newly rerun by authoring Rev1.12)')
 text=text.replace('**End of the single canonical Rev 1.11 specification.**','**End of the single canonical Rev 1.12 specification.**')
 chapter=(WORK/'integration_chapter.md').read_text()
 marker=next((x for x in ['## Appendix A','## Appendix'] if x in text),None)
 if marker:text=text.replace(marker,chapter+'\n\n'+marker,1)
 else:text+='\n\n'+chapter
 text=text.replace('**Active authority selector:**','**Rev1.12 owner direction:** integrate the reviewed recommendations, including read-only crypto scope. Independent F15/BG and financial authority remain unissued. §30 governs the reviewed integration; source lineage remains preserved.\n\n**Active authority selector:**',1)
 write(MASTER,text);(OUT/OLDMASTER).unlink()
 # Exact manifest of the parent is retained; overwrites are preserved at finalization below.
 counts_md='\n'.join(f'| {k} | {v} |' for k,v in counts.items())
 header=f'''# VAN Next — Rev1.12 reviewed adoption integration\n\n**State:** owner-directed specification integration; independent semantic/F15 admission pending; no application implementation, live deployment or financial authority is claimed.\n\nThe active master is `{MASTER}`; the only execution plan is `plan/DEVELOPMENT_PLAN.json`. Old plans are lineage.\n\n| Scope | Generated count |\n|---|---:|\n{counts_md}\n\n**BG-001:** {units['BG-001']['packet_id']}; **first new UX:** {units['UX-001']['packet_id']}. Unit IDs are stable; sequence-based packet IDs changed and must always be revision-qualified. `traceability/REV111_PACKET_CROSSWALK.json` maps all 121 old units.\n\n'''
 write('README_START_HERE.md',header+'''## Read in this order\n\n1. Master §30 and the retained full product/forecast chapters.\n2. `contracts/HIGH_VALUE_INTEGRATION_CONTRACTS.md`, the source/adoption/review crosswalks and exact producer/consumer contracts.\n3. Generated full plan and test registry, followed by `OPUS_CONTINUATION_HANDOFF.md`.\n\nNew read-only services are BE-037–044; independent verifiers BQ-008/009. Existing 90 forecast requirements, 20 corrective contracts, 77 Opus and 18 backend-first requirements remain intact. Twelve new principal schemas supplement the 18 unchanged forecast schemas. All application tests are NOT_RUN.\n\n## Verification boundary\n\nRun the reproducible document scripts described in `verification/README.md`. Document/schema tests are not tests of VAN, Qlib, a chain provider, calibration accuracy or profitability. Actual source/economic/provider/device validation remains in the plan. Historical receipts moved to `lineage/rev1_11/evidence`. Current receipt files explicitly identify their scope and environment. No F15 or BG certificate is issued.\n''')
 write('contracts/HIGH_VALUE_INTEGRATION_CONTRACTS.md',chapter+'\n\n## Machine contracts and planned acceptance\n\n'+ '\n\n'.join(f"### {r['id']} — {r['title']}\n\n{r['text']}\n\nOwners: {', '.join(r['backend_units']+r['frontend_units']+r['other_units'])}.\n\nPositive: {r['acceptance']['positive']}\n\nAdversarial: {r['acceptance']['adversarial']}\n\nRecovery: {r['acceptance']['recovery']}" for r in reqs['requirements'] if r['id'].startswith('VAN-HVA-'))+'\n')
 # Corrected standalone source-derived companion. It points into the one active programme.
 comp=upload.decode().replace('Revision 1.0','Revision 1.1 — corrected integrated companion',1)
 comp=comp.replace('**RECOMMENDATION / DERIVED IMPLEMENTATION BLUEPRINT — NOT ADOPTED, NOT DEPLOYED**','**OWNER-DIRECTED SCOPE INTEGRATION / INDEPENDENT SEMANTIC ADMISSION PENDING / NOT IMPLEMENTED, NOT DEPLOYED**',1)
 comp=comp.replace('No repository writes, owner-signatures, strategy promotions, venue onboarding or live orders are authorized by this document.','This revision integrates the reviewed requirements into the delivered Unified Rev1.12 specification. It does not itself authorize repository merges, owner-signatures, strategy promotions, venue onboarding or live orders.')
 # Source-quality namespace only (never alter inherited implementation evidence enums).
 comp=re.sub(r'\bE([1-5])\b',r'RS\1',comp)
 comp=comp.replace('**Evidence categories:**','**Research-source categories (RS, never implementation E grades):**')
 comp=comp.replace('confidence-aware ranking only after calibration and authoritatively approved V1 gate','qualified model-weighted ranking only after a separately reviewed policy version; existing AllocatorV1 remains confidence-free')
 comp=comp.replace('the existing calibrated allocator upgrade','the separately reviewed allocator policy version; existing AllocatorV1 does not provide calibrated model-weighted ranking')
 comp=comp.replace('NeuralForecast where justified','full required NeuralForecast engineering; economic use only where justified')
 comp=comp.replace('Prototype in sequence','Implement admitted read-only scope').replace('**Prototype**','**Implement admitted read-only scope**')
 comp=comp.replace('NeuralForecast deep experiments are optional','Required NeuralForecast integrations are mandatory; further deep experiments are evidence- and cost-selected')
 comp=comp.replace('Treat Qlib + LightGBM as the first model-adoption tranche, with NeuralForecast as a conditional challenger.','Preserve all mandatory Qlib/LightGBM/NeuralForecast software and challenger plugins; only economic influence is conditional.')
 comp=comp.replace('| **M8** | Owner UI / analytics | M2 and at least one qualified feed |','| **M8** | Owner UI / analytics | Canonical BG-001 and UX-003 only |')
 comp=comp.replace('## 12. Dependency-ordered delivery programme','## 12. Historical milestone aliases — not an independent delivery schedule')
 comp=comp.replace('## 15. Explicit owner decision requested before implementation','## 15. Superseded narrower staging proposal — corrected by current owner-directed scope')
 start=comp.index('**Proposed adoption decision:**');end=comp.index('**Default recommendation:**',start)
 comp=comp[:start]+('**Operative adoption scope:** the owner directed proceeding with the reviewed recommendations. All existing forecast engineering and read-only A04/A05 domain duties are included in Unified Rev1.12. M0–M9 and G0–G6 are explanatory lineage aliases, not selective waivers or independent approval paths. No wallet, signing, new live venue or increased capital permission is included. PRE-003 independent F15 and BG-001 remain unissued.\n\n')+comp[end:]
 comp=comp.replace('**Training contract:**','**Training contract:**')
 rule=f'''\n> **Operative integration rule:** this is a corrected, source-derived companion to `{MASTER}`. The only active requirements and schedule are the Unified Rev1.12 machine registries. Section 30 of that master and `contracts/HIGH_VALUE_INTEGRATION_CONTRACTS.md` resolve inherited illustrative schema and staging ambiguity. Existing forecast scope cannot be reduced, observed facts must be split from modeled economics, and all new frontend stays after BG-001. The original Rev1.0 text is retained unchanged in lineage.\n'''
 comp=comp.replace('\n---\n',rule+'\n---\n',1)
 comp+='\n\n## 16. Integrated correction and source-reconciliation contract\n\n'+chapter+'\n'
 write('VAN_HIGH_VALUE_TRADING_ADOPTIONS_BLUEPRINT_REV1_1_20261017.md',comp)
 # Update service and screen reading copies by explicit extensions, never removing inherited detail.
 for f in ['contracts/BACKEND_SERVICE_COMPLETION_CONTRACTS.md','contracts/BACKEND_TO_FRONTEND_CONSUMPTION_CONTRACT.md']:
  t=(OUT/f).read_text();write(f,'> Rev1.12: complete inherited contracts retained; new mandatory domain obligations below. The machine catalogue and plan are active.\n\n'+t+'\n\n'+chapter)
 t=(OUT/'design/ALL_SCREEN_TACTILE_SPECIFICATIONS.md').read_text();t+='\n\n# Rev1.12 — Six additional contextual read-only views, after BG-001\n\n'
 for s in surfaces['surfaces'][-6:]:t+=f"## {s['id']}: {s['title']}\n\n{s['first_fold']}\n\n{s['dark_light']}\n\nStates: {', '.join(s['states'])}. Backend owners: {', '.join(s['backend_units'])}. Frontend: FE-023 only after BG-001. Acceptance: {s['test_id']}, NOT_RUN. {s['authority_rule']}\n\n"
 write('design/ALL_SCREEN_TACTILE_SPECIFICATIONS.md',t)
 write('research/FORECAST_READING_RULE.md',(OUT/'research/FORECAST_READING_RULE.md').read_text()+'\n\nRev1.12 preserves all 90 forecast requirements, 48 source-packet meanings and 18 schemas. §30 adds full discovery-cohort, chain-state, sellability and typed-Jev contracts at the shared owners. Generic model development has no crypto-provider dependency; the final domain/BG tests require real integrations where specified. The 66-head review replaces default-branch-only source assumptions, not the full forecasting requirements.\n')
 handoff=header+'''## Exact continuation\n\nRead this complete package, the canonical selector, R01–R12 dispositions, A01–A08 crosswalk, all requirement/service/test/surface registries and source evidence before work. Preserve the actual retained implementations, not branch titles or test-count claims.\n\nThe next programme work is PRE-001/PRE-002 source-and-semantic admission. Refresh refs and compare against the stored 66-head evidence; independently reconcile each shared account-runtime, evidence, Jev, temperament and PR101 correction function. Do not blanket merge. The owner authorized the reviewed scope integration, not a fabricated signature or a passed F15. Application code-bearing source consolidation starts only after genuine PRE-003 exit.\n\nThen use the generated 131-packet plan, not M0–M9 or a historical packet number. All 82 backends and 12 verifiers must close before BG-001. Do not build any new native UI sooner. One valid negative economic result does not excuse absent required model software; inaccessible required source proof is explicit, never fixture-as-live. No new licence, account, wallet, paid feed, custody or trading permission is part of this work.\n\nReproduce and fix limit-price, policy-expiry, pending-order protection, intrabar ambiguity, complete fee/financing debits, post-liquidation equity and whole-account replay using existing correction contracts. Preserve working resting orders, recoverable lockouts and signed modes. Keep one RiskAuthority, account reservation authority, ExecutionRouter, model registry/calibration and shared dial-jev service.\n\nAll new chain operations are read-only. Evaluate exact provider capabilities, source availability, finality, quotas, state-bound sellability, complete discovery cohorts and missing outcomes. Carry out success, refusal, interruption, revocation/reorg and recovery proofs through registered callers and owner-visible readbacks. Report engineering, provider, economic and financial authority separately.\n\nUse Global DIAL on authorized Netcup/Oracle topology; never the physical desktop. Zuul remains CI/admission; GitHub Actions is not a new authority. Keep existing signed gates and owner mandates intact. Do not rewrite application acceptance tests to PASS because the documentary checker passes.\n'''
 write('OPUS_CONTINUATION_HANDOFF.md',handoff)
 write('CONSOLIDATION_REPORT.md',header+chapter)
 t=(OUT/'CONSOLIDATION_APPLY_PROTOCOL.md').read_text();write('CONSOLIDATION_APPLY_PROTOCOL.md','> Rev1.12 controls this delivered candidate; update active filenames from 1_11 to 1_12 when applying the protocol below. No repository write or formal signature has occurred in this delivery. The exact 205 inherited requirement objects and 1185 application test objects are preserved; new scope requires independent semantic review.\n\n'+t.replace('REV1_11','REV1_12').replace('Rev1.11','Rev1.12'))
 write('OWNER_DECISIONS_AND_CONSOLIDATION.md',(OUT/'OWNER_DECISIONS_AND_CONSOLIDATION.md').read_text()+'''\n\n## Rev1.12 owner direction — reviewed adoption integration\n\nCurrent owner instruction: “Proceed according to your recommendations.” Basis: the delivered comparative review R01–R12. This authorizes proceeding with corrected specification integration and the read-only crypto domain scope into the unified programme. It does not settle unrelated OQs, change OD-00–39, mint a signature, accept application tests, issue F15/BG, authorize blanket merges or activate financial operations. Exact machine record: `consolidation/OWNER_SCOPE_DIRECTION_REV1_12.json`.\n''')
 write('contracts/high_value/README.md','''# Rev1.12 proposed high-value application contracts\n\nTwelve strict principal JSON schemas and twelve synthetic examples. These are application interface specifications, not implementations of chain parsing, economic forecasting or VAN services. The executable checker tests schema/selected local semantic counterexamples only. Source/fixture/economic/live evidence remains separate.\n\nBase timestamps bind information available at a decision cutoff. Quotes contain observed-size cash amounts; forecast records carry target/model/calibration identity; NetEdgeAssessment links their arithmetic. Detailed temporal, chain codec, finality, parser, provider, cross-record hash and economic qualification remains in VAN-HVA application test contracts. No fixture is evidence of a provider call.\n\nResearch grades use RS1–RS5 and implementation levels use E0–E6 (or SPEC_ONLY). Neither conveys financial authority. All additive records have trade_authorized=false. Identity- or provider-bound relationships require validated chain adapters and existing source/evidence resolution, not trust in arbitrary strings.\n''')
 write('verification/README.md','''# Document verification versus application qualification\n\nFrom this extracted package run:\n\n```sh\npython verification/verify_unified.py --selftest\npython plan/render_plan.py --check\npython verification/verify_graph_export.py --selftest\npython verification/verify_hva_contracts.py --selftest\npython verification/verify_integration_preservation.py --selftest\npython verification/verify_news_readiness.py --selftest\npython verification/verify_forecast_contracts.py\npython verification/verify_package.py\n```\n\nThe schema checker requires jsonschema. These commands check this specification and synthetic examples, not VAN application source or provider behavior. The preserved application tests are separately planned and NOT_RUN. `assert_readiness.py` must continue to refuse the unissued F15/BG certificates.\n\nExisting tests and source receipts in lineage are historical. Current VM receipts bind only the exact files sent to the isolated VM and their stated tests; they are not a full app test run or signed acceptance. Coordinated tampering with files and unsigned scope locks still requires independent authority/signature review.\n''')
 # Save build sources and target invariants for reproducibility.
 for f in ['hva_spec.py','hva_contracts.py','integration_chapter.md','verify_hva_contracts.py']:
  d=OUT/'tools/integration_sources'/f;d.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(WORK/f,d)
 shutil.copy2(__file__,OUT/'tools/integration_sources/build_integration.py')
 write('consolidation/GENERATED_SCOPE_COUNTS.json',{'revision':REV,'counts':counts,'original_unit_ids_preserved':121,'original_requirement_objects_preserved':205,'original_test_objects_preserved':1185,'new_requirements':32,'new_application_contracts':102,'new_principal_schemas':12,'new_synthetic_examples':12,'BG_packet':units['BG-001']['packet_id'],'first_UX_packet':units['UX-001']['packet_id'],'application_tests_executed':0})
 # Snapshot overwritten/moved parent files; byte-identical originals can be reconstructed without duplicating large unchanged assets.
 (OUT/'plan/VAN_NEXT_DETERMINISTIC_PLAN_REV1_11.md').unlink(missing_ok=True)
 preserved=[]
 for src in sorted(PARENT.rglob('*')):
  if not src.is_file():continue
  rel=src.relative_to(PARENT);dst=OUT/rel
  if not dst.exists() or dst.read_bytes()!=src.read_bytes():
   archive=OUT/'lineage/rev1_11'/rel;archive.parent.mkdir(parents=True,exist_ok=True);archive.write_bytes(src.read_bytes());location=str(archive.relative_to(OUT))
  else:location=str(rel)
  preserved.append({'original_path':str(rel),'preserved_at':location,'sha256':sha(src.read_bytes()),'bytes':src.stat().st_size})
 write('lineage/REV111_PRESERVATION_MANIFEST.json',{'schema':'van.original-byte-preservation/1.0','parent_zip_sha256':sha(PARENT_ZIP.read_bytes()),'parent_zip_bytes':PARENT_ZIP.stat().st_size,'files':preserved,'scope':'Original parent files reconstructable by these exact bytes; not a new signed acceptance.'})
 # The new scope lock is generated after all machine-record changes.
 verifier=loadmod('new_verify',OUT/'verification/verify_unified.py');lock=load('plan/PROPOSED_SCOPE_LOCK.json');lock['records']=verifier.lock_snapshot(verifier.load_bundle(OUT));write('plan/PROPOSED_SCOPE_LOCK.json',lock)
 # scope-lock original was captured earlier, verify inherited manifest points at original for this changed file.
 for rel in ['plan/PROPOSED_SCOPE_LOCK.json','plan/PLAN_INPUT_PROVENANCE.json','MANIFEST.json']:
  a=OUT/'lineage/rev1_11'/rel;a.parent.mkdir(parents=True,exist_ok=True);a.write_bytes((PARENT/rel).read_bytes())
  entry=next(r for r in preserved if r['original_path']==rel);entry['preserved_at']=str(a.relative_to(OUT))
 write('lineage/REV111_PRESERVATION_MANIFEST.json',{'schema':'van.original-byte-preservation/1.0','parent_zip_sha256':sha(PARENT_ZIP.read_bytes()),'parent_zip_bytes':PARENT_ZIP.stat().st_size,'files':preserved,'scope':'Original parent files reconstructable by these exact bytes; not a new signed acceptance.'})
 # Render the actual machine-derived plan and compact graph export.
 subprocess.run([sys.executable,str(OUT/'plan/render_plan.py')],check=True)
 write('evidence/GRAPH_EXPORT.json',{'schema':'van.canonical.graph/1.0','plan_sha256':sha((OUT/'plan/DEVELOPMENT_PLAN.json').read_bytes()),'nodes':[[u['id'],u['kind'],u['stage'],u['dependencies']] for u in plan['units']],'required_backend_ids':backend,'required_backend_verification_ids':bv})
 print(json.dumps({'root':str(OUT),**counts,'BG':units['BG-001']['packet_id'],'UX':units['UX-001']['packet_id']},indent=2))
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--parent-zip',type=pathlib.Path,default=PARENT_ZIP)
 ap.add_argument('--parent-directory',type=pathlib.Path,default=PARENT)
 ap.add_argument('--source-blueprint',type=pathlib.Path,default=SOURCE_BLUEPRINT)
 ap.add_argument('--review-pack',type=pathlib.Path,default=REVIEW_PACK)
 ap.add_argument('--output',type=pathlib.Path,default=OUT)
 a=ap.parse_args();PARENT_ZIP=a.parent_zip;PARENT=a.parent_directory;SOURCE_BLUEPRINT=a.source_blueprint;REVIEW_PACK=a.review_pack;OUT=a.output
 if OUT.resolve()==PARENT.resolve() or PARENT.resolve() in OUT.resolve().parents:
  raise SystemExit('Output must be separate from the immutable parent directory')
 if OUT.exists():
  raise SystemExit('Output already exists; choose a fresh directory. No existing output is overwritten by this CLI.')
 if not PARENT.exists():
  PARENT.mkdir(parents=True)
  with zipfile.ZipFile(PARENT_ZIP) as z:
   for n in z.namelist():
    p=pathlib.PurePosixPath(n)
    if '..' in p.parts or p.is_absolute():raise ValueError('Unsafe parent member')
    rel=pathlib.Path(*p.parts[1:])
    if n.endswith('/') or not rel.parts:continue
    target=PARENT/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(n))
 build()
