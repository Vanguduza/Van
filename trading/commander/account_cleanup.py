"""Private prospective unlink evidence in the existing native control journal.

These are technical facts, not business operations or retrospective completion.
MAY_BEGIN is a durable reservation before a syscall, not proof it was attempted.
A filesystem/SQL gap stays ambiguous. Parent UNKNOWN is never rewritten.
"""
from dataclasses import dataclass,asdict
from contextlib import contextmanager
import json
import hashlib
import hmac
import secrets
import stat
import sqlite3
from urllib.parse import quote
import os
from pathlib import Path
import re
import time

from fastapi import HTTPException
from vati.core.canonical import canonical_hash

SCHEMA='vati.private-unlink-recovery/2'
TYPE='INTERNAL_UNLINK_RECOVERY'
PRODUCER='vati-native-account-control'
HEX=re.compile(r'^[0-9a-f]{64}$')
STEPS=('REGISTRY_REMOVE','CREDENTIAL_OVERWRITE','CREDENTIAL_UNLINK')
IDENTITY_FIELDS=('alias','broker','mode','server','login','currency','venue','bridge_url','demo','enabled','router_venue','safety_identity')


def unknown():
    from commander.account_effects import AccountEffectUnknown
    return AccountEffectUnknown('Original local-unlink recovery evidence is unavailable or ambiguous; HOLD')


def generation(st):
    return [st.st_dev,st.st_ino,st.st_mode,st.st_size,st.st_mtime_ns,st.st_ctime_ns]


def root_identity(path):
    p=Path(path)
    if p.is_symlink() or not p.is_dir():raise unknown()
    st=p.stat()
    return {'path_ref':canonical_hash(str(p.resolve())),'device':st.st_dev,'inode':st.st_ino,'uid':st.st_uid,'mode':st.st_mode}


def continuity(settings,registry):
    domain=Path(settings.secrets_dir)/'.account-control-domain.env'
    if domain.is_symlink() or not domain.is_file():raise unknown()
    return {'secrets_root':root_identity(settings.secrets_dir),'registry_root':root_identity(registry.path.parent),
        'registry_ref':canonical_hash(str(registry.path.resolve())),
        'domain_file_generation':generation(domain.stat())}


def _hex(value):
    return isinstance(value,str) and HEX.fullmatch(value) is not None


def _generation(value):
    return isinstance(value,list) and len(value)==6 and all(type(x) is int and x>=0 for x in value)


def _root(value):
    return (isinstance(value,dict) and set(value)=={'path_ref','device','inode','uid','mode'} and _hex(value['path_ref'])
        and all(type(value[k]) is int and value[k]>=0 for k in ('device','inode','uid','mode')))


def _plan(plan):
    if not isinstance(plan,dict) or set(plan)!={'alias','account_control_domain','original_resource_version','review_digest',
            'account_identity','account_public_digest','registry_revision','removed_resource_version','continuity','credential_cleanup','target','steps'}:
        raise unknown()
    if (not isinstance(plan['alias'],str) or not re.fullmatch(r'[a-z0-9_]{3,32}',plan['alias'])
            or any(not _hex(plan[k]) for k in ('account_control_domain','original_resource_version','review_digest','account_public_digest','removed_resource_version'))
            or type(plan['registry_revision']) is not int or plan['registry_revision']<0):raise unknown()
    identity=plan['account_identity'];roots=plan['continuity']
    if (not isinstance(identity,dict) or set(identity)!=set(IDENTITY_FIELDS) or identity['alias']!=plan['alias']
            or type(identity['demo']) is not bool or type(identity['enabled']) is not bool
            or any(not isinstance(identity[k],str) or len(identity[k])>512 for k in IDENTITY_FIELDS if k not in {'demo','enabled'})
            or not isinstance(roots,dict) or set(roots)!={'secrets_root','registry_root','registry_ref','domain_file_generation'}
            or not _root(roots['secrets_root']) or not _root(roots['registry_root'])
            or not _hex(roots['registry_ref']) or not _generation(roots['domain_file_generation'])):raise unknown()
    if plan['credential_cleanup'] not in {'DELETE_MANAGED','KEEP_SHARED','KEEP_EXTERNAL','NONE'}:raise unknown()
    expected=list(STEPS if plan['credential_cleanup']=='DELETE_MANAGED' else STEPS[:1])
    if plan['steps']!=expected:raise unknown()
    target=plan['target']
    if plan['credential_cleanup']=='DELETE_MANAGED':
        if (not isinstance(target,dict) or set(target)!={'name','generation','uid','links'}
                or target['name']!=plan['alias']+'.env' or not _generation(target['generation'])
                or type(target['uid']) is not int or target['uid']<0 or type(target['links']) is not int or target['links']!=1):raise unknown()
    elif target is not None:raise unknown()


def is_technical(event):
    """Strict known discriminant only; never hides an arbitrary business row."""
    p=event.payload
    if not isinstance(p,dict) or p.get('record_type')!=TYPE:return False
    try:
        if (set(p)!={'schema','record_type','operation_id','device_id','account_control_domain','kind','previous_ref','data'}
                or p['schema']!=SCHEMA or event.hash!=canonical_hash(event.body())
                or not isinstance(p['operation_id'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,128}',p['operation_id'])
                or not isinstance(p['device_id'],str) or not 1<=len(p['device_id'])<=256
                or not _hex(p['account_control_domain'])
                or not isinstance(p['previous_ref'],str) or p['previous_ref'] and not _hex(p['previous_ref'])):raise unknown()
        d=p['data']
        if p['kind']=='PLAN':_plan(d)
        elif p['kind']=='STEP':
            if (not isinstance(d,dict) or set(d)!={'plan_ref','epoch','step','state','generation','resource_version'}
                    or not _hex(d['plan_ref']) or type(d['epoch']) is not int or d['epoch']<1
                    or d['step'] not in STEPS or d['state'] not in {'MAY_BEGIN','DONE','VERIFIED_ABSENT'}
                    or d['generation'] is not None and not _generation(d['generation'])
                    or d['resource_version'] is not None and not _hex(d['resource_version'])):raise unknown()
        elif p['kind']=='CHILD':
            if (not isinstance(d,dict) or set(d)!={'plan_ref','epoch','intent','review_digest','reauth_fact_digest','retire_parent_safety_obligation'}
                    or not _hex(d['plan_ref']) or not _hex(d['review_digest']) or not _hex(d['reauth_fact_digest'])
                    or type(d['epoch']) is not int or d['epoch']<2 or type(d['retire_parent_safety_obligation']) is not bool):raise unknown()
            from commander.account_effects import AccountEffectIntent
            intent=AccountEffectIntent(**{**d['intent'],'targets':tuple(d['intent']['targets'])});intent.validate()
            if intent.command!='account_remove':raise unknown()
        elif p['kind']=='POSTCONDITION':
            if (not isinstance(d,dict) or set(d)!={'plan_ref','epoch','child_operation_id','resource_version','target_state_digest','native_review_ref','observed_at_ms','valid_until_ms','lease_epoch'}
                    or any(not _hex(d[k]) for k in ('plan_ref','resource_version','target_state_digest','native_review_ref'))
                    or any(type(d[k]) is not int for k in ('epoch','observed_at_ms','valid_until_ms','lease_epoch'))
                    or d['epoch']<2 or d['lease_epoch']<1 or not 0<=d['observed_at_ms']<d['valid_until_ms']<=d['observed_at_ms']+30000
                    or not isinstance(d['child_operation_id'],str)):raise unknown()
        elif p['kind']=='RESOLUTION':
            if (not isinstance(d,dict) or set(d)!={'plan_ref','epoch','child_operation_id','child_applied_ref','postcondition_ref','parent_original_ref','retire_parent_safety_obligation'}
                    or any(not _hex(d[k]) for k in ('plan_ref','child_applied_ref','postcondition_ref','parent_original_ref'))
                    or type(d['epoch']) is not int or d['epoch']<2 or d['retire_parent_safety_obligation'] is not True
                    or not isinstance(d['child_operation_id'],str)):raise unknown()
        elif p['kind']=='EPOCH':
            if (not isinstance(d,dict) or set(d)!={'plan_ref','epoch','executor_operation_id'}
                    or not _hex(d['plan_ref']) or type(d['epoch']) is not int or d['epoch']<1
                    or not isinstance(d['executor_operation_id'],str)
                    or not re.fullmatch(r'[A-Za-z0-9_-]{20,128}',d['executor_operation_id'])):raise unknown()
        else:raise unknown()
        return True
    except (KeyError,TypeError,ValueError,AttributeError) as exc:
        raise unknown() from exc


@dataclass(frozen=True)
class CleanupFact:
    payload: dict
    received_at_ms: int
    hash: str

    def body(self):
        return {'producer':PRODUCER,'received_at_ms':self.received_at_ms,'payload':self.payload}


class UnlinkRecoveryBook:
    """Technical tables in the SAME existing DB; independent committed writer.

    No global business chain-head lock is acquired. A caller lending an active
    Ledger transaction is refused rather than pretending staged facts are durable.
    The private lease connection keeps its own row/kernel fence throughout.
    """
    def __init__(self,ledger,*,clock=None,initialize=True,secrets_root=None):
        self.ledger=ledger;self.clock=clock or (lambda:int(time.time()*1000))
        self.pg=hasattr(ledger,'name')
        self.namespace=ledger.name if self.pg else 'vati'
        self._active=None
        self.secrets_root=Path(secrets_root) if secrets_root is not None else None
        if initialize:
            from vati.core.ledger import require_committed_source_read
            require_committed_source_read(ledger)
        self._available=self._ensure_schema(allow_create=initialize)

    def _connect(self):
        if self.pg:
            db=self.ledger._connect(self.ledger.path)
            db.autocommit=True
            db.execute('SET synchronous_commit=on')
            return db
        path=Path(self.ledger.path).resolve()
        if not path.is_file():raise unknown()
        db=sqlite3.connect('file:'+quote(str(path))+'?mode=rw',uri=True,timeout=5,isolation_level=None)
        db.execute('PRAGMA synchronous=FULL')
        return db

    def _table(self,name):return ('vati.' if self.pg else '')+'account_unlink_'+name

    def _execute(self,db,sql,values=()):
        return db.execute(sql.replace('?', '%s') if self.pg else sql,values)

    def _ensure_schema(self,*,allow_create=True):
        # This is a transactional versioned native-owner migration, not a new DB.
        # The three tables contain only technical recovery facts/heads/schema ID.
        with self._connection() as db:
            probe=(self._execute(db,"SELECT to_regclass('vati.account_unlink_schema')").fetchone()[0]
                   if self.pg else self._execute(db,"SELECT name FROM sqlite_master WHERE type='table' AND name='account_unlink_schema'").fetchone())
            if probe is None:
                if not allow_create:return False
                # Never turn orphaned/unsealed technical history into a new schema.
                for suffix in ('heads','facts'):
                    present=(self._execute(db,'SELECT to_regclass(?)',(self._table(suffix),)).fetchone()[0] if self.pg else
                             self._execute(db,"SELECT name FROM sqlite_master WHERE type='table' AND name=?",(self._table(suffix),)).fetchone())
                    if present is not None:raise unknown()
                self._execute(db,'BEGIN')
                try:
                    self._execute(db,'CREATE TABLE IF NOT EXISTS '+self._table('schema')+' (version INTEGER PRIMARY KEY, contract TEXT NOT NULL)')
                    self._execute(db,'CREATE TABLE IF NOT EXISTS '+self._table('heads')+' (namespace TEXT NOT NULL, operation_id TEXT NOT NULL, seq BIGINT NOT NULL, fact_ref TEXT NOT NULL, integrity_json TEXT NOT NULL, PRIMARY KEY(namespace,operation_id))')
                    self._execute(db,'CREATE TABLE IF NOT EXISTS '+self._table('facts')+' (namespace TEXT NOT NULL, operation_id TEXT NOT NULL, seq BIGINT NOT NULL, body_json TEXT NOT NULL, fact_ref TEXT NOT NULL, PRIMARY KEY(namespace,operation_id,seq), UNIQUE(namespace,fact_ref))')
                    self._execute(db,'INSERT INTO '+self._table('schema')+'(version,contract) VALUES(?,?) ON CONFLICT(version) DO NOTHING',(2,SCHEMA))
                    db.commit()
                except BaseException:db.rollback();raise
            rows=self._execute(db,'SELECT version,contract FROM '+self._table('schema')).fetchall()
            if rows!=[(2,SCHEMA)]:raise unknown()
            # Validate actual expected columns even after an interrupted/foreign DDL.
            expected={'schema':{'version','contract'},'heads':{'namespace','operation_id','seq','fact_ref','integrity_json'},
                      'facts':{'namespace','operation_id','seq','body_json','fact_ref'}}
            for table,columns in expected.items():
                if self.pg:
                    actual={r[0] for r in self._execute(db,"SELECT column_name FROM information_schema.columns WHERE table_schema='vati' AND table_name=?",('account_unlink_'+table,)).fetchall()}
                else:actual={r[1] for r in self._execute(db,'PRAGMA table_info('+self._table(table)+')').fetchall()}
                if actual!=columns:raise unknown()
                primary={'schema':('version',),'heads':('namespace','operation_id'),'facts':('namespace','operation_id','seq')}[table]
                expected_constraints={('p',primary)}
                if table=='facts':expected_constraints.add(('u',('namespace','fact_ref')))
                if self.pg:
                    constraints=self._execute(db,
                        'SELECT c.contype,c.condeferrable,c.convalidated,array_agg(a.attname ORDER BY k.ordinality) '
                        'FROM pg_constraint c CROSS JOIN LATERAL unnest(c.conkey) WITH ORDINALITY k(attnum,ordinality) '
                        'JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.attnum '
                        "WHERE c.conrelid=?::regclass AND c.contype IN ('p','u') GROUP BY c.oid,c.contype",
                        (self._table(table),)).fetchall()
                    if any(r[1] or not r[2] for r in constraints):raise unknown()
                    present={(r[0],tuple(r[3])) for r in constraints}
                    details=self._execute(db,"SELECT column_name,data_type,is_nullable FROM information_schema.columns WHERE table_schema='vati' AND table_name=?",('account_unlink_'+table,)).fetchall()
                    types={k:('integer' if k=='version' else 'bigint' if k=='seq' else 'text','NO') for k in columns}
                    if {r[0]:(r[1],r[2]) for r in details}!=types:raise unknown()
                else:
                    details=self._execute(db,'PRAGMA table_info('+self._table(table)+')').fetchall()
                    expected_types={k:('INTEGER' if k=='version' else 'BIGINT' if k=='seq' else 'TEXT') for k in columns}
                    if any(r[2].upper()!=expected_types[r[1]] or r[4] is not None
                            or r[3]!=(0 if table=='schema' and r[1]=='version' else 1) for r in details):raise unknown()
                    if tuple(r[1] for r in sorted(details,key=lambda r:r[5]) if r[5])!=primary:raise unknown()
                    present={('p',primary)}
                    for index in self._execute(db,'PRAGMA index_list('+self._table(table)+')').fetchall():
                        if index[2] and index[3]!='pk':
                            if index[4]:raise unknown()
                            names=tuple(r[2] for r in self._execute(db,'PRAGMA index_info('+index[1]+')').fetchall())
                            present.add(('u',names))
                if present!=expected_constraints:raise unknown()
            return True

    @contextmanager
    def _connection(self):
        # Missing/corrupt/unavailable private SQL evidence is a typed HOLD;
        # never reconstruct tables/history or expose a driver error as data.
        errors=(sqlite3.DatabaseError,)
        if self.pg:
            import psycopg
            errors+=(psycopg.Error,)
        db=None
        try:
            db=self._connect()
            yield db
        except errors as exc:raise unknown() from exc
        finally:
            if db is not None:db.close()

    @contextmanager
    def atomic(self,operation_id):
        from vati.core.ledger import require_committed_source_read
        require_committed_source_read(self.ledger)
        if not self._available:raise unknown()
        if self._active is not None:raise unknown()
        with self._connection() as db:
            self._execute(db,'BEGIN' if self.pg else 'BEGIN IMMEDIATE')
            try:
                self._execute(db,'INSERT INTO '+self._table('heads')+'(namespace,operation_id,seq,fact_ref,integrity_json) VALUES(?,?,0,?,?) ON CONFLICT(namespace,operation_id) DO NOTHING',(self.namespace,operation_id,'',''))
                self._execute(db,'SELECT seq FROM '+self._table('heads')+' WHERE namespace=? AND operation_id=?'+(' FOR UPDATE' if self.pg else ''),(self.namespace,operation_id)).fetchone()
                self._active=db
                yield
                db.commit()  # MUST finish before the caller can reach a filesystem effect
            except BaseException:db.rollback();raise
            finally:self._active=None

    def _integrity_key(self,*,create=False):
        """Local data integrity only. Never creates on reads or over history."""
        from vati.core.file_lock import exclusive_state_lock
        from commander.accounts import _write_secrets
        if self.secrets_root is None:raise unknown()
        root_identity(self.secrets_root)
        path=self.secrets_root/'private.unlink-plan-integrity.env'
        # Refuse a pre-existing link before the replace-lock helper resolves its
        # target; do not create a foreign sidecar merely to refuse this read.
        if path.is_symlink():raise unknown()
        with exclusive_state_lock(path):
            if path.is_symlink():raise unknown()
            if not path.exists():
                if not create:raise unknown()
                db=self._active
                if db is None:raise unknown()
                if self._execute(db,'SELECT 1 FROM '+self._table('facts')+' LIMIT 1').fetchone():raise unknown()
                _write_secrets(path,{'UNLINK_PLAN_INTEGRITY_KEY':secrets.token_hex(32)},merge=False)
                directory=os.open(self.secrets_root,os.O_RDONLY|os.O_DIRECTORY)
                try:os.fsync(directory)
                finally:os.close(directory)
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
            try:
                before=os.fstat(fd)
                if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid()
                        or stat.S_IMODE(before.st_mode)!=0o600 or before.st_nlink!=1 or before.st_size>256):raise unknown()
                raw=os.read(fd,257).decode('ascii')
                after=os.fstat(fd)
                if generation(before)!=generation(after) or generation(after)!=generation(path.lstat()):raise unknown()
            except (OSError,UnicodeError) as exc:raise unknown() from exc
            finally:os.close(fd)
            match=re.fullmatch(r'UNLINK_PLAN_INTEGRITY_KEY=([0-9a-f]{64})\n',raw)
            if match is None:raise unknown()
            key=bytes.fromhex(match[1])
            identity={'key_id':hashlib.sha256(key).hexdigest(),'key_generation':generation(after),
                      'root':root_identity(self.secrets_root),'schema':'vati.unlink-integrity/1'}
            return key,identity

    def _seal(self,operation_id,seq,ref,purpose,*,create=False):
        try:key,identity=self._integrity_key(create=create)
        except (OSError,ValueError) as exc:raise unknown() from exc
        from commander.account_effects import AccountEffectJournal
        parent=AccountEffectJournal(self.ledger)._states().get(operation_id)
        if parent is None:raise unknown()
        context={'identity':identity,'purpose':purpose,'namespace':self.namespace,'operation_id':operation_id,
                 'original_intent_hash':canonical_hash(asdict(parent.intent)),'sequence':seq,'fact_ref':ref}
        return {'context':context,'mac':hmac.new(key,canonical_hash(context).encode('ascii'),hashlib.sha256).hexdigest()}

    def _verify_seal(self,value,operation_id,seq,ref,purpose):
        expected=self._seal(operation_id,seq,ref,purpose)
        if not isinstance(value,dict) or set(value)!={'context','mac'} or value['context']!=expected['context']:
            raise unknown()
        if not isinstance(value['mac'],str) or not hmac.compare_digest(value['mac'],expected['mac']):raise unknown()

    def _facts(self,operation_id):
        if not self._available:return []
        def read(db):
            rows=self._execute(db,'SELECT seq,body_json,fact_ref FROM '+self._table('facts')+' WHERE namespace=? AND operation_id=? ORDER BY seq',(self.namespace,operation_id)).fetchall()
            head=self._execute(db,'SELECT seq,fact_ref,integrity_json FROM '+self._table('heads')+' WHERE namespace=? AND operation_id=?',(self.namespace,operation_id)).fetchone()
            facts=[]
            for number,(seq,raw,ref) in enumerate(rows,1):
                try:
                    body=json.loads(raw)
                    seal=body.pop('integrity',None) if isinstance(body,dict) else None
                    self._verify_seal(seal,operation_id,seq,ref,'FACT')
                    if seq!=number or not isinstance(body,dict) or set(body)!={'producer','received_at_ms','payload'} or body['producer']!=PRODUCER or type(body['received_at_ms']) is not int:raise unknown()
                    fact=CleanupFact(body['payload'],body['received_at_ms'],ref)
                    if canonical_hash(fact.body())!=ref:raise unknown()
                except (KeyError,TypeError,ValueError) as exc:raise unknown() from exc
                facts.append(fact)
            if (head is None and rows or head is not None and head[:2]!=(len(rows),facts[-1].hash if facts else '')):raise unknown()
            if rows:
                try:self._verify_seal(json.loads(head[2]),operation_id,len(rows),facts[-1].hash,'HEAD')
                except (ValueError,TypeError) as exc:raise unknown() from exc
            elif head is not None and head[2]!='':raise unknown()
            return facts
        if self._active is not None:return read(self._active)
        with self._connection() as db:
            # Head and facts share a real repeatable/read transaction.
            self._execute(db,'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY' if self.pg else 'BEGIN')
            try:return read(db)
            finally:db.rollback()

    def _history(self,operation_id):
        if not self.ledger.verify_chain()[0]:raise unknown()
        rows=[];plan=None;epoch=0;executor=None;steps={};previous='';children={};postconditions={};resolution=None
        for event in self._facts(operation_id):
            if not is_technical(event):raise unknown()
            p=event.payload;d=p['data']
            if p['operation_id']!=operation_id or p['previous_ref']!=previous:raise unknown()
            if plan is None:
                if p['kind']!='PLAN':raise unknown()
                plan=event
            elif p['kind']=='PLAN':raise unknown()
            elif (p['device_id']!=plan.payload['device_id'] or p['account_control_domain']!=plan.payload['account_control_domain']
                    or d['plan_ref']!=plan.hash):raise unknown()
            if p['kind']=='CHILD':
                raw=d['intent'];child_id=raw['operation_id']
                if (child_id in children or child_id==operation_id or d['epoch']!=epoch+1
                        or raw['device_id']!=plan.payload['device_id']
                        or 'account:'+plan.payload['data']['alias'] not in raw['targets']
                        or 'account-control-domain:'+plan.payload['account_control_domain'] not in raw['targets']):raise unknown()
                children[child_id]=event
            if p['kind']=='POSTCONDITION':
                if (d['epoch']!=epoch or d['child_operation_id']!=executor or executor not in children
                        or d['resource_version']!=plan.payload['data']['removed_resource_version']):raise unknown()
                postconditions[event.hash]=event
            if p['kind']=='RESOLUTION':
                if (resolution is not None or d['epoch']!=epoch or d['child_operation_id']!=executor
                        or d['postcondition_ref'] not in postconditions or executor not in children
                        or not children[executor].payload['data']['retire_parent_safety_obligation']):raise unknown()
                resolution=event
            if p['kind']=='EPOCH':
                if d['epoch']!=epoch+1 or epoch==0 and d['executor_operation_id']!=operation_id:raise unknown()
                if epoch>0 and (d['executor_operation_id'] not in children
                        or children[d['executor_operation_id']].payload['data']['epoch']!=d['epoch']):raise unknown()
                epoch=d['epoch'];executor=d['executor_operation_id']
            if p['kind']=='STEP':
                if d['state']=='MAY_BEGIN':
                    for prior in plan.payload['data']['steps'][:plan.payload['data']['steps'].index(d['step'])]:
                        if prior not in steps or steps[prior].payload['data']['state'] not in {'DONE','VERIFIED_ABSENT'}:raise unknown()
                if d['epoch']!=epoch or d['step'] not in plan.payload['data']['steps']:raise unknown()
                if d['state']=='MAY_BEGIN' and (d['generation'] is not None or d['resource_version'] is not None):raise unknown()
                if d['state']=='VERIFIED_ABSENT':
                    if epoch<2 or executor not in children or d['step'] not in {'REGISTRY_REMOVE','CREDENTIAL_UNLINK'}:raise unknown()
                if d['state'] in {'DONE','VERIFIED_ABSENT'}:
                    if d['resource_version']!=plan.payload['data']['removed_resource_version']:raise unknown()
                    if d['step']=='CREDENTIAL_OVERWRITE':
                        original=plan.payload['data']['target']['generation']
                        if not _generation(d['generation']) or d['generation'][:4]!=original[:4]:raise unknown()
                    elif d['generation'] is not None:raise unknown()
                old=steps.get(d['step'])
                if d['state']=='DONE' and (old is None or old.payload['data']['state']!='MAY_BEGIN' or old.payload['data']['epoch']!=epoch):raise unknown()
                if old is not None and (old.payload['data']['state'] in {'DONE','VERIFIED_ABSENT'} or old.payload['data']['epoch']==epoch and d['state']=='MAY_BEGIN'):raise unknown()
                steps[d['step']]=event
            rows.append(event);previous=event.hash
        if plan is not None:
            from commander.account_effects import AccountEffectJournal
            parent=AccountEffectJournal(self.ledger)._states().get(operation_id)
            d=plan.payload['data']
            if (parent is None or parent.intent.command!='account_remove' or parent.intent.device_id!=plan.payload['device_id']
                    or plan.payload['account_control_domain']!=d['account_control_domain']
                    or 'account:'+d['alias'] not in parent.intent.targets
                    or 'account-control-domain:'+d['account_control_domain'] not in parent.intent.targets
                    or parent.intent.resource_version!=d['original_resource_version']
                    or not parent.intent.authority_ref.endswith('::review:'+d['review_digest'])):raise unknown()
            states=AccountEffectJournal(self.ledger)._states()
            from commander.account_effects import AccountEffectIntent
            for child_id,record in children.items():
                raw=record.payload['data']['intent']
                intent=AccountEffectIntent(**{**raw,'targets':tuple(raw['targets'])})
                if child_id not in states or states[child_id].intent!=intent:raise unknown()
            if resolution is not None:
                r=resolution.payload['data'];child=states[r['child_operation_id']]
                if (parent.phase!='UNKNOWN' or parent.result is not None or r['parent_original_ref']!=parent.event_ref
                        or child.phase!='APPLIED' or child.event_ref!=r['child_applied_ref']
                        or child.result.get('postcondition_ref')!=r['postcondition_ref']
                        or child.result.get('cleanup_parent_operation_id')!=operation_id
                        or child.result.get('plan_ref')!=plan.hash):raise unknown()
        return {'plan':plan,'epoch':epoch,'executor':executor,'steps':steps,'rows':rows,'head':previous,
                'children':children,'postconditions':postconditions,'resolution':resolution}

    def _append(self,operation_id,device_id,domain,kind,data,previous):
        now=self.clock()
        body={'producer':PRODUCER,'received_at_ms':now,'payload':{'schema':SCHEMA,'record_type':TYPE,
            'operation_id':operation_id,'device_id':device_id,'account_control_domain':domain,'kind':kind,
            'previous_ref':previous,'data':data}}
        event=CleanupFact(body['payload'],now,canonical_hash(body))
        if self._active is None:raise unknown()
        is_technical(event)
        row=self._execute(self._active,'SELECT seq,fact_ref FROM '+self._table('heads')+' WHERE namespace=? AND operation_id=?',(self.namespace,operation_id)).fetchone()
        if row is None or row[1]!=previous:raise unknown()
        self._execute(self._active,'INSERT INTO '+self._table('facts')+'(namespace,operation_id,seq,body_json,fact_ref) VALUES(?,?,?,?,?)',
            (self.namespace,operation_id,row[0]+1,json.dumps({**body,'integrity':self._seal(operation_id,row[0]+1,event.hash,'FACT')},sort_keys=True,separators=(',',':'),allow_nan=False),event.hash))
        self._execute(self._active,'UPDATE '+self._table('heads')+' SET seq=?,fact_ref=?,integrity_json=? WHERE namespace=? AND operation_id=?',
            (row[0]+1,event.hash,json.dumps(self._seal(operation_id,row[0]+1,event.hash,'HEAD'),sort_keys=True,separators=(',',':')),self.namespace,operation_id))
        return event

    def prepare(self,intent,plan):
        """Inert prospective data before any physical original unlink effect."""
        from commander.account_effects import AccountEffectJournal
        _plan(plan)
        with self.atomic(intent.operation_id):
            state=AccountEffectJournal(self.ledger)._states().get(intent.operation_id)
            if state is None or state.intent!=intent or state.phase!='IN_FLIGHT' or intent.command!='account_remove':raise unknown()
            if ('account:'+plan['alias'] not in intent.targets or 'account-control-domain:'+plan['account_control_domain'] not in intent.targets
                    or intent.resource_version!=plan['original_resource_version']
                    or not intent.authority_ref.endswith('::review:'+plan['review_digest'])):raise unknown()
            history=self._history(intent.operation_id)
            if history['plan'] is not None:
                if history['plan'].payload['data']!=plan:raise unknown()
                return history['plan'].hash,history['epoch']
            try:self._integrity_key(create=True)
            except (OSError,ValueError) as exc:raise unknown() from exc
            event=self._append(intent.operation_id,intent.device_id,plan['account_control_domain'],'PLAN',plan,'')
            self._append(intent.operation_id,intent.device_id,plan['account_control_domain'],'EPOCH',
                {'plan_ref':event.hash,'epoch':1,'executor_operation_id':intent.operation_id},event.hash)
            return event.hash,1

    def require_epoch(self,operation_id,plan_ref,epoch,executor):
        h=self._history(operation_id)
        if h['plan'] is None or h['plan'].hash!=plan_ref or h['epoch']!=epoch or h['executor']!=executor:raise unknown()
        return h

    def step(self,operation_id,plan_ref,epoch,executor,step,state,*,post_generation=None,resource_version=None):
        with self.atomic(operation_id):
            h=self.require_epoch(operation_id,plan_ref,epoch,executor)
            plan=h['plan'];p=plan.payload
            self._append(operation_id,p['device_id'],p['account_control_domain'],'STEP',
                {'plan_ref':plan_ref,'epoch':epoch,'step':step,'state':state,
                 'generation':post_generation,'resource_version':resource_version},h['head'])
            # Validate the just-written transition before the commit can succeed.
            self._history(operation_id)

    def summary(self,operation_id,device_id):
        h=self._history(operation_id);plan=h['plan']
        if plan is None:return {'state':'LEGACY_UNBOUND_HOLD','plan_ref':None,'execution_authority':False}
        if plan.payload['device_id']!=device_id:raise unknown()
        from commander.account_effects import AccountEffectJournal
        parent=AccountEffectJournal(self.ledger).status(operation_id,device_id)
        epochs={row.payload['data']['epoch']:row.payload['data']['executor_operation_id'] for row in h['rows'] if row.payload['kind']=='EPOCH'}
        return {'schema':'vati.pending-local-cleanup/1','state':'QUALIFIED_SEPARATE_RESOLUTION' if h['resolution'] else 'PROSPECTIVE_PLAN_RETAINED',
                'plan_ref':plan.hash,'epoch':h['epoch'],'parent_operation_id':operation_id,'parent_phase':parent.phase,
                'step_facts':{k:{'state':v.payload['data']['state'],'epoch':v.payload['data']['epoch'],
                    'executor_operation_id':epochs[v.payload['data']['epoch']]} for k,v in h['steps'].items()},
                'linked_resolution_ref':h['resolution'].hash if h['resolution'] else None,
                'linked_resolution_child_operation_id':h['resolution'].payload['data']['child_operation_id'] if h['resolution'] else None,
                'linked_child_applied_ref':h['resolution'].payload['data']['child_applied_ref'] if h['resolution'] else None,
                'parent_original_unchanged':True,'execution_authority':False}

    def qualify_parent(self,operation_id,plan_ref,device_id,domain):
        from commander.account_effects import AccountEffectJournal
        history=self._history(operation_id);plan=history['plan']
        parent=AccountEffectJournal(self.ledger)._states().get(operation_id)
        if (plan is None or plan.hash!=plan_ref or plan.payload['device_id']!=device_id
                or plan.payload['account_control_domain']!=domain or parent is None
                or parent.phase not in {'IN_FLIGHT','UNKNOWN'} or parent.result is not None
                or not history['steps'] or history['resolution'] is not None):raise unknown()
        return QualifiedCleanupParent(operation_id,plan_ref,device_id,domain,canonical_hash(asdict(parent.intent)))

    def require_qualified(self,qualified):
        if not isinstance(qualified,QualifiedCleanupParent):raise unknown()
        actual=self.qualify_parent(qualified.operation_id,qualified.plan_ref,qualified.device_id,qualified.domain)
        if actual!=qualified:raise unknown()
        return self._history(qualified.operation_id)

    def begin_child(self,qualified,child,*,review_digest,reauth_fact_digest,retire_parent_safety_obligation):
        """Caller owns real lease->alias->registry->credential locks, never PID inference.

        This advances a prospective execution fence. Old original code checks it
        after ALL waits at every physical boundary; it cannot resume afterward.
        """
        from commander.account_effects import AccountEffectJournal
        self.require_qualified(qualified)
        journal=AccountEffectJournal(self.ledger);parent=journal.status(qualified.operation_id,qualified.device_id)
        if parent.phase=='IN_FLIGHT':journal.uncertain(parent)
        current=journal.status(child.intent.operation_id,qualified.device_id)
        if current!=child or current.phase!='IN_FLIGHT' or child.intent.command!='account_remove':raise unknown()
        with self.atomic(qualified.operation_id):
            history=self.require_qualified(qualified);plan=history['plan'];epoch=history['epoch']+1
            if child.intent.operation_id in history['children']:raise unknown()
            record=self._append(qualified.operation_id,qualified.device_id,qualified.domain,'CHILD',
                {'plan_ref':plan.hash,'epoch':epoch,'intent':asdict(child.intent),'review_digest':review_digest,
                 'reauth_fact_digest':reauth_fact_digest,'retire_parent_safety_obligation':retire_parent_safety_obligation},history['head'])
            self._append(qualified.operation_id,qualified.device_id,qualified.domain,'EPOCH',
                {'plan_ref':plan.hash,'epoch':epoch,'executor_operation_id':child.intent.operation_id},record.hash)
        return epoch

    def postcondition(self,qualified,child_id,epoch,*,target_state_digest,native_review_ref,observed_at_ms,valid_until_ms,lease_epoch):
        with self.atomic(qualified.operation_id):
            h=self.require_epoch(qualified.operation_id,qualified.plan_ref,epoch,child_id)
            if not observed_at_ms<=self.clock()<valid_until_ms:raise unknown()
            record=self._append(qualified.operation_id,qualified.device_id,qualified.domain,'POSTCONDITION',
                {'plan_ref':qualified.plan_ref,'epoch':epoch,'child_operation_id':child_id,
                 'resource_version':h['plan'].payload['data']['removed_resource_version'],
                 'target_state_digest':target_state_digest,'native_review_ref':native_review_ref,
                 'observed_at_ms':observed_at_ms,'valid_until_ms':valid_until_ms,'lease_epoch':lease_epoch},h['head'])
            self._history(qualified.operation_id)
        return record.hash

    def resolve(self,qualified,child_id,epoch,postcondition_ref):
        """A new linked fact AFTER child APPLIED, never the parent's result."""
        from commander.account_effects import AccountEffectJournal
        with self.atomic(qualified.operation_id):
            h=self.require_epoch(qualified.operation_id,qualified.plan_ref,epoch,child_id)
            # No second business writer inside the technical writer (SQLite
            # shares that database lock). Both referenced terminal outcomes are
            # immutable; use the existing owner's verified read snapshot.
            with self.ledger.read_snapshot():
                states=AccountEffectJournal(self.ledger)._states()
            parent=states.get(qualified.operation_id);child=states.get(child_id)
            post=h['postconditions'].get(postcondition_ref)
            if (parent is None or parent.phase!='UNKNOWN' or parent.result is not None or child is None or child.phase!='APPLIED'
                    or post is None or post.payload['data']['child_operation_id']!=child_id
                    or not h['children'][child_id].payload['data']['retire_parent_safety_obligation']
                    or not post.payload['data']['observed_at_ms']<=self.clock()<post.payload['data']['valid_until_ms']
                    or child.result.get('postcondition_ref')!=postcondition_ref):raise unknown()
            resolution=self._append(qualified.operation_id,qualified.device_id,qualified.domain,'RESOLUTION',
                {'plan_ref':qualified.plan_ref,'epoch':epoch,'child_operation_id':child_id,'child_applied_ref':child.event_ref,
                 'postcondition_ref':postcondition_ref,'parent_original_ref':parent.event_ref,
                 'retire_parent_safety_obligation':True},h['head'])
            self._history(qualified.operation_id)
        return resolution.hash

    def resolved(self,operation_id):
        # Expensive, independent chain/business/child/postcondition joins, not a status string.
        return self._history(operation_id)['resolution'] is not None


@dataclass(frozen=True)
class QualifiedCleanupParent:
    operation_id: str
    plan_ref: str
    device_id: str
    domain: str
    original_intent_hash: str


def prepare_plan(settings,registry,account,review,target):
    from vati.accounts.resource_version import resource_snapshot
    current=registry.get(account.alias)
    if (asdict(current)!=asdict(account) or resource_snapshot(registry,account.alias)['resource_version']!=review.get('resource_version')
            or review.get('before')!=account.public()
            or canonical_hash({k:v for k,v in review.items() if k!='review_digest'})!=review.get('review_digest')):raise unknown()
    cleanup=review['retirement']['credential_cleanup'];protected=None
    if target is not None:
        if target.is_symlink() or not target.is_file():raise unknown()
        st=target.stat()
        if st.st_nlink!=1 or st.st_uid!=os.getuid():raise unknown()
        protected={'name':target.name,'generation':generation(st),'uid':st.st_uid,'links':st.st_nlink}
    plan={'alias':account.alias,'account_control_domain':None,'original_resource_version':review['resource_version'],
        'review_digest':review['review_digest'],'account_identity':{k:getattr(account,k) for k in IDENTITY_FIELDS},
        'account_public_digest':canonical_hash(account.public()),'registry_revision':registry._loaded_revisions.get(account.alias,0),
        'removed_resource_version':canonical_hash({'schema':'vati.account-resource/1','alias':account.alias,
            'revision':registry._loaded_revisions.get(account.alias,0)+1,'account':None,'credential_file_generation':None}),
        'continuity':continuity(settings,registry),'credential_cleanup':cleanup,'target':protected,
        'steps':list(STEPS if cleanup=='DELETE_MANAGED' else STEPS[:1])}
    return plan


@dataclass(frozen=True)
class OriginalAccountObservation:
    """Original observation interface, NOT a new Account/registry/entry grant."""
    alias: str
    broker: str
    mode: str
    server: str
    login: str
    currency: str
    venue: str
    bridge_url: str
    demo: bool
    enabled: bool
    router_venue: str
    safety_identity: str

    @property
    def credential_ref(self):
        if self.broker!='PAPER':raise unknown()
        from vati.accounts.registry import CredentialRef
        return CredentialRef()


def original_target_state(settings,registry,book,qualified):
    """Call under canonical local locks, before/after I/O; absence is not old completion."""
    from vati.accounts.resource_version import resource_snapshot
    h=book.require_qualified(qualified);p=h['plan'].payload['data']
    if continuity(settings,registry)!=p['continuity']:raise unknown()
    current=registry.accounts.get(p['alias']);resource=resource_snapshot(registry,p['alias'])
    if current is not None:
        if (canonical_hash(current.public())!=p['account_public_digest'] or resource['resource_version']!=p['original_resource_version']
                or resource['revision']!=p['registry_revision']):raise unknown()
        if 'REGISTRY_REMOVE' in h['steps'] and h['steps']['REGISTRY_REMOVE'].payload['data']['state'] in {'DONE','VERIFIED_ABSENT'}:raise unknown()
        remaining=list(p['steps']);registry_state='ORIGINAL_PRESENT'
    else:
        if (resource['revision']!=p['registry_revision']+1 or resource['resource_version']!=p['removed_resource_version']
                or 'REGISTRY_REMOVE' not in h['steps']):raise unknown()
        remaining=[step for step in p['steps'] if step!='REGISTRY_REMOVE'];registry_state='ORIGINAL_LINK_ABSENT_NOT_ORIGINAL_COMPLETION'
    target=None;file_state='NOT_MANAGED'
    if p['target'] is not None:
        target=Path(settings.secrets_dir)/p['target']['name']
        if target.is_symlink():raise unknown()
        if target.exists():
            st=target.stat()
            if not target.is_file() or st.st_uid!=p['target']['uid'] or st.st_nlink!=1:raise unknown()
            current_generation=generation(st)
            overwrite=h['steps'].get('CREDENTIAL_OVERWRITE')
            if current_generation==p['target']['generation']:
                if overwrite is not None and overwrite.payload['data']['state']=='DONE':raise unknown()
                file_state='ORIGINAL_MANAGED_FILE'
            elif overwrite is not None and overwrite.payload['data']['state']=='DONE' and current_generation==overwrite.payload['data']['generation']:
                file_state='ORIGINAL_OWN_OVERWRITE_UNUSABLE_FOR_NEW_NATIVE_OBSERVATION'
                remaining=[step for step in remaining if step!='CREDENTIAL_OVERWRITE']
            else:raise unknown()
            if any(a.alias!=p['alias'] and a.credential_ref.secrets_file and Path(a.credential_ref.secrets_file).resolve()==target.resolve() for a in registry.accounts.values()):raise unknown()
        else:
            unlink=h['steps'].get('CREDENTIAL_UNLINK')
            if unlink is None or unlink.payload['data']['state'] not in {'DONE','VERIFIED_ABSENT'}:raise unknown()
            file_state='ORIGINAL_UNLINK_FACT_AND_CURRENT_ABSENCE_NOT_PROVIDER_STATE'
            remaining=[step for step in remaining if step not in {'CREDENTIAL_OVERWRITE','CREDENTIAL_UNLINK'}]
    state={'registry_state':registry_state,'resource_version':resource['resource_version'],'file_state':file_state,'remaining_steps':remaining,
           'original_plan_ref':qualified.plan_ref,'original_parent_operation_id':qualified.operation_id}
    return h,p,target,state


def original_observation_view(settings,registry,book,qualified,require_current):
    """Only original, still-intact managed credentials can supply this recovery read.

    No account/secret is restored or registered. Adapter factory receives a
    frozen original observation interface and unshared transport-only read view.
    """
    from vati.core.file_lock import exclusive_state_lock
    h=book.require_qualified(qualified);plan=h['plan'].payload['data'];alias=plan['alias']
    target=Path(settings.secrets_dir)/(alias+'.env')
    if plan['credential_cleanup']!='DELETE_MANAGED' or plan['target'] is None:raise unknown()
    def check(current):
        _,_,_,state=original_target_state(settings,current,book,qualified)
        if state['file_state']!='ORIGINAL_MANAGED_FILE':raise unknown()
    def qualify():
        book.require_qualified(qualified)
        if continuity(settings,registry)!=plan['continuity']:raise unknown()
        require_current()  # Actual current read/key/time/held lease; not a caller flag.
        return {'plan_ref':qualified.plan_ref,'device_id':qualified.device_id,'alias':alias,
                'managed_root_ref':plan['continuity']['secrets_root']['path_ref'],'file_generation':plan['target']['generation']}
    with registry._mutation_lock(),exclusive_state_lock(target):
        check(registry);qualify()
    view=registry.original_credential_read_view(alias=alias,managed_root=settings.secrets_dir,target=target,
        expected_generation=plan['target']['generation'],qualify=qualify,validate_current=check)
    return OriginalAccountObservation(**plan['account_identity']),view,qualify


class NativeCleanup:
    """Existing account_remove's explicit, original-bound pending-cleanup variant."""
    def __init__(self,settings,ledger,registry_factory,domain):
        self.settings,self.ledger,self.registry_factory,self.domain=settings,ledger,registry_factory,domain
        self.book=UnlinkRecoveryBook(ledger,initialize=False,secrets_root=settings.secrets_dir)

    @staticmethod
    def validate_args(args,*,with_fact=False):
        fields={'alias','variant','parent_operation_id','plan_ref','retire_parent_safety_obligation'}
        if with_fact:fields|={'reauth_fact_id','reauth_fact_digest'}
        values={k:v for k,v in args.items() if not k.startswith('_')}
        if (set(values)!=fields or values['variant']!='PENDING_CLEANUP'
                or not isinstance(values['alias'],str) or not re.fullmatch(r'[a-z0-9_]{3,32}',values['alias'])
                or not isinstance(values['parent_operation_id'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,128}',values['parent_operation_id'])
                or not _hex(values['plan_ref']) or type(values['retire_parent_safety_obligation']) is not bool):raise unknown()
        if with_fact and (not _hex(values['reauth_fact_digest']) or not isinstance(values['reauth_fact_id'],str)
                or not re.fullmatch(r'[A-Za-z0-9_-]{20,128}',values['reauth_fact_id'])):raise unknown()
        return values

    def _qualified(self,args,device_id):
        original=self.book._history(args['parent_operation_id'])['plan']
        if (original is None or original.hash!=args['plan_ref']
                or continuity(self.settings,self.registry_factory())!=original.payload['data']['continuity']):raise unknown()
        # A missing/replaced namespace key cannot be recreated merely to read
        # pending cleanup. Validate retained continuity BEFORE ordinary domain().
        qualified=self.book.qualify_parent(args['parent_operation_id'],args['plan_ref'],device_id,self.domain(self.ledger))
        h=self.book.require_qualified(qualified)
        if h['plan'].payload['data']['alias']!=args['alias']:raise unknown()
        return qualified

    def _observe(self,args,qualified,require_lease,read_guard,*,child_id=None):
        from contextlib import nullcontext
        from vati.core.file_lock import exclusive_state_lock
        from commander.account_retirement import inspect_retirement
        registry=self.registry_factory();h=self.book.require_qualified(qualified);p=h['plan'].payload['data']
        target=Path(self.settings.secrets_dir)/p['target']['name'] if p['target'] else None
        def require_current():
            if not callable(read_guard):raise HTTPException(403,'Current native owner-read scope unavailable; HOLD')
            read_guard();require_lease()
            if self.domain(self.ledger)!=qualified.domain:raise unknown()
            require_lease.check_time()
        with registry._mutation_lock(),exclusive_state_lock(target) if target else nullcontext():
            h,p,target,state=original_target_state(self.settings,self.registry_factory(),self.book,qualified)
            require_current()
            state_digest=canonical_hash(state);current=self.registry_factory().accounts.get(args['alias'])
        # NO registry writer or credential lock spans native/provider observations.
        observation_view=None;observation_guard=require_current
        if current is not None:account=current
        elif p['account_identity']['broker']=='PAPER':account=OriginalAccountObservation(**p['account_identity'])
        else:
            account,observation_view,observation_guard=original_observation_view(self.settings,registry,self.book,qualified,require_current)
        readbacks=[]
        facts=inspect_retirement(self.settings,registry,account,inside_removal=True,operation_id=child_id,native_ledger=self.ledger,
            readback_guards=readbacks,cleanup_parent=qualified,cleanup_book=self.book,
            observation_view=observation_view,observation_guard=observation_guard)
        if len(readbacks)!=1:raise unknown()
        with registry._mutation_lock(),exclusive_state_lock(target) if target else nullcontext():
            _,_,_,after=original_target_state(self.settings,self.registry_factory(),self.book,qualified)
            if canonical_hash(after)!=state_digest:raise unknown()
            readbacks[0]();require_current();readbacks[0].check_time()
        view={'parent_operation_id':qualified.operation_id,'plan_ref':qualified.plan_ref,'original_device_id':qualified.device_id,
            'account_control_domain':qualified.domain,'alias':args['alias'],'original_epoch':h['epoch'],
            'original_account':{k:p['account_identity'][k] for k in ('alias','broker','server','login','currency','demo','safety_identity')},
            'current_local_state':{'registry':state['registry_state'],'credential':state['file_state']},
            'original_step_head_ref':h['head'],'target_state_digest':state_digest,'remaining_steps':state['remaining_steps'],
            'retire_parent_safety_obligation':args['retire_parent_safety_obligation'],'retirement':facts,
            'parent_original_state':'UNKNOWN','parent_original_result':None,'provider_closure_authority':False}
        review={'schema':'vati.pending-account-cleanup-review/1','action':'account_remove','variant':'PENDING_CLEANUP',
            'request_digest':canonical_hash({k:v for k,v in args.items() if not k.startswith('_')}),
            'resource_version':state['resource_version'],'context_digest':canonical_hash(view),'view':view}
        review['review_digest']=canonical_hash(review)
        return review,readbacks[0],require_current

    def review(self,args,device_id,read_guard):
        from commander.account_retirement import retirement_scope
        self.validate_args(args,with_fact='reauth_fact_id' in args)
        qualified=self._qualified(args,device_id)
        with retirement_scope(self.settings,args['alias']) as lease,self.registry_factory().operation_lock(args['alias']):
            return self._observe(args,qualified,lease,read_guard)[0]

    def execute(self,args,intent,read_guard):
        from contextlib import nullcontext,ExitStack
        from commander.account_retirement import retirement_scope
        from commander.account_effects import AccountEffectJournal,invoke_account_effect,mark_account_effect,require_current_account_effect
        from commander.accounts import _shred
        from vati.core.file_lock import exclusive_state_lock
        self.validate_args(args,with_fact=True)
        journal=AccountEffectJournal(self.ledger,cleanup_secrets_root=self.settings.secrets_dir)
        existing=journal.status(intent.operation_id,intent.device_id)
        if existing is not None:
            from commander.account_effects import AccountOperationUnconfirmed,AccountEffectConflict
            if existing.intent!=intent:raise AccountEffectConflict('Original cleanup child intent differs')
            if existing.phase=='APPLIED':return existing.result
            if existing.phase=='REFUSED':raise HTTPException(existing.result['status_code'],existing.result['detail'])
            raise AccountOperationUnconfirmed(intent.operation_id)
        qualified=self._qualified(args,intent.device_id)
        scopes=ExitStack();recovery={}
        def child_effect():
            lease=scopes.enter_context(retirement_scope(self.settings,args['alias']))
            scopes.enter_context(self.registry_factory().operation_lock(args['alias']))
            with nullcontext():
                review,readback,current=self._observe(args,qualified,lease,read_guard,child_id=intent.operation_id)
                if review['resource_version']!=intent.resource_version or review['review_digest']!=args.get('_expected_review_digest'):
                    raise HTTPException(409,'Pending cleanup changed; review the exact current original again')
                registry=self.registry_factory();h=self.book.require_qualified(qualified);plan=h['plan'].payload['data']
                target=Path(self.settings.secrets_dir)/plan['target']['name'] if plan['target'] else None
                with registry._mutation_lock(),exclusive_state_lock(target) if target else nullcontext():
                    _,_,_,state=original_target_state(self.settings,self.registry_factory(),self.book,qualified)
                    if canonical_hash(state)!=review['view']['target_state_digest']:raise unknown()
                    current();readback();require_current_account_effect()
                    claim=journal.status(intent.operation_id,intent.device_id)
                    epoch=self.book.begin_child(qualified,claim,review_digest=review['review_digest'],
                        reauth_fact_digest=args['reauth_fact_digest'],retire_parent_safety_obligation=args['retire_parent_safety_obligation'])
                    def guarded(for_resolution=False):
                        self.book.require_epoch(qualified.operation_id,qualified.plan_ref,epoch,intent.operation_id)
                        if continuity(self.settings,self.registry_factory())!=plan['continuity']:raise unknown()
                        current();readback()
                        if not for_resolution:require_current_account_effect()
                        elif int(time.time())>=intent.expires_at_unix:raise HTTPException(403,'Original cleanup permission expired')
                        readback.check_time();lease.check_time()
                    def pure_final():
                        # No blocking work after the final time guard at the syscall.
                        readback.check_time();lease.check_time()
                        if int(time.time())>=intent.expires_at_unix:raise HTTPException(403,'Original cleanup permission expired')
                        mark_account_effect()
                    def step(name,state,**kw):
                        self.book.step(qualified.operation_id,qualified.plan_ref,epoch,intent.operation_id,name,state,**kw)
                    remaining=state['remaining_steps']
                    if 'REGISTRY_REMOVE' in remaining:
                        def before_remove():guarded();step('REGISTRY_REMOVE','MAY_BEGIN');guarded();pure_final()
                        def after_remove():step('REGISTRY_REMOVE','DONE',resource_version=plan['removed_resource_version'])
                        self.registry_factory().remove(args['alias'],before_replace=before_remove,after_replace=after_remove)
                    else:
                        old=h['steps'].get('REGISTRY_REMOVE')
                        if old is not None and old.payload['data']['state']=='MAY_BEGIN':
                            step('REGISTRY_REMOVE','VERIFIED_ABSENT',resource_version=plan['removed_resource_version'])
                    def credential_guard():
                        from vati.accounts.resource_version import resource_snapshot
                        if resource_snapshot(self.registry_factory(),args['alias'])['resource_version']!=plan['removed_resource_version']:raise unknown()
                        guarded()
                    if target is not None and target.exists():
                        if 'CREDENTIAL_OVERWRITE' not in remaining:
                            # An already overwritten secret cannot supply the required
                            # NEW native observation; _observe must have held this case.
                            raise unknown()
                        expected=tuple(plan['target']['generation'])
                        def before_write():credential_guard();step('CREDENTIAL_OVERWRITE','MAY_BEGIN');credential_guard()
                        def after_write(own):step('CREDENTIAL_OVERWRITE','DONE',post_generation=list(own),resource_version=plan['removed_resource_version'])
                        def before_unlink():credential_guard();step('CREDENTIAL_UNLINK','MAY_BEGIN');credential_guard()
                        def after_unlink():step('CREDENTIAL_UNLINK','DONE',resource_version=plan['removed_resource_version'])
                        _shred(target,before_write=before_write,before_unlink=before_unlink,expected_generation=expected,
                            before_effect=pure_final,after_write=after_write,after_unlink=after_unlink)
                    guarded()
                    _,_,_,post=original_target_state(self.settings,self.registry_factory(),self.book,qualified)
                    if post['remaining_steps']:raise unknown()
                    source=readback.source_fact;lease_fact=lease.scope_fact()
                    ref=self.book.postcondition(qualified,intent.operation_id,epoch,target_state_digest=canonical_hash(post),
                        native_review_ref=source['native_review_ref'],observed_at_ms=source['observed_at_ms'],
                        valid_until_ms=min(source['valid_until_ms'],lease_fact['expires_at_ms']),lease_epoch=lease_fact['lease_epoch'])
                    result={'alias':args['alias'],'removed':True,'cleanup_parent_operation_id':qualified.operation_id,
                        'plan_ref':qualified.plan_ref,'postcondition_ref':ref,'remote_account_closed':False,'historical_data_retained':True,
                        'retained_remote_funds':review['view']['retirement']['retained_remote_funds'],
                        'credential_cleanup':plan['credential_cleanup'],'parent_original_unchanged':True}
                    recovery.update(epoch=epoch,postcondition_ref=ref,target=target,guarded=guarded)
                    return result
        def classified_child_effect():
            from commander import account_effects as effects
            from commander.account_effects import AccountEffectError
            try:return child_effect()
            except AccountEffectError:
                marker=effects._effect_started.get()
                if marker is not None and marker[0] is False:
                    raise HTTPException(409,'Current original cleanup evidence is unavailable; no new local effect started') from None
                raise
        try:
            result=invoke_account_effect(journal,intent,classified_child_effect,dispatch_guard=read_guard,qualified_cleanup_parent=qualified)
            if args['retire_parent_safety_obligation'] and recovery:
                # Resolution is independent of the already committed local child.
                # Failure leaves the OLD safety fence held, never a false child
                # refusal or a second dispatch. Readback exposes that distinction.
                from commander.account_effects import AccountEffectError
                try:
                    registry=self.registry_factory();target=recovery['target']
                    with registry._mutation_lock(),exclusive_state_lock(target) if target else nullcontext():
                        recovery['guarded'](True)
                        _,_,_,post=original_target_state(self.settings,self.registry_factory(),self.book,qualified)
                        if post['remaining_steps']:raise unknown()
                        self.book.resolve(qualified,intent.operation_id,recovery['epoch'],recovery['postcondition_ref'])
                except (AccountEffectError,HTTPException,OSError):
                    confirmed=journal.status(intent.operation_id,intent.device_id)
                    if confirmed is None or confirmed.phase!='APPLIED' or confirmed.result!=result:raise
            return result
        finally:scopes.close()
