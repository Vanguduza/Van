"""Account-incarnation deletion DATA in the existing native registry writer.

No permission issuer, strategy promotion/reassignment or financial history.
Detachment is deliberately irreversible here: BE009 has no qualified explicit
account reassignment producer. Alias reuse/cancel/relink cannot clear it.
"""
import copy
import re
from vati.core.canonical import canonical_hash

PHASES={'DELETING','PENDING_ARCHIVE','RELINK_REQUIRED','ARCHIVED'}
FIELDS={'schema','alias','operation_id','device_id','account_control_domain','incarnation',
        'revision','phase','created_at_unix','archive_at_unix','grace_seconds','restore',
        'strategies','session_sources','history_ref','credential_disposition','unlink_ref',
        'oauth_discard_ref','detached','link_intent','remote_account_closed','original_request'}

def validate_records(value):
    if not isinstance(value,dict):raise ValueError('Lifecycle records unreadable; HOLD')
    for alias,row in value.items():
        if (not isinstance(alias,str) or not re.fullmatch(r'[a-z0-9_]{3,32}',alias)
            or not isinstance(row,dict) or set(row)!=FIELDS or row['alias']!=alias
            or row['schema']!='vati.account-lifecycle/1' or row['phase'] not in PHASES
            or row['detached'] is not True or row['link_intent']!='RELINK_REQUIRED'
            or row['remote_account_closed'] is not False
            or any(type(row[k]) is not int or row[k]<=0 for k in ('revision','created_at_unix','archive_at_unix','grace_seconds'))
            or row['archive_at_unix']!=row['created_at_unix']+row['grace_seconds']
            or not isinstance(row['strategies'],list) or any(not isinstance(x,str) for x in row['strategies'])
            or len(set(row['strategies']))!=len(row['strategies'])
            or not isinstance(row['original_request'],dict)
            or row['original_request'].get('variant')!='DELETE_GRACE'
            or row['original_request'].get('alias')!=alias
            or row['original_request'].get('grace_seconds')!=row['grace_seconds']
            or set(row['original_request'])-{'alias','variant','grace_seconds','oauth_discard_digest','reauth_fact_id','reauth_fact_digest'}
            or not isinstance(row['session_sources'],list)
            or not isinstance(row['restore'],(dict,type(None)))
            or row['phase']=='ARCHIVED' and row['restore'] is not None):raise ValueError('Lifecycle evidence invalid; HOLD')
        for k in ('incarnation','account_control_domain','history_ref','oauth_discard_ref'):
            if not isinstance(row[k],str) or not re.fullmatch('[0-9a-f]{64}',row[k]):raise ValueError('Lifecycle binding invalid; HOLD')
        for k in ('operation_id','device_id'):
            if not isinstance(row[k],str) or not row[k]:raise ValueError('Lifecycle original identity missing; HOLD')
    return copy.deepcopy(value)

def require_attached(registry,alias):
    if alias in registry._lifecycles:
        from vati.accounts.registry import AccountRegistryError
        raise AccountRegistryError('Account incarnation is detached; cancellation/relink is not strategy reassignment')

def public_record(row):
    """No restore payload, native paths, credentials, notes or financial values."""
    keys=('schema','alias','operation_id','device_id','account_control_domain','incarnation',
          'revision','phase','created_at_unix','archive_at_unix','grace_seconds','strategies',
          'history_ref','credential_disposition','detached','link_intent','remote_account_closed')
    body={k:copy.deepcopy(row[k]) for k in keys}
    body['record_digest']=canonical_hash(row)
    body['financial_history_retained']=True
    body['execution_authority']=False
    return body
