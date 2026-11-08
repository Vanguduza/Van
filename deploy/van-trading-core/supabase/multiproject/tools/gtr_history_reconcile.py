#!/usr/bin/env python3
"""Offline GTR migration-history reconciliation. No DB/SSH/network executor.

Produces a bounded READ ONLY capture query and compares supplied metadata. The
hosted connection/identity must be observed independently. Matching versions do
not prove matching SQL, schema, data, cutover readiness or release authority.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import pathlib
import re
import stat
import gtr_migration_plan as migration
import recovery
import render

GTR_COMMIT='8131858c7c7479d178cbe9e246f83cb49ed80f5e'
ACTIVE_PROJECT='bicyjghgdnzlnjqxzoud'
RETIRED_PROJECT='gylrgwqyuiwkyykardwc'
MANIFEST_SHA='e63bbf3ef3f57d6cf4750879e2aceb5b0fdf794d20fcaf562616b8065cd9f3cc'
MANIFEST_PATH='supabase/baseline/manifest.json'
FORMAT='POSTGRESQL_JSONB_STATEMENT_ARRAY_SHA256_V1'
VERSION=re.compile(r'^[0-9]{14}$')  # Opaque migration IDs, not timestamps.
SHA=re.compile(r'^[a-f0-9]{64}$')
NONCE=re.compile(r'^[a-f0-9]{32}$')
MAX_ROWS=10000
MAX_INPUT=8*1024*1024

class ReconcileError(ValueError):pass

def digest(raw):return hashlib.sha256(raw).hexdigest()

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n'

def exact(value,keys):
    if not isinstance(value,dict) or set(value)!=set(keys):raise ReconcileError('EXACT_FIELDS_REQUIRED')

def public_source(root,relative,expected,max_bytes=8*1024*1024):
    """Pin every path component without following symlinks; bound every read."""
    path=pathlib.Path(root)
    if not path.is_absolute() or '..' in path.parts:raise ReconcileError('ABSOLUTE_SOURCE_REQUIRED')
    if not isinstance(relative,str) or not re.fullmatch(r'[A-Za-z0-9_./-]+',relative) or pathlib.PurePosixPath(relative).is_absolute() or any(x in ('','.','..') for x in relative.split('/')):
        raise ReconcileError('SOURCE_PATH_REFUSED')
    if not isinstance(expected,str) or not SHA.fullmatch(expected):raise ReconcileError('SOURCE_SHA256_REQUIRED')
    fd=os.open('/',os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW)
    source=None
    try:
        for component in [*path.parts[1:],*relative.split('/')[:-1]]:
            nxt=os.open(component,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=nxt
        source=os.open(relative.split('/')[-1],os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
        before=os.fstat(source)
        if not stat.S_ISREG(before.st_mode) or before.st_size>max_bytes or before.st_nlink!=1:
            raise ReconcileError('BOUNDED_REGULAR_SOURCE_REQUIRED')
        with os.fdopen(source,'rb') as f:
            source=None;raw=f.read(max_bytes+1);after=os.fstat(f.fileno())
        fields=lambda x:(x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
        if fields(before)!=fields(after) or len(raw)!=before.st_size or digest(raw)!=expected:
            raise ReconcileError('SOURCE_IDENTITY_CHANGED')
        return raw
    finally:
        if source is not None:os.close(source)
        os.close(fd)

def source_catalog(source_root):
    manifest=json.loads(public_source(source_root,MANIFEST_PATH,MANIFEST_SHA),object_pairs_hook=render.unique_object)
    lock=migration.load_lock()
    if lock['commit']!=GTR_COMMIT:raise ReconcileError('PINNED_GTR_SOURCE_REQUIRED')
    entries={};groups={}
    for family,rows in (('legacy',manifest['legacy_history']),('hosted_archive',manifest['hosted_history']),('active',lock['files'])):
        if not isinstance(rows,list):raise ReconcileError('HISTORY_LIST_REQUIRED')
        group=[];versions=set()
        for row in rows:
            path=row['path'];name=pathlib.PurePosixPath(path).name
            match=re.fullmatch(r'([0-9]{14})_([a-z0-9_]+)\.sql',name)
            prefix={'legacy':'supabase/migration-history/legacy/','hosted_archive':'supabase/live-history/','active':'supabase/migrations/'}[family]
            if not match or path!=prefix+name or match[1] in versions or path in entries:
                raise ReconcileError('HISTORY_PATH_OR_VERSION_DUPLICATE')
            raw=public_source(source_root,path,row['sha256'])
            if family=='active' and len(raw)!=row['bytes']:raise ReconcileError('ACTIVE_SOURCE_LENGTH_CHANGED')
            record={'path':path,'version':match[1],'name':match[2],'source_file_sha256':row['sha256'],'bytes':len(raw),'family':family}
            entries[path]=record;group.append(record);versions.add(match[1])
        groups[family]=sorted(group,key=lambda x:x['version'])
    if [len(groups[x]) for x in ('legacy','hosted_archive','active')]!=[173,125,13]:
        raise ReconcileError('PINNED_HISTORY_COUNTS_CHANGED')
    for entry in manifest['sources']:
        if entry['path'] not in entries or entries[entry['path']]['source_file_sha256']!=entry['sha256']:
            raise ReconcileError('CURATED_SOURCE_BINDING_CHANGED')
    contract=public_source(source_root,manifest['source_contract_file'],manifest['source_contract_sha256'])
    if manifest['baseline_target']!=groups['active'][0]['version'] or manifest['baseline_sha256']!=groups['active'][0]['source_file_sha256']:
        raise ReconcileError('BASELINE_BINDING_CHANGED')
    families={}
    for row in entries.values():families.setdefault(row['version'],[]).append(row['family'])
    return {'schema_version':1,'kind':'GTR_PINNED_SOURCE_HISTORY_CATALOG_NOT_HOSTED_OBSERVATION',
        'repository':'Vanguduza/Nissan-Gtr-Auto','commit':GTR_COMMIT,
        'manifest_sha256':MANIFEST_SHA,'baseline_version':manifest['baseline_target'],
        'source_contract_sha256':digest(contract),'curated_source_count':len(manifest['sources']),
        'histories':groups,'cross_family_version_overlap':sorted(v for v,f in families.items() if len(f)>1),
        'cross_family_content_variants':{v:sorted({r['source_file_sha256'] for r in entries.values() if r['version']==v}) for v,f in families.items() if len(f)>1},
        'current_hosted_state_observed':False,'history_repair_authorized':False}

def capture_sql(nonce):
    if not isinstance(nonce,str) or not NONCE.fullmatch(nonce):raise ReconcileError('EXACT_CAPTURE_NONCE_REQUIRED')
    # No connection URL or credential supplied. Caller must independently verify
    # the active project's authenticated connection and retain its receipt.
    return f"""-- READ ONLY metadata capture. Run with psql -X -qAt -v ON_ERROR_STOP=1.
-- The declared project ref is an ASSERTION, not observed connection identity.
-- One transaction and one result: no SQL statements, rows or secrets returned.
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='10s';
SET LOCAL lock_timeout='2s';
SET LOCAL idle_in_transaction_session_timeout='15s';
SET LOCAL search_path=pg_catalog;
-- Hold a non-exclusive schema-stability lock while proving this is the
-- ordinary ledger table, not a view/foreign table or row-filtered relation.
LOCK TABLE ONLY supabase_migrations.schema_migrations IN ACCESS SHARE MODE;
DO $ledger_guard$ DECLARE target oid := 'supabase_migrations.schema_migrations'::regclass;
BEGIN
  IF NOT EXISTS (SELECT FROM pg_class WHERE oid=target AND relkind='r'
                 AND NOT relrowsecurity AND NOT relforcerowsecurity)
     OR (SELECT count(*) FROM pg_attribute WHERE attrelid=target AND NOT attisdropped
         AND ((attname IN ('version','name') AND atttypid='text'::regtype)
           OR (attname='statements' AND atttypid='text[]'::regtype)))<>3
  THEN RAISE EXCEPTION 'LEDGER_BASE_TABLE_WITHOUT_RLS_AND_TYPED_COLUMNS_REQUIRED'; END IF;
END $ledger_guard$;
WITH ledger AS MATERIALIZED (
  SELECT version,name,statements FROM supabase_migrations.schema_migrations
  ORDER BY version COLLATE "C" LIMIT {MAX_ROWS+1}
), observed AS (
  SELECT version,name,
    CASE WHEN statements IS NULL THEN NULL ELSE cardinality(statements) END AS statement_count,
    CASE WHEN statements IS NULL THEN NULL ELSE encode(sha256(convert_to(to_jsonb(statements)::text,'UTF8')),'hex') END AS statements_sha256
  FROM ledger
)
SELECT jsonb_build_object(
  'schema_version',1,'kind','GTR_READ_ONLY_LEDGER_SNAPSHOT_V1',
  'capture_nonce','{nonce}','declared_project_ref','{ACTIVE_PROJECT}',
  'captured_at',transaction_timestamp(),'server_version_num',current_setting('server_version_num')::integer,
  'database_name',current_database(),'sql_role',current_user,
  'read_only',current_setting('transaction_read_only')='on',
  'isolation',current_setting('transaction_isolation'),
  'fingerprint_format','{FORMAT}',
  'row_count',(SELECT count(*) FROM observed),
  'truncated',(SELECT count(*)>{MAX_ROWS} FROM observed),
  'rows',COALESCE((SELECT jsonb_agg(jsonb_build_object('version',version,'name',name,
     'statement_count',statement_count,'statements_sha256',statements_sha256) ORDER BY version COLLATE "C") FROM observed),'[]'::jsonb));
ROLLBACK;
"""

def timestamp(value):
    if not isinstance(value,str) or len(value)>64:raise ReconcileError('UTC_CAPTURE_TIME_REQUIRED')
    try:d=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError:raise ReconcileError('UTC_CAPTURE_TIME_REQUIRED') from None
    if d.tzinfo is None:raise ReconcileError('UTC_CAPTURE_TIME_REQUIRED')
    return d.astimezone(timezone.utc)

def validate_snapshot(snapshot,nonce):
    fields=('schema_version','kind','capture_nonce','declared_project_ref','captured_at',
       'server_version_num','database_name','sql_role','read_only','isolation','fingerprint_format','row_count','truncated','rows')
    exact(snapshot,fields)
    if type(snapshot['schema_version']) is not int or snapshot['schema_version']!=1 or snapshot['kind']!='GTR_READ_ONLY_LEDGER_SNAPSHOT_V1':raise ReconcileError('LEDGER_SNAPSHOT_KIND_INVALID')
    if not isinstance(nonce,str) or not NONCE.fullmatch(nonce) or snapshot['capture_nonce']!=nonce:raise ReconcileError('CAPTURE_CORRELATION_MISMATCH')
    if snapshot['declared_project_ref']!=ACTIVE_PROJECT:raise ReconcileError('ACTIVE_PROJECT_ASSERTION_REQUIRED')
    if snapshot['read_only'] is not True or snapshot['isolation']!='repeatable read':raise ReconcileError('READ_ONLY_REPEATABLE_CAPTURE_REQUIRED')
    if snapshot['truncated'] is not False:raise ReconcileError('TRUNCATED_LEDGER_REFUSED')
    if snapshot['fingerprint_format']!=FORMAT:raise ReconcileError('INCOMPARABLE_STATEMENT_HASH_FORMAT')
    if type(snapshot['server_version_num']) is not int or not 150000<=snapshot['server_version_num']<190000:raise ReconcileError('SERVER_VERSION_UNSUPPORTED')
    for key in ('database_name','sql_role'):
        if not isinstance(snapshot[key],str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]{0,127}',snapshot[key]):raise ReconcileError('DATABASE_METADATA_INVALID')
    timestamp(snapshot['captured_at'])
    rows=snapshot['rows']
    if not isinstance(rows,list) or len(rows)>MAX_ROWS or type(snapshot['row_count']) is not int or snapshot['row_count']!=len(rows):raise ReconcileError('LEDGER_COUNT_MISMATCH')
    seen=set()
    for row in rows:
        exact(row,('version','name','statement_count','statements_sha256'))
        if not isinstance(row['version'],str) or not VERSION.fullmatch(row['version']) or row['version'] in seen:raise ReconcileError('INVALID_OR_DUPLICATE_LEDGER_VERSION')
        seen.add(row['version'])
        name=row['name']
        if name is not None and (not isinstance(name,str) or len(name)>256 or any(ord(c)<32 for c in name)):raise ReconcileError('LEDGER_NAME_INVALID')
        count=row['statement_count'];h=row['statements_sha256']
        if count is None and h is None:continue
        if type(count) is not int or not 0<=count<=100000 or not isinstance(h,str) or not SHA.fullmatch(h):raise ReconcileError('LEDGER_STATEMENT_METADATA_INVALID')
    return {r['version']:dict(r) for r in rows}

def compare(catalog,snapshot,*,nonce,now,previous=None):
    # Only source_catalog() results may be used by the public CLI. This pure
    # comparison API is intentionally independent of network/DB execution.
    if catalog.get('kind')!='GTR_PINNED_SOURCE_HISTORY_CATALOG_NOT_HOSTED_OBSERVATION' or catalog.get('commit')!=GTR_COMMIT or catalog.get('manifest_sha256')!=MANIFEST_SHA:raise ReconcileError('PINNED_SOURCE_CATALOG_REQUIRED')
    current=validate_snapshot(snapshot,nonce)
    if not isinstance(now,datetime) or now.tzinfo is None:raise ReconcileError('EXPLICIT_EVALUATION_TIME_REQUIRED')
    age=(now.astimezone(timezone.utc)-timestamp(snapshot['captured_at'])).total_seconds()
    history={}
    for family,rows in catalog['histories'].items():
        for row in rows:history.setdefault(row['version'],[]).append(row)
    details=[];unknown=[];name_drift=[];unhashed=[];ambiguous=[]
    for version,row in sorted(current.items()):
        matches=history.get(version,[])
        families=sorted(x['family'] for x in matches)
        if not matches:unknown.append(version)
        variants=len({x['source_file_sha256'] for x in matches})
        if variants>1:ambiguous.append(version)
        mismatch=bool(matches) and row['name'] not in (None,'') and row['name'] not in {m['name'] for m in matches}
        if mismatch:name_drift.append(version)
        if row['statement_count'] is None:unhashed.append(version)
        details.append({'version':version,'source_families':families,'classification':'KNOWN_VERSION_CONTENT_UNVERIFIED' if matches else 'UNKNOWN_VERSION_REQUIRES_REVIEW',
            'source_name_mismatch':mismatch,'source_file_content_variants':variants,'statement_fingerprint_present':row['statement_count'] is not None})
    active={x['version'] for x in catalog['histories']['active']}
    archived={x['version'] for x in catalog['histories']['hosted_archive']}
    added=[];removed=[];changed=[];same=[];incomparable=[]
    if previous is not None:
        before=validate_snapshot(previous,previous['capture_nonce'])
        if previous['database_name']!=snapshot['database_name'] or previous['server_version_num']!=snapshot['server_version_num']:
            raise ReconcileError('PREVIOUS_CAPTURE_CONTEXT_CHANGED_REVIEW_REQUIRED')
        if timestamp(previous['captured_at'])>=timestamp(snapshot['captured_at']):raise ReconcileError('PREVIOUS_CAPTURE_NOT_EARLIER')
        added=sorted(set(current)-set(before));removed=sorted(set(before)-set(current))
        for version in sorted(set(current)&set(before)):
            a=before[version];z=current[version]
            if a['statement_count'] is None or z['statement_count'] is None:incomparable.append(version)
            elif a!=z:changed.append(version)
            else:same.append(version)
    baseline=catalog['baseline_version']
    mode=('EMPTY_LEDGER_REQUIRES_INVENTORY' if not current else
          'BASELINE_MARKER_RECORDED_NOT_SCHEMA_PROOF' if baseline in current else
          'HISTORICAL_OR_OTHER_LEDGER_DO_NOT_REPLAY_BASELINE')
    blockers=['AUTHENTICATED_PROJECT_CONNECTION_NOT_ATTESTED_BY_THIS_TOOL',
              'LEDGER_MATCH_IS_NOT_SCHEMA_OR_DATA_EQUIVALENCE','SOURCE_SQL_FILE_HASH_IS_NOT_LEDGER_STATEMENT_ARRAY_HASH',
              'LIVE_CANARY_AND_RELEASE_AUTHORIZATION_REMAIN_SEPARATE']
    if age<0: blockers.append('CAPTURE_TIME_IS_IN_THE_FUTURE')
    if age>3600: blockers.append('CAPTURE_OLDER_THAN_ONE_HOUR')
    if unknown:blockers.append('UNRECOGNIZED_MIGRATION_VERSIONS')
    if ambiguous:blockers.append('SAME_VERSION_HAS_DISTINCT_SOURCE_BYTES_SEMANTICS_UNPROVEN')
    if name_drift:blockers.append('VERSION_NAME_DRIFT')
    if unhashed:blockers.append('MISSING_STATEMENT_FINGERPRINTS')
    if removed or changed:blockers.append('PREVIOUS_LEDGER_REMOVED_OR_CHANGED')
    return {'schema_version':1,'kind':'GTR_LEDGER_RECONCILIATION_NOT_RELEASE_AUTHORIZATION',
        'source_commit':GTR_COMMIT,'snapshot_sha256':digest(canonical(snapshot).encode()),
        'capture_age_seconds':age,'ledger_mode':mode,'supplied_row_count':len(current),
        'classified_versions':details,'unknown_versions':unknown,'source_name_drift':name_drift,'source_content_ambiguous_versions':ambiguous,
        'active_versions_not_recorded':sorted(active-set(current)),
        'archived_hosted_versions_not_recorded':sorted(archived-set(current)),
        'previous_capture_diff':{'provided':previous is not None,'added':added,'removed':removed,'changed':changed,'same':same,'incomparable':incomparable},
        'blockers':blockers,'current_hosted_state_independently_verified':False,
        'may_apply_baseline':False,'may_repair_history':False,'may_cutover':False,
        'production_changes':False}

def compile_review(source_root,nonce,snapshot=None,previous=None,now=None):
    catalog=source_catalog(source_root)
    artifacts={'source-history-catalog.json':canonical(catalog),'capture-ledger.read-only.sql':capture_sql(nonce)}
    if snapshot is not None:
        artifacts['ledger-review.json']=canonical(compare(catalog,snapshot,nonce=nonce,now=now or datetime.now(timezone.utc),previous=previous))
    artifacts['history-review-receipt.json']=canonical({'kind':'OFFLINE_HISTORY_REVIEW_FILES_NOT_EXECUTED',
        'source_commit':GTR_COMMIT,'capture_nonce':nonce,'files':{n:digest(s.encode()) for n,s in artifacts.items()},
        'hosted_connection_established':False,'history_repair_authorized':False,'production_deployed':False})
    return artifacts

def load_snapshot_file(path):
    # Reuse the established owner-only, no-symlink, single-link file boundary,
    # but ledger exports have a larger explicit bound than credential JSON.
    with recovery.private_directory(path.parent) as directory:
        fd=recovery.open_private_file(directory,path.name)
        try:
            before=os.fstat(fd)
            if before.st_size>MAX_INPUT:raise ReconcileError('LEDGER_INPUT_TOO_LARGE')
            parts=[];size=0
            while True:
                chunk=os.read(fd,min(65536,MAX_INPUT+1-size))
                if not chunk:break
                size+=len(chunk);parts.append(chunk)
                if size>MAX_INPUT:raise ReconcileError('LEDGER_INPUT_TOO_LARGE')
            after=os.fstat(fd)
            identity=lambda x:(x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
            if identity(before)!=identity(after) or size!=before.st_size:raise ReconcileError('LEDGER_INPUT_CHANGED')
            def invalid_constant(value):raise ReconcileError('NONFINITE_JSON_REFUSED')
            return json.loads(b''.join(parts),object_pairs_hook=render.unique_object,parse_constant=invalid_constant)
        finally:os.close(fd)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=pathlib.Path,required=True)
    parser.add_argument('--capture-nonce',required=True)
    parser.add_argument('--snapshot',type=pathlib.Path)
    parser.add_argument('--previous',type=pathlib.Path)
    parser.add_argument('--out',type=pathlib.Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.previous and not args.snapshot:raise ReconcileError('CURRENT_SNAPSHOT_REQUIRED')
        snapshot=load_snapshot_file(args.snapshot) if args.snapshot else None
        previous=load_snapshot_file(args.previous) if args.previous else None
        artifacts=compile_review(args.source_root,args.capture_nonce,snapshot,previous)
        render.write_bundle(args.out,artifacts)
        print('OFFLINE_HISTORY_REVIEW_CREATED__NO_HOSTED_QUERY_OR_MUTATION')
        return 0
    except (ValueError,KeyError,TypeError,OSError):
        print('REFUSED_HISTORY_REVIEW')
        return 2

if __name__=='__main__':raise SystemExit(main())
