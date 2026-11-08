#!/usr/bin/env python3
"""Fail-closed, offline schema-compatibility comparison for Nissan GTR.

Inputs are metadata-only identity snapshots. This module contains no SQL,
SSH, Docker, network, migration runner or deploy functionality. Even exact
schema matches do not authorize a canary, history repair or cutover.
"""
from __future__ import annotations
import hashlib
import json
import re

GROUP_FIELDS={
    'tables':4,
    'views':4,
    'functions':7,
    'policies':8,
    'relation_grants':11,
}
KEY_PREFIX={
    'tables':2,
    'views':2,
    'functions':3,
    'policies':3,
    'relation_grants':3,
}
BOUNDED={
    'tables':5000,'views':1000,'functions':5000,
    'policies':5000,'relation_grants':50000,
}
REQUIRED=set(GROUP_FIELDS)|{'private_usage'}
SHA256=re.compile(r'^[0-9a-f]{64}$')
MD5=re.compile(r'^[0-9a-f]{32}$')
SCHEMA_VERSION=1
KIND='GTR_OFFLINE_SCHEMA_COMPATIBILITY_REVIEW_V1'

class SchemaReviewError(ValueError):
    pass

def _string(x):
    return isinstance(x,str) and 0<len(x)<=8192 and '\x00' not in x

def _bools(row,indices):
    return all(type(row[i]) is bool for i in indices)

def _sha(x,kind):
    return isinstance(x,str) and bool((SHA256 if kind=='sha256' else MD5).fullmatch(x))

def validate(metadata):
    """Reject payloads that could hide raw SQL, duplicated identities or missing scopes."""
    if not isinstance(metadata,dict) or set(metadata)!=REQUIRED:
        raise SchemaReviewError('EXACT_METADATA_SCOPE_REQUIRED')
    if not isinstance(metadata['private_usage'],list) or len(metadata['private_usage'])!=3 or not all(type(x) is bool for x in metadata['private_usage']):
        raise SchemaReviewError('PRIVATE_SCHEMA_USAGE_VECTOR_REQUIRED')
    for group,fields in GROUP_FIELDS.items():
        rows=metadata[group]
        if not isinstance(rows,list) or not rows or len(rows)>BOUNDED[group]:
            raise SchemaReviewError('METADATA_COUNT_INVALID_'+group)
        seen=set()
        previous=None
        for row in rows:
            if not isinstance(row,list) or len(row)!=fields:
                raise SchemaReviewError('EXACT_ROW_FIELDS_REQUIRED_'+group)
            n=KEY_PREFIX[group]
            valid_ident=all(_string(v) for v in row[:n])
            # Zero-argument PostgreSQL functions have a VALID empty identity signature.
            if group=='functions':
                valid_ident=(all(_string(v) for v in row[:2])
                    and isinstance(row[2],str) and len(row[2])<=8192
                    and '\x00' not in row[2])
            if not valid_ident:
                raise SchemaReviewError('OBJECT_IDENTITY_REQUIRED_'+group)
            ident=tuple(row[:n])
            if ident in seen:raise SchemaReviewError('DUPLICATE_IDENTITY_'+group)
            if previous is not None and ident<=previous:
                raise SchemaReviewError('UNSORTED_IDENTITIES_'+group)
            seen.add(ident);previous=ident
            if group=='tables':
                if not _bools(row,[2]) or row[3] not in ('p','u','t'):
                    raise SchemaReviewError('INVALID_TABLE_FIELDS')
            elif group=='views':
                if row[2] is not None and not _sha(row[2],'sha256'):
                    raise SchemaReviewError('VIEW_FINGERPRINT_REQUIRED')
                if row[3] is not None and (not isinstance(row[3],list) or not all(_string(s) for s in row[3])):
                    raise SchemaReviewError('VIEW_OPTIONS_REQUIRED')
            elif group=='functions':
                if not _sha(row[3],'md5') or not _bools(row,[4,5,6]):
                    raise SchemaReviewError('FUNCTION_IDENTITY_OR_ACCESS_INVALID')
            elif group=='policies':
                if row[3] not in ('PERMISSIVE','RESTRICTIVE') or not isinstance(row[4],list) or not all(_string(s) for s in row[4]) or not _string(row[5]):
                    raise SchemaReviewError('POLICY_METADATA_REQUIRED')
                if not all(x is None or _sha(x,'sha256') for x in row[6:8]):
                    raise SchemaReviewError('POLICY_PREDICATE_FINGERPRINT_REQUIRED')
            elif group=='relation_grants':
                if row[2] not in ('anon','authenticated','service_role') or not _bools(row,range(3,11)):
                    raise SchemaReviewError('GRANT_BITMAP_REQUIRED')
    return metadata

def _digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def compare(hosted,postforward):
    """Return non-secret identity and change counts; NEVER authorize a release."""
    validate(hosted);validate(postforward)
    differences={}
    blockers=[]
    for group in GROUP_FIELDS:
        n=KEY_PREFIX[group]
        h={tuple(row[:n]):row for row in hosted[group]}
        f={tuple(row[:n]):row for row in postforward[group]}
        added=sorted(set(f)-set(h))
        missing=sorted(set(h)-set(f))
        common=sorted(set(h)&set(f))
        changed=[ident for ident in common if h[ident]!=f[ident]]
        result={'hosted_count':len(h),'postforward_count':len(f),'shared_count':len(common),
            'identical_count':len(common)-len(changed),
            'new_in_postforward':len(added),'missing_from_postforward':len(missing),
            'changed_shared':len(changed),
            'hosted_metadata_digest':_digest(hosted[group]),
            'postforward_metadata_digest':_digest(postforward[group]),
            'added_identities':[list(x) for x in added],
            'missing_identities':[list(x) for x in missing],
            'modified_identities':[list(x) for x in changed]}
        if group=='functions':
            result['definition_hash_changes']=sum(h[x][3]!=f[x][3] for x in changed)
            result['execute_grant_changes']=sum(h[x][4:]!=f[x][4:] for x in changed)
            result['execute_grant_direction']={}
            for i,role in ((4,'anon'),(5,'authenticated'),(6,'service_role')):
                result['execute_grant_direction'][role]={
                    'lost':sum(h[x][i] and not f[x][i] for x in common),
                    'gained':sum(not h[x][i] and f[x][i] for x in common)}
        elif group=='policies':
            result['predicate_changes']=sum(h[x][6:]!=f[x][6:] for x in changed)
            result['role_or_command_changes']=sum(h[x][3:6]!=f[x][3:6] for x in changed)
        elif group=='relation_grants':
            result['changed_permission_bits']=sum(h[x][i]!=f[x][i] for x in common for i in range(3,11))
            result['lost_effective_privileges']=sum(h[x][i] and not f[x][i] for x in common for i in range(3,11))
            result['gained_effective_privileges']=sum(not h[x][i] and f[x][i] for x in common for i in range(3,11))
        differences[group]=result
        if added or missing or changed:
            blockers.append('SCHEMA_SCOPE_DIFFERENCE_'+group.upper())
    private_equal=hosted['private_usage']==postforward['private_usage']
    if not private_equal:blockers.append('PRIVATE_SCHEMA_USAGE_DIFFERENCE')
    return {
        'schema_version':SCHEMA_VERSION,'kind':KIND,
        'scope':'METADATA_ONLY_HOSTED_VS_NETWORK_ISOLATED_POSTFORWARD',
        'groups':differences,
        'private_usage_equal':private_equal,
        'metadata_identity_and_fingerprint_equal':not blockers,
        'blockers':blockers,
        'production_deployment_authorized':False,
        'migration_history_repair_authorized':False,
        'canary_activation_authorized':False,
        'nissan_gtr_cutover_authorized':False,
        'hosted_database_modified':False,
        'sql_or_customer_rows_returned':False,
        'critical_limits':[
            'Input authenticity, project identity and exact PostgreSQL source versions require independent custody.',
            'Function-body hashes detect textual drift, not proof of semantic incompatibility.',
            'Even exact metadata matches do not prove row data, Auth, Storage/R2, payments, cron or Edge parity.',
            'Do not change ACLs, policies, source data, production services or activation based solely on this result.',
            'The original safety-refused canary operation remains blocked.'
        ]
    }
