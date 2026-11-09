#!/usr/bin/env python3
"""Private logical backup capture and non-deploying fresh-database restore plans.

Only capture contacts the explicitly configured database (read-only). No command
here restores, drops, renames, restarts or switches a database. The caller must
retain the manifest digest independently: hashes are integrity, not authority.
Backups contain sensitive Auth data and are NOT encrypted by this module.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import fcntl
import json
import os
import pathlib
import re
import selectors
import signal
import stat
import subprocess
import time
import uuid
import bootstrap as b
import render

class RecoveryError(ValueError): pass

MAX_VERIFIED_ARCHIVE_BYTES=256*1024*1024  # Bounded immutable in-memory readback; larger archives require native custody.
SHA=re.compile(r'^[a-f0-9]{64}$')
SNAPSHOT=re.compile(r'^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{8}-[0-9A-Fa-f]+$')
CAPTURE_KEYS={'schema_version','kind','backup_id','created_at','source_revision','project',
              'observation','archive','format','external_prerequisites','production_restore_authorized'}


def canonical(value: dict) -> bytes:
    return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()


def project_identity(p: dict) -> dict:
    # Validate the complete original project, including canonical UUID/DNS and database.
    render.validate({'schema_version':1,'target_installation':render.ROOT,
                     'allowed_postgres_service':'db','projects':[p]})
    return {'project_uuid':p['project_uuid'],'source_database':p['database'],
            'issuer':'https://'+p['hostname']+'/auth/v1','roles':b.names(p)}


def require_sha(value: str) -> str:
    if not isinstance(value,str) or not SHA.fullmatch(value):raise RecoveryError('SHA256_REQUIRED')
    return value


@contextmanager
def private_directory(path: pathlib.Path):
    if not path.is_absolute() or '..' in path.parts:raise RecoveryError('ABSOLUTE_PRIVATE_PATH_REQUIRED')
    fd=os.open('/',os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            nxt=os.open(part,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=nxt
        meta=os.fstat(fd)
        if meta.st_uid!=os.geteuid() or meta.st_mode & 0o077:
            raise RecoveryError('PRIVATE_DIRECTORY_OWNER_MODE_REQUIRED')
        readable=os.open('.',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
        os.close(fd);fd=readable
        yield fd
    finally:os.close(fd)


def open_private_file(directory: int, name: str) -> int:
    if pathlib.Path(name).name!=name or name in ('','.','..'):
        raise RecoveryError('PLAIN_FILENAME_REQUIRED')
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
    meta=os.fstat(fd)
    if not stat.S_ISREG(meta.st_mode) or meta.st_uid!=os.geteuid() or meta.st_mode & 0o077 or meta.st_nlink!=1:
        os.close(fd);raise RecoveryError('PRIVATE_REGULAR_SINGLE_LINK_FILE_REQUIRED')
    return fd


def digest_fd(fd: int) -> tuple[str,int]:
    before=os.fstat(fd);os.lseek(fd,0,os.SEEK_SET);h=hashlib.sha256();size=0
    while True:
        chunk=os.read(fd,1024*1024)
        if not chunk:break
        h.update(chunk);size+=len(chunk)
    after=os.fstat(fd)
    if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):
        raise RecoveryError('ARCHIVE_CHANGED_DURING_READ')
    os.lseek(fd,0,os.SEEK_SET)
    return h.hexdigest(),size


def validate_manifest(value: dict, p: dict) -> None:
    if not isinstance(value,dict) or set(value)!=CAPTURE_KEYS:
        raise RecoveryError('BACKUP_MANIFEST_FIELDS_INVALID')
    if type(value['schema_version']) is not int or value['schema_version']!=1 or value['kind']!='DIAL_PROJECT_LOGICAL_BACKUP_V1':
        raise RecoveryError('BACKUP_MANIFEST_KIND_INVALID')
    if value['project']!=project_identity(p):raise RecoveryError('BACKUP_PROJECT_MISMATCH')
    if value['format']!='postgresql-custom' or value['production_restore_authorized'] is not False:
        raise RecoveryError('BACKUP_IS_NOT_RESTORE_AUTHORITY')
    obs=value['observation'];arc=value['archive']
    if not isinstance(obs,dict) or set(obs)!={'database','project_uuid','issuer','server_version_num','system_identifier','snapshot'}:
        raise RecoveryError('BACKUP_OBSERVATION_INVALID')
    if obs['database']!=p['database'] or obs['project_uuid']!=p['project_uuid'] or obs['issuer']!=value['project']['issuer']:
        raise RecoveryError('BACKUP_OBSERVATION_SCOPE_MISMATCH')
    if type(obs['server_version_num']) is not int or not 170000<=obs['server_version_num']<180000:
        raise RecoveryError('POSTGRES17_OBSERVATION_REQUIRED')
    if not isinstance(obs['system_identifier'],str) or not re.fullmatch(r'[0-9]{1,20}',obs['system_identifier']) or not isinstance(obs['snapshot'],str) or not SNAPSHOT.fullmatch(obs['snapshot']):
        raise RecoveryError('NATIVE_SNAPSHOT_IDENTITY_REQUIRED')
    if not isinstance(arc,dict) or set(arc)!={'file','sha256','bytes'} or arc['file']!='project.dump' or type(arc['bytes']) is not int or arc['bytes']<5:
        raise RecoveryError('BACKUP_ARCHIVE_DESCRIPTOR_INVALID')
    require_sha(arc['sha256'])
    if not re.fullmatch(r'[a-f0-9]{40}',value['source_revision'] or ''):
        raise RecoveryError('SOURCE_REVISION_REQUIRED')
    if str(uuid.UUID(value['backup_id']))!=value['backup_id']:
        raise RecoveryError('BACKUP_UUID_REQUIRED')
    if datetime.fromisoformat(value['created_at']).tzinfo is None:
        raise RecoveryError('BACKUP_TIMESTAMP_REQUIRED')
    expected=['cluster_roles','project_secrets','server_configuration','storage_objects','independent_owner_admission']
    if value['external_prerequisites']!=expected:
        raise RecoveryError('BACKUP_PREREQUISITES_MISSING')


def sealed_archive(fd: int, expected_sha: str, expected_size: int) -> int:
    """Verify a bounded immutable copy; source changes cannot alter later restore input."""
    if expected_size>MAX_VERIFIED_ARCHIVE_BYTES:raise RecoveryError('ARCHIVE_EXCEEDS_QUALIFIED_SNAPSHOT_LIMIT')
    before=os.fstat(fd)
    if before.st_size!=expected_size:raise RecoveryError('BACKUP_ARCHIVE_DIGEST_MISMATCH')
    result=os.memfd_create('dial-verified-restore',os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
    try:
        os.lseek(fd,0,os.SEEK_SET);digest=hashlib.sha256();size=0
        while True:
            chunk=os.read(fd,1024*1024)
            if not chunk:break
            size+=len(chunk)
            if size>expected_size:raise RecoveryError('ARCHIVE_CHANGED_DURING_READ')
            digest.update(chunk)
            pending=memoryview(chunk)
            while pending:
                written=os.write(result,pending)
                if not written:raise RecoveryError('ARCHIVE_SNAPSHOT_WRITE_FAILED')
                pending=pending[written:]
        after=os.fstat(fd)
        if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):
            raise RecoveryError('ARCHIVE_CHANGED_DURING_READ')
        if size!=expected_size or digest.hexdigest()!=expected_sha:raise RecoveryError('BACKUP_ARCHIVE_DIGEST_MISMATCH')
        fcntl.fcntl(result,fcntl.F_ADD_SEALS,fcntl.F_SEAL_WRITE|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_GROW|fcntl.F_SEAL_SEAL)
        os.lseek(result,0,os.SEEK_SET)
        if os.read(result,5)!=b'PGDMP':raise RecoveryError('CUSTOM_ARCHIVE_MAGIC_REQUIRED')
        os.lseek(result,0,os.SEEK_SET)
        return result
    except BaseException:
        os.close(result);raise


@contextmanager
def verified_archive(bundle: pathlib.Path, expected_manifest_sha256: str, p: dict):
    """Yield a sealed verified byte snapshot. Consumers must use this FD, never a path."""
    require_sha(expected_manifest_sha256)
    with private_directory(bundle) as directory:
        mf=open_private_file(directory,'manifest.json')
        try:
            raw=os.read(mf,65537)
            if len(raw)>65536 or hashlib.sha256(raw).hexdigest()!=expected_manifest_sha256:
                raise RecoveryError('BACKUP_MANIFEST_DIGEST_MISMATCH')
            value=json.loads(raw,object_pairs_hook=render.unique_object)
            validate_manifest(value,p)
        finally:os.close(mf)
        archive=open_private_file(directory,'project.dump')
        snapshot=None
        try:
            snapshot=sealed_archive(archive,value['archive']['sha256'],value['archive']['bytes'])
            yield value,snapshot
        finally:
            if snapshot is not None:os.close(snapshot)
            os.close(archive)


def connection_env(config: dict) -> dict[str,str]:
    keys={'host','port','user','passfile','system_identifier','sslmode'}
    if not isinstance(config,dict) or set(config)!=keys:raise RecoveryError('ENDPOINT_FIELDS_INVALID')
    host=config['host']
    if not isinstance(host,str) or not (re.fullmatch(r'[a-zA-Z0-9_.-]+',host) or (host.startswith('/') and '\n' not in host and '\0' not in host)):
        raise RecoveryError('ENDPOINT_HOST_INVALID')
    if type(config['port']) is not int or not 1<=config['port']<=65535:raise RecoveryError('ENDPOINT_PORT_INVALID')
    b.ident(config['user'])
    if not isinstance(config['system_identifier'],str) or not re.fullmatch(r'[0-9]{1,20}',config['system_identifier']):
        raise RecoveryError('EXPECTED_CLUSTER_ID_REQUIRED')
    if config['sslmode'] not in ('verify-full','disable'):raise RecoveryError('ENDPOINT_TLS_MODE_INVALID')
    if config['sslmode']=='disable' and not (host.startswith('/') or host in ('127.0.0.1','localhost')):
        raise RecoveryError('REMOTE_TLS_REQUIRED')
    pw=pathlib.Path(config['passfile'])
    with private_directory(pw.parent) as directory:
        fd=open_private_file(directory,pw.name);os.close(fd)
    return {'PGHOST':host,'PGPORT':str(config['port']),'PGUSER':config['user'],
            'PGPASSFILE':str(pw),'PGSSLMODE':config['sslmode'],'PGCONNECT_TIMEOUT':'5',
            'PGAPPNAME':'dial-project-backup','PGOPTIONS':'-c statement_timeout=120000 -c lock_timeout=5000 -c search_path=pg_catalog'}


def read_snapshot(process: subprocess.Popen, deadline: float) -> dict:
    selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ)
    data=b''
    try:
        while time.monotonic()<deadline:
            if not selector.select(max(0,deadline-time.monotonic())):break
            chunk=os.read(process.stdout.fileno(),4096)
            if not chunk:raise RecoveryError('SNAPSHOT_EXPORTER_EXITED')
            data+=chunk
            if len(data)>16384:raise RecoveryError('SNAPSHOT_OBSERVATION_TOO_LARGE')
            if b'\n' in data:return json.loads(data.split(b'\n',1)[0],object_pairs_hook=render.unique_object)
        raise RecoveryError('SNAPSHOT_EXPORT_TIMEOUT')
    finally:selector.close()


def bounded_dump(args: list[str], env: dict, output_fd: int, error_fd: int, timeout: float = 120) -> int:
    """Bound bytes and elapsed time; failed/partial output never becomes a backup manifest."""
    proc=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=error_fd,env=env,start_new_session=True)
    select=selectors.DefaultSelector();select.register(proc.stdout,selectors.EVENT_READ)
    deadline=time.monotonic()+timeout;total=0
    try:
        while True:
            remaining=deadline-time.monotonic()
            if remaining<=0 or not select.select(remaining):raise RecoveryError('PG_DUMP_TIMEOUT')
            chunk=os.read(proc.stdout.fileno(),1024*1024)
            if not chunk:break
            total+=len(chunk)
            if total>MAX_VERIFIED_ARCHIVE_BYTES:raise RecoveryError('ARCHIVE_EXCEEDS_QUALIFIED_SNAPSHOT_LIMIT')
            pending=memoryview(chunk)
            while pending:
                n=os.write(output_fd,pending)
                if not n:raise RecoveryError('DUMP_WRITE_FAILED')
                pending=pending[n:]
        proc.wait(timeout=max(.1,deadline-time.monotonic()))
        if proc.returncode:raise RecoveryError('PG_DUMP_FAILED_PRIVATE_DIAGNOSTICS_RETAINED')
        return total
    finally:
        select.close();proc.stdout.close()
        if proc.poll() is None:
            os.killpg(proc.pid,signal.SIGTERM)
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)


def capture(p: dict, config: dict, pg_bin: pathlib.Path, out: pathlib.Path,
            source_revision: str, library_path: str | None = None) -> dict:
    identity=project_identity(p)
    if not re.fullmatch(r'[a-f0-9]{40}',source_revision):raise RecoveryError('SOURCE_REVISION_REQUIRED')
    if not pg_bin.is_absolute() or any(not (pg_bin/n).is_file() or not os.access(pg_bin/n,os.X_OK) for n in ('psql','pg_dump')):
        raise RecoveryError('EXACT_PG_BINARIES_REQUIRED')
    endpoint=connection_env(config)
    env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8',**endpoint,'PGDATABASE':p['database']}
    if library_path:
        if not pathlib.Path(library_path).is_absolute():raise RecoveryError('ABSOLUTE_LIBRARY_PATH_REQUIRED')
        env['LD_LIBRARY_PATH']=library_path
    render.write_bundle(out,{'capture-intent.json':canonical({'project':identity,'source_revision':source_revision,'state':'CAPTURE_PREPARED_NOT_COMPLETE'}).decode()})
    exporter=None
    with private_directory(out) as directory:
        archive_fd=os.open('project.dump.partial',os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
        log_fd=os.open('capture-errors.private.txt',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
        try:
            exporter=subprocess.Popen([str(pg_bin/'psql'),'-X','-qAt','--no-password','-v','ON_ERROR_STOP=1'],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log_fd,env=env,start_new_session=True)
            query="BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n"+\
                "SELECT json_build_object('database',current_database(),'project_uuid',(SELECT project_uuid::text FROM dial_private.project_identity WHERE singleton),'issuer',(SELECT issuer FROM dial_private.project_identity WHERE singleton),'server_version_num',current_setting('server_version_num')::int,'system_identifier',(SELECT system_identifier::text FROM pg_control_system()),'snapshot',pg_export_snapshot());\n"
            exporter.stdin.write(query.encode());exporter.stdin.flush()
            obs=read_snapshot(exporter,time.monotonic()+15)
            if obs.get('database')!=p['database'] or obs.get('project_uuid')!=p['project_uuid'] or obs.get('issuer')!=identity['issuer'] or obs.get('system_identifier')!=config['system_identifier']:
                raise RecoveryError('LIVE_BACKUP_SOURCE_MISMATCH')
            if type(obs.get('server_version_num')) is not int or not 170000<=obs['server_version_num']<180000 or not SNAPSHOT.fullmatch(obs.get('snapshot','')):
                raise RecoveryError('PG17_SNAPSHOT_REQUIRED')
            args=[str(pg_bin/'pg_dump'),'--no-password','--format=custom','--compress=6',
                  '--snapshot='+obs['snapshot'],'--lock-wait-timeout=5000','--dbname='+p['database']]
            bounded_dump(args,env,archive_fd,log_fd)
            exporter.stdin.write(b'COMMIT;\n\\q\n');exporter.stdin.close();exporter.stdin=None
            exporter.wait(timeout=10)
            if exporter.returncode:raise RecoveryError('SNAPSHOT_COMMIT_FAILED')
            os.fsync(archive_fd);digest,size=digest_fd(archive_fd)
            if os.read(archive_fd,5)!=b'PGDMP':raise RecoveryError('DUMP_FORMAT_INVALID')
            manifest={'schema_version':1,'kind':'DIAL_PROJECT_LOGICAL_BACKUP_V1',
                'backup_id':str(uuid.uuid4()),'created_at':datetime.now(timezone.utc).isoformat(),
                'source_revision':source_revision,'project':identity,'observation':obs,
                'archive':{'file':'project.dump','sha256':digest,'bytes':size},'format':'postgresql-custom',
                'external_prerequisites':['cluster_roles','project_secrets','server_configuration','storage_objects','independent_owner_admission'],
                'production_restore_authorized':False}
            validate_manifest(manifest,p)
            os.rename('project.dump.partial','project.dump',src_dir_fd=directory,dst_dir_fd=directory)
            raw=canonical(manifest)
            mf=os.open('manifest.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
            with os.fdopen(mf,'wb') as handle:handle.write(raw);handle.flush();os.fsync(handle.fileno())
            os.fsync(directory)
            return {'state':'LOGICAL_BACKUP_CAPTURED_NOT_RESTORE_QUALIFIED','backup_id':manifest['backup_id'],
                    'manifest_sha256':hashlib.sha256(raw).hexdigest(),'archive_sha256':digest,'archive_bytes':size}
        finally:
            if exporter is not None:
                if exporter.poll() is None:
                    os.killpg(exporter.pid,signal.SIGTERM)
                    try:exporter.wait(timeout=5)
                    except subprocess.TimeoutExpired:os.killpg(exporter.pid,signal.SIGKILL);exporter.wait(timeout=5)
                if exporter.stdin is not None:exporter.stdin.close()
                if exporter.stdout is not None:exporter.stdout.close()
            os.close(archive_fd);os.close(log_fd)


def restore_plan(p: dict, manifest: dict, target: str, all_projects: list[dict],
                 expected_manifest_sha256: str) -> dict:
    """No side effects. Exact FD-bound archive verification is required again at execution."""
    validate_manifest(manifest,p);require_sha(expected_manifest_sha256)
    if hashlib.sha256(canonical(manifest)).hexdigest()!=expected_manifest_sha256:
        raise RecoveryError('RESTORE_PLAN_MANIFEST_MISMATCH')
    b.ident(target)
    if target in {x['database'] for x in all_projects}|{'postgres','template0','template1','legacy_van'} or not re.fullmatch(r'dial_restore_[a-f0-9]{16}',target):
        raise RecoveryError('FRESH_QUARANTINE_DATABASE_REQUIRED')
    owner=b.ident(b.names(p)['owner']);db=b.ident(target)
    preflight="\\set ON_ERROR_STOP on\nDO $check$ BEGIN IF EXISTS (SELECT FROM pg_database WHERE datname="+b.lit(target)+") THEN RAISE EXCEPTION 'RESTORE_TARGET_ALREADY_EXISTS'; END IF; END $check$;\n"
    create=preflight+f'CREATE DATABASE {db} OWNER {owner} TEMPLATE template0 ALLOW_CONNECTIONS false CONNECTION LIMIT 8;\nREVOKE ALL ON DATABASE {db} FROM PUBLIC;\nALTER DATABASE {db} ALLOW_CONNECTIONS true;\n'
    pre_restore="\\set ON_ERROR_STOP on\nDO $check$ BEGIN "+\
        f"IF current_database()<>{b.lit(target)} OR (SELECT system_identifier::text FROM pg_control_system())<>{b.lit(manifest['observation']['system_identifier'])} THEN RAISE EXCEPTION 'RESTORE_TARGET_IDENTITY_MISMATCH'; END IF; "+\
        f"IF NOT EXISTS (SELECT FROM pg_database d JOIN pg_roles r ON r.oid=d.datdba WHERE d.datname=current_database() AND r.rolname={b.lit(b.names(p)['owner'])}) THEN RAISE EXCEPTION 'RESTORE_TARGET_OWNER_MISMATCH'; END IF; "+\
        "IF EXISTS (SELECT FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%' AND n.nspname NOT LIKE 'pg_temp%') OR EXISTS (SELECT FROM pg_namespace WHERE nspname NOT IN ('public','pg_catalog','information_schema') AND nspname NOT LIKE 'pg_toast%' AND nspname NOT LIKE 'pg_temp%') OR EXISTS (SELECT FROM pg_proc WHERE pronamespace='public'::regnamespace) OR EXISTS (SELECT FROM pg_type WHERE typnamespace='public'::regnamespace) OR EXISTS (SELECT FROM pg_extension WHERE extname<>'plpgsql') OR EXISTS (SELECT FROM pg_foreign_server) THEN RAISE EXCEPTION 'RESTORE_TARGET_NOT_EMPTY'; END IF; "+\
        "IF EXISTS (SELECT FROM pg_database d,LATERAL aclexplode(coalesce(d.datacl,acldefault('d',d.datdba))) a WHERE d.datname=current_database() AND a.grantee<>d.datdba AND a.privilege_type IN ('CONNECT','CREATE')) THEN RAISE EXCEPTION 'RESTORE_TARGET_NOT_QUARANTINED'; END IF; END $check$;\n"
    return {'schema_version':1,'kind':'FRESH_PROJECT_RESTORE_PLAN_NOT_EXECUTED',
            'project_uuid':p['project_uuid'],'source_database':p['database'],'target_database':target,
            'manifest_sha256':expected_manifest_sha256,'archive_sha256':manifest['archive']['sha256'],
            'expected_cluster_system_identifier':manifest['observation']['system_identifier'],
            'create_sql':create,'pre_restore_sql':pre_restore,
            'restore_args':['--no-password','--exit-on-error','--single-transaction','--dbname='+target],
            'archive_input':'VERIFIED_OPEN_FD_REQUIRED_NOT_REOPENED_PATH',
            'preserves_owners_and_acls':True,'changes_source_database':False,'switches_live_routing':False,
            'production_restore_authorized':False,
            'required_before_restore':['trusted_source_SQL_review','same_cluster_identity_and_existing_roles','new_empty_target','independent_owner_admission'],
            'required_before_cutover':['restored_identity_and_schema_verification','project_data_and_auth_checks','single_writer_fence','project_only_HBA_and_DSN_change','neighbor_regression','durable_original_receipt']}


def load_private_json(path: pathlib.Path) -> dict:
    with private_directory(path.parent) as directory:
        fd=open_private_file(directory,path.name)
        try:
            raw=os.read(fd,65537)
            if len(raw)>65536:raise RecoveryError('PRIVATE_JSON_TOO_LARGE')
            return json.loads(raw,object_pairs_hook=render.unique_object)
        finally:os.close(fd)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('capture','verify','plan'))
    parser.add_argument('--manifest',type=pathlib.Path,required=True)
    parser.add_argument('--project',required=True)
    parser.add_argument('--endpoint',type=pathlib.Path)
    parser.add_argument('--pg-bin',type=pathlib.Path)
    parser.add_argument('--library-path')
    parser.add_argument('--source-revision')
    parser.add_argument('--out',type=pathlib.Path)
    parser.add_argument('--bundle',type=pathlib.Path)
    parser.add_argument('--manifest-sha256')
    parser.add_argument('--target')
    a=parser.parse_args(argv)
    try:
        ps,_=render.load_manifest(a.manifest)
        matched=[p for p in ps if p['slug']==a.project]
        if len(matched)!=1:raise RecoveryError('EXACT_PROJECT_REQUIRED')
        p=matched[0]
        if a.action=='capture':
            if not all((a.endpoint,a.pg_bin,a.out,a.source_revision)):raise RecoveryError('CAPTURE_ARGUMENTS_REQUIRED')
            result=capture(p,load_private_json(a.endpoint),a.pg_bin,a.out,a.source_revision,a.library_path)
        else:
            if not a.bundle or not a.manifest_sha256:raise RecoveryError('EXTERNAL_MANIFEST_DIGEST_REQUIRED')
            with verified_archive(a.bundle,a.manifest_sha256,p) as (m,fd):
                if a.action=='verify':result={'state':'ARCHIVE_INTEGRITY_VERIFIED_NOT_RESTORED','project_uuid':p['project_uuid'],'archive_sha256':m['archive']['sha256']}
                else:
                    if not a.target or not a.out:raise RecoveryError('RESTORE_PLAN_ARGUMENTS_REQUIRED')
                    plan=restore_plan(p,m,a.target,ps,a.manifest_sha256)
                    render.write_bundle(a.out,{'restore-plan.json':canonical(plan).decode(),'create-quarantine.sql':plan['create_sql'],'pre-restore-check.sql':plan['pre_restore_sql']})
                    result={'state':'RESTORE_PLAN_CREATED_NOT_EXECUTED','target_database':a.target}
        print(json.dumps(result,sort_keys=True));return 0
    except (ValueError,TypeError,KeyError,OSError,subprocess.SubprocessError) as exc:
        # Never print external command stderr, connection passwords or arbitrary input.
        print('REFUSED: '+(str(exc) if isinstance(exc,RecoveryError) else type(exc).__name__));return 2

if __name__=='__main__':raise SystemExit(main())
