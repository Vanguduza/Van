#!/usr/bin/env python3
"""Validate proposed news arming contract metadata, never runtime proof truth."""
from pathlib import Path
import json,copy,argparse,sys
EXPECTED_ARM={'grant_signature_valid','arming_window_open','account_mandate_current','policy_revisions_current','required_sources_healthy','unused_nonce'}
EXPECTED_USE={'two_source_agreement','mandate_and_risk_gate','unused_nonce'}
EXPECTED_EDGES={('DRAFT_UNAPPROVED','SIGNED'),('DRAFT_UNAPPROVED','VOIDED'),('SIGNED','ARMED'),('SIGNED','VOIDED'),('SIGNED','EXPIRED'),('ARMED','USED'),('ARMED','VOIDED'),('ARMED','EXPIRED')}
def check(x):
 e=[];m=x['machine'];edges=[(t['from'],t['to']) for t in m['transitions']]
 if len(edges)!=len(set(edges)):e.append('DUPLICATE_TRANSITION')
 if set(edges)!=EXPECTED_EDGES:e.append('UNAPPROVED_EDGE')
 if len(m['states'])!=len(set(m['states'])):e.append('DUPLICATE_STATE')
 if set(m['states'])!={'DRAFT_UNAPPROVED','SIGNED','ARMED','USED','EXPIRED','VOIDED'}:e.append('STATE_SCOPE_CHANGED')
 if m['initial']!='DRAFT_UNAPPROVED':e.append('INITIAL_BYPASS')
 if set(x['approved_arming_proofs'])!=EXPECTED_ARM:e.append('ARM_PROOFS_CHANGED')
 if set(x['use_requires'])!=EXPECTED_USE:e.append('USE_PROOFS_CHANGED')
 if set(x['added_arming_proof_types'])!=EXPECTED_ARM:e.append('UNTYPED_PROOF')
 for name,proof in x['added_arming_proof_types'].items():
  if not proof.get('issuer') or not proof.get('fields') or not proof.get('failures'):e.append('INCOMPLETE_PROOF_TYPE')
 for t in m['transitions']:
  proof=set(t.get('requires','').split('+'))-{''}
  if (t['from'],t['to'])==('SIGNED','ARMED') and proof!=EXPECTED_ARM:e.append('ARM_GUARD_MISMATCH')
  if (t['from'],t['to'])==('ARMED','USED') and proof!=EXPECTED_USE:e.append('USE_GUARD_MISMATCH')
  if (t['from'],t['to'])==('DRAFT_UNAPPROVED','SIGNED') and proof!={'owner_biometric_over_frozen_grant'}:e.append('SIGNATURE_BYPASS')
 if x.get('no_future_actual_required_to_arm') is not True:e.append('FUTURE_RELEASE_REQUIRED_TO_ARM')
 if 'ARMED' not in m['receipt_states']:e.append('ARMING_NOT_RECORDED')
 if x['status']!='PROPOSED_PENDING_OWNER_LOCK_AND_INDEPENDENT_ADMISSION':e.append('FALSE_AUTHORITY_STATE')
 return sorted(set(e))
def selftest(x):
 def arm(d):return next(t for t in d['machine']['transitions'] if t['from']=='SIGNED' and t['to']=='ARMED')
 def use(d):return next(t for t in d['machine']['transitions'] if t['from']=='ARMED' and t['to']=='USED')
 cases=[('remove arm guard',lambda d:arm(d).pop('requires'),'ARM_GUARD_MISMATCH'),('valid but insufficient proof',lambda d:arm(d).update(requires='unused_nonce'),'ARM_GUARD_MISMATCH'),('draft shortcut',lambda d:d['machine']['transitions'].append({'from':'DRAFT_UNAPPROVED','to':'USED','requires':'two_source_agreement+mandate_and_risk_gate+unused_nonce'}),'UNAPPROVED_EDGE'),('signed shortcut',lambda d:d['machine']['transitions'].append({'from':'SIGNED','to':'USED','requires':'unused_nonce'}),'UNAPPROVED_EDGE'),('single source use',lambda d:use(d).update(requires='mandate_and_risk_gate+unused_nonce'),'USE_GUARD_MISMATCH'),('repin insufficient arming list',lambda d:d.update(approved_arming_proofs=['unused_nonce']),'ARM_PROOFS_CHANGED'),('duplicate transition',lambda d:d['machine']['transitions'].append(copy.deepcopy(arm(d))),'DUPLICATE_TRANSITION'),('no typed issuer',lambda d:d['added_arming_proof_types']['grant_signature_valid'].update(issuer=None),'INCOMPLETE_PROOF_TYPE'),('future actual needed before arm',lambda d:d.update(no_future_actual_required_to_arm=False),'FUTURE_RELEASE_REQUIRED_TO_ARM'),('no arming receipt',lambda d:d['machine']['receipt_states'].remove('ARMED'),'ARMING_NOT_RECORDED'),('initial already armed',lambda d:d['machine'].update(initial='ARMED'),'INITIAL_BYPASS'),('fake owner accepted',lambda d:d.update(status='OWNER_ACCEPTED'),'FALSE_AUTHORITY_STATE')]
 rows=[]
 for name,fn,expected in cases:
  d=copy.deepcopy(x);fn(d);e=check(d);rows.append({'case':name,'caught':expected in e,'expected':expected,'findings':e})
 return {'cases':len(rows),'caught':sum(t['caught'] for t in rows),'results':rows,'scope':'Proposed schema/transition readiness metadata only; does not validate actual signatures, source health or broker effects.'}
def main():
 p=argparse.ArgumentParser();p.add_argument('--selftest',action='store_true');args=p.parse_args();x=json.loads((Path(__file__).resolve().parents[1]/'contracts/NEWS_ARMING_READINESS_AMENDMENT_REV1_10.json').read_text());r=selftest(x) if args.selftest else {'findings':check(x),'status':'PROPOSED_NOT_ISSUED'};print(json.dumps(r,indent=2));return 0 if (r['caught']==r['cases'] if args.selftest else not r['findings']) else 1
if __name__=='__main__':sys.exit(main())
