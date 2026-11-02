"""Durable OAuth callback/link claims in the gateway's existing encrypted store.

A committed claim precedes an external call. An unconfirmed claim is never
replayed by lease expiry, a process restart, a different state or a lost reply.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
import secrets
import time

from fastapi import HTTPException


class OAuthEffectUnconfirmed(HTTPException):
    effect_state = "UNKNOWN"
    reconciliation_required = True

    def __init__(self,detail="OAuth effect is unconfirmed; native reconciliation required"):
        super().__init__(409,detail)


class OAuthTargetBlocked(HTTPException):
    effect_state = "REFUSED"
    reconciliation_required = True

    def __init__(self,detail="Prior OAuth target effect requires native reconciliation"):
        super().__init__(409,detail)


RESUME_SELECTORS=frozenset({'original_operation_id','original_approval_expires_at_unix',
    'original_resource_version','original_issued_at_unix','original_account_control_domain'})


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class OAuthClaim:
    fresh: bool
    digest: str
    material: dict | None = field(repr=False)
    receipt: dict | None = field(repr=False)
    binding: dict | None = field(default=None,repr=False)


class OAuthEffects:
    def __init__(self, store, cipher, decode_pending):
        self.store, self.cipher, self.decode_pending = store, cipher, decode_pending
        self.worker = secrets.token_hex(16)
        self.fault = None
        self.active = set()

    async def migrate(self):
        await self.store.execute('''CREATE TABLE IF NOT EXISTS trading_oauth_effects (
            state TEXT NOT NULL, operation TEXT NOT NULL CHECK(operation IN ('CALLBACK','LINK')),
            broker TEXT NOT NULL, owner_device_id TEXT NOT NULL, request_digest TEXT NOT NULL,
            target_key TEXT NOT NULL, phase TEXT NOT NULL CHECK(phase IN ('IN_FLIGHT','APPLIED','UNKNOWN')),
            worker_id TEXT NOT NULL, receipt_enc TEXT, error_code TEXT,
            created_at_unix INTEGER NOT NULL, updated_at_unix INTEGER NOT NULL,
            PRIMARY KEY(state,operation))''')
        await self.store.execute('CREATE INDEX IF NOT EXISTS idx_trading_oauth_effect_target ON trading_oauth_effects(target_key,phase)')

    def _link_envelope(self, row):
        """Existing encrypted column holds typed intent until actual completion.

        INTENT is not a receipt, APPLIED, or authority. Legacy rows have no
        provable original native scope and must never be adopted into one.
        """
        try:
            value=json.loads(self.cipher.decrypt(row['receipt_enc'].encode()))
            binding=value['native_binding']
            keys={'schema','record_type','state','operation','request_digest','broker','owner_device_id','native_binding'}
            if (value.get('schema')!='van.oauth-link-binding/1'
                or set(value)!=(keys|{'result'} if row['phase']=='APPLIED' else keys)
                or value.get('record_type')!=('RECEIPT' if row['phase']=='APPLIED' else 'INTENT')
                or any(value.get(key)!=row[key] for key in ('state','operation','request_digest','broker','owner_device_id'))
                or not isinstance(binding,dict)
                or not {'account_control_domain','resource_version','operation_id','device_id','expires_at_unix'}<=set(binding)
                or set(binding)-{'account_control_domain','resource_version','operation_id','device_id','expires_at_unix',
                    'approval_operation_id','original_expires_at_unix'}
                or binding['device_id']!=row['owner_device_id']
                or any(not isinstance(binding.get(key),str) or not re.fullmatch(r'[0-9a-f]{64}',binding[key])
                    for key in ('account_control_domain','resource_version'))
                or not isinstance(binding['operation_id'],str)
                or not re.fullmatch(r'[A-Za-z0-9_-]{20,128}',binding['operation_id'])
                or type(binding['expires_at_unix']) is not int or binding['expires_at_unix']<=0
                or ('original_expires_at_unix' in binding and (type(binding['original_expires_at_unix']) is not int or binding['original_expires_at_unix']<=0))
                or ('approval_operation_id' in binding and (not isinstance(binding['approval_operation_id'],str)
                    or not re.fullmatch(r'[A-Za-z0-9_-]{20,128}',binding['approval_operation_id'])))
                or row['operation']!='LINK'):
                raise ValueError('unbound original link')
            return value
        except Exception:
            raise OAuthEffectUnconfirmed('Original OAuth link has no verifiable native scope; retain it unbound for reconciliation') from None

    @staticmethod
    def _same_scope(original, expected):
        if expected is None or any(original.get(key)!=expected.get(key)
            for key in ('account_control_domain','resource_version','device_id')):
            raise OAuthTargetBlocked('Original OAuth link belongs to another native scope or version; do not rebind it')

    @staticmethod
    def _link_result(value,row):
        from van_gateway.trading.account_contracts import PublicAccountRecord
        binding=value['native_binding'];result=value.get('result')
        try:
            if not isinstance(result,dict) or set(result)!={'account','account_control_domain','operation_id','device_id',
                'action','oauth_state','native_resource_version','effect_state','reconciliation_required'}:
                raise ValueError('unexpected native link receipt fields')
            account=PublicAccountRecord.model_validate(result['account'])
            if (any(result.get(key)!=binding[bound] for key,bound in (
                    ('account_control_domain','account_control_domain'),('operation_id','operation_id'),
                    ('device_id','device_id'),('native_resource_version','resource_version')))
                or result['action']!=('deriv_oauth_link' if row['broker']=='deriv' else 'ctrader_link')
                or result['oauth_state']!=row['state'] or result['effect_state']!='APPLIED'
                or result['reconciliation_required'] is not False
                or row['target_key']!='account:'+account.alias or account.broker!=row['broker'].upper()
                or account.mode not in {'DEMO_TRADER','OBSERVE'} or not account.login or not account.currency):
                raise ValueError('mismatched original link receipt')
        except Exception:
            raise OAuthEffectUnconfirmed('Original link receipt is incomplete or differs from its sealed intent') from None
        return result

    def _receipt(self, row, *, native_binding=None):
        if row['operation']=='LINK':
            value=self._link_envelope(row)
            self._same_scope(value['native_binding'],native_binding)
            if row['phase']!='APPLIED' or not isinstance(value.get('result'),dict):
                raise OAuthEffectUnconfirmed()
            return self._link_result(value,row)
        try:
            result = json.loads(self.cipher.decrypt(row['receipt_enc'].encode()))
            if (not isinstance(result,dict) or result.get('schema')!='van.oauth-effect-receipt/1'
                or any(result.get(key)!=row[key] for key in ('state','operation','request_digest','broker','owner_device_id'))
                or not isinstance(result.get('result'),dict)):
                raise ValueError('invalid or unbound receipt')
            return result['result']
        except Exception:
            raise OAuthEffectUnconfirmed('OAuth receipt cannot be read; native reconciliation required') from None

    async def link_binding(self,state,broker,owner_device_id,account_control_domain):
        row=await self.store.fetchone("SELECT * FROM trading_oauth_effects WHERE state=? AND operation='LINK'",(state,))
        if row is None:return None
        if not owner_device_id or row['owner_device_id']!=owner_device_id:
            raise HTTPException(403,'OAuth state belongs to another device')
        if row['broker']!=broker:raise HTTPException(400,'OAuth state belongs to a different broker')
        binding=self._link_envelope(row)['native_binding']
        if binding['account_control_domain']!=account_control_domain:
            raise OAuthTargetBlocked('Original OAuth link native namespace is not selected')
        return binding

    async def link_record(self,state,owner_device_id):
        row=await self.store.fetchone("SELECT * FROM trading_oauth_effects WHERE state=? AND operation='LINK'",(state,))
        if row is None:return None
        if not owner_device_id or row['owner_device_id']!=owner_device_id:
            raise HTTPException(403,'OAuth state belongs to another device')
        try:self._link_envelope(row)
        except OAuthEffectUnconfirmed:
            # Preserve genuinely recorded old completion as historical data;
            # it is never original native-scope proof or an executable grant.
            if row['phase']=='APPLIED':
                try:
                    value=json.loads(self.cipher.decrypt(row['receipt_enc'].encode()))
                    if (value.get('schema')!='van.oauth-effect-receipt/1'
                        or any(value.get(k)!=row[k] for k in ('state','operation','request_digest','broker','owner_device_id'))
                        or not isinstance(value.get('result'),dict)):raise ValueError()
                except Exception:raise OAuthEffectUnconfirmed('Historical link confirmation cannot be verified') from None
            return {'legacy_unbound':True,'status':'RECORDED_APPLIED_UNBOUND' if row['phase']=='APPLIED' else 'OUTCOME_UNCONFIRMED'}
        return dict(row)

    async def require_original_semantics(self,state,broker,owner_device_id,domain,payload):
        binding=await self.link_binding(state,broker,owner_device_id,domain)
        if binding is None:raise OAuthEffectUnconfirmed('Original link intent is unavailable')
        row=await self.store.fetchone("SELECT request_digest FROM trading_oauth_effects WHERE state=? AND operation='LINK'",(state,))
        semantic={k:v for k,v in payload.items() if k not in RESUME_SELECTORS}
        expected=fingerprint({'state':state,'operation':'LINK','broker':broker,'payload':semantic})
        if row is None or row['request_digest']!=expected:
            raise OAuthTargetBlocked('Original link semantic arguments differ; use a new reviewed operation')
        return binding

    async def lifecycle_plan(self,alias,device,domain,*,db=None):
        """Exact immutable LINK producer relation; no broker/device-wide purge.

        Unselected OAuth attempts have no alias and are not guessed into scope.
        Any ambiguous/unknown original on this target holds deletion.
        """
        async def read(conn):
            rows=await (await conn.execute("SELECT * FROM trading_oauth_effects WHERE operation='LINK' AND target_key=? ORDER BY state",('account:'+alias,))).fetchall()
            facts=[]
            for row in rows:
                envelope=self._link_envelope(row);binding=envelope['native_binding']
                if binding['account_control_domain']!=domain:continue
                if row['owner_device_id']!=device:raise OAuthTargetBlocked('Another owner original link exists; HOLD')
                if row['phase']!='APPLIED':raise OAuthEffectUnconfirmed('Original link requires reconciliation before account deletion')
                self._link_result(envelope,row)
                facts.append({'state':row['state'],'broker':row['broker'],'request_digest':row['request_digest'],
                    'operation_id':binding['operation_id'],'resource_version':binding['resource_version']})
            return {'schema':'van.account-oauth-discard-plan/1','alias':alias,'device_id':device,
                'account_control_domain':domain,'links':facts,'unselected_attempts':'NOT_ACCOUNT_ASSOCIATED_NOT_DISCARDED'}
        if db is not None:return await read(db)
        async with self.store.connection() as conn:
            await conn.execute('BEGIN')
            try:return await read(conn)
            finally:await conn.rollback()

    async def lifecycle_discard(self,alias,device,domain,expected):
        async with self.store.connection() as db:
            await db.execute('BEGIN IMMEDIATE')
            try:
                plan=await self.lifecycle_plan(alias,device,domain,db=db)
                if fingerprint(plan)!=expected:raise OAuthTargetBlocked('OAuth deletion scope changed since review')
                for item in plan['links']:
                    state=item['state']
                    # Keep original journal and immutable native binding. This
                    # tombstone fences a delayed callback/material completion.
                    key='account_lifecycle_oauth_discard:'+state
                    value={'schema':'van.account-oauth-discard/1','plan_digest':expected,**item,
                        'alias':alias,'device_id':device,'account_control_domain':domain}
                    old=await (await db.execute('SELECT value FROM runtime_meta WHERE key=?',(key,))).fetchone()
                    if old is not None and json.loads(old['value'])!=value:raise OAuthTargetBlocked('Original discard binding changed')
                    await db.execute('INSERT OR IGNORE INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)',
                        (key,json.dumps(value,sort_keys=True,separators=(',',':')),int(time.time()*1000)))
                    await db.execute('DELETE FROM trading_oauth_pending WHERE state=?',(state,))
                await db.commit()
                return expected
            except BaseException:await db.rollback();raise

    async def begin(self,state,operation,broker,payload,*,owner_device_id=None,validate=None,native_binding=None):
        if operation not in {'CALLBACK','LINK'} or broker not in {'deriv','ctrader'}:
            raise ValueError('invalid native OAuth operation')
        # A fresh A4 permission signs the entire submitted body, including
        # resume selectors. They do not change the original business effect.
        semantic_payload=({k:v for k,v in payload.items() if k not in RESUME_SELECTORS} if operation=='LINK' else payload)
        digest = fingerprint({'state':state,'operation':operation,'broker':broker,'payload':semantic_payload})
        async with self.store.connection() as db:
            await db.execute('BEGIN IMMEDIATE')
            if await (await db.execute('SELECT key FROM runtime_meta WHERE key=?',('account_lifecycle_oauth_discard:'+state,))).fetchone():
                raise OAuthTargetBlocked('Original authorization was discarded by account lifecycle')
            cursor = await db.execute('SELECT * FROM trading_oauth_effects WHERE state=? AND operation=?',(state,operation))
            existing = await cursor.fetchone()
            if existing is not None:
                if owner_device_id is not None and existing['owner_device_id'] != owner_device_id:
                    raise HTTPException(403,'OAuth state belongs to another device')
                if existing['broker'] != broker or existing['request_digest'] != digest:
                    raise HTTPException(409,'OAuth operation conflicts with its original request')
                original=self._link_envelope(existing)['native_binding'] if operation=='LINK' else None
                if operation=='LINK':self._same_scope(original,native_binding)
                if operation=='LINK' and 'original_operation_id' in payload and (
                    payload['original_operation_id']!=original['operation_id'] or
                    payload.get('original_approval_expires_at_unix')!=original.get('original_expires_at_unix',original['expires_at_unix']) or
                    payload.get('original_resource_version')!=original['resource_version'] or
                    payload.get('original_account_control_domain')!=original['account_control_domain']):
                    raise OAuthTargetBlocked('Resume identity changed before original link arbitration')
                if existing['phase'] == 'APPLIED':
                    result = self._receipt(existing,native_binding=native_binding)
                    await db.commit()
                    return OAuthClaim(False,digest,None,result,original)
                raise OAuthEffectUnconfirmed('OAuth operation outcome is unconfirmed; native reconciliation required before retry')
            cursor = await db.execute('SELECT * FROM trading_oauth_pending WHERE state=?',(state,))
            pending = self.decode_pending(await cursor.fetchone())
            if pending is None or pending.get('broker') != broker:
                raise HTTPException(400 if operation=='CALLBACK' else 404,'unknown, expired or wrong-broker OAuth state')
            owner = pending.get('_owner_device_id')
            if not isinstance(owner,str) or not owner or (owner_device_id is not None and owner_device_id != owner):
                raise HTTPException(400 if operation=='CALLBACK' else 403,'OAuth state has no matching authenticated device owner')
            if operation == 'CALLBACK':
                if pending.get('ready'):
                    raise HTTPException(409,'OAuth result predates durable callback identity; do not repeat the token exchange')
                if broker == 'ctrader':
                    target = 'code:'+fingerprint({'broker':broker,'client_id':pending.get('client_id'),'code':payload.get('code')})
                else:
                    target = 'callback:'+state
            else:
                if not pending.get('ready'):
                    raise HTTPException(404,'OAuth authorization is incomplete')
                alias = str(payload.get('alias','')).strip().lower()
                if not re.fullmatch(r'[a-z0-9_]{3,32}',alias):
                    raise HTTPException(422,'alias must match [a-z0-9_]{3,32}')
                target = 'account:'+alias
            if validate is not None:
                validate(pending)
            if operation == 'LINK':
                if (not isinstance(native_binding,dict) or native_binding.get('device_id')!=owner
                    or type(native_binding.get('expires_at_unix')) is not int
                    or native_binding['expires_at_unix']<=int(time.time())):
                    raise HTTPException(403,'Current verified original link admission is required')
                cursor=await db.execute("SELECT * FROM trading_oauth_effects WHERE target_key=? AND phase IN ('IN_FLIGHT','UNKNOWN')",(target,))
                for prior in await cursor.fetchall():
                    try: prior_domain=self._link_envelope(prior)['native_binding']['account_control_domain']
                    except OAuthEffectUnconfirmed: prior_domain=None
                    if prior_domain in (None,native_binding.get('account_control_domain')):
                        raise OAuthTargetBlocked('OAuth target has a prior effect requiring reconciliation; a new state cannot bypass it')
                cursor=None
            else:
                cursor = await db.execute('SELECT state FROM trading_oauth_effects WHERE target_key=? LIMIT 1',(target,))
            if cursor is not None and await cursor.fetchone() is not None:
                raise OAuthTargetBlocked('OAuth target has a prior effect requiring reconciliation; a new state cannot bypass it')
            now = int(time.time())
            await db.execute('''INSERT INTO trading_oauth_effects
                (state,operation,broker,owner_device_id,request_digest,target_key,phase,worker_id,created_at_unix,updated_at_unix)
                VALUES (?,?,?,?,?,?,'IN_FLIGHT',?,?,?)''',(state,operation,broker,owner,digest,target,self.worker,now,now))
            if operation=='LINK':
                envelope={'schema':'van.oauth-link-binding/1','record_type':'INTENT','state':state,
                    'operation':operation,'request_digest':digest,'broker':broker,'owner_device_id':owner,
                    'native_binding':native_binding}
                # Validate the exact persisted format before its first claim.
                encrypted_intent=self.cipher.encrypt(json.dumps(envelope).encode()).decode()
                self._link_envelope({**envelope,'phase':'IN_FLIGHT','receipt_enc':encrypted_intent})
                await db.execute("UPDATE trading_oauth_effects SET receipt_enc=? WHERE state=? AND operation=?",
                    (encrypted_intent,state,operation))
            await db.commit()
        self.active.add((state,operation))
        return OAuthClaim(True,digest,pending,None,native_binding)

    async def complete(self,state,operation,digest,receipt,*,patch=None,consume=False):
        if not isinstance(receipt,dict):
            raise ValueError("native OAuth completion requires a structured receipt")
        async with self.store.connection() as db:
            await db.execute('BEGIN IMMEDIATE')
            cursor = await db.execute('SELECT * FROM trading_oauth_effects WHERE state=? AND operation=?',(state,operation))
            row = await cursor.fetchone()
            if row is None or row['request_digest'] != digest or row['phase'] != 'IN_FLIGHT' or row['worker_id'] != self.worker:
                raise HTTPException(409,'OAuth claim is no longer owned by this worker')
            if await (await db.execute('SELECT key FROM runtime_meta WHERE key=?',('account_lifecycle_oauth_discard:'+state,))).fetchone():
                raise OAuthTargetBlocked('Original authorization was discarded; material cannot return')
            if patch is not None:
                if {'broker','_owner_device_id','_state','_broker','_created_at_unix'} & patch.keys():
                    raise ValueError('OAuth completion cannot change its owner or broker')
                cursor = await db.execute('SELECT * FROM trading_oauth_pending WHERE state=?',(state,))
                pending = self.decode_pending(await cursor.fetchone())
                if pending is None:
                    raise HTTPException(409,'OAuth material expired while its external effect was in flight')
                pending.pop('broker',None)
                value = self.cipher.encrypt(json.dumps({**pending,**patch}).encode()).decode()
                await db.execute('UPDATE trading_oauth_pending SET payload_enc=? WHERE state=?',(value,state))
            if consume:
                await db.execute('DELETE FROM trading_oauth_pending WHERE state=?',(state,))
            if self.fault:
                self.fault('after_material_before_receipt')
            envelope = {'schema':'van.oauth-effect-receipt/1',
                **{key:row[key] for key in ('state','operation','request_digest','broker','owner_device_id')},'result':receipt}
            if operation=='LINK':
                original=self._link_envelope(row)
                envelope={**original,'record_type':'RECEIPT','result':receipt}
                self._link_result(envelope,row)
            encrypted = self.cipher.encrypt(json.dumps(envelope).encode()).decode()
            await db.execute("UPDATE trading_oauth_effects SET phase='APPLIED',receipt_enc=?,updated_at_unix=? WHERE state=? AND operation=?",(encrypted,int(time.time()),state,operation))
            if self.fault:
                self.fault('after_receipt_before_commit')
            await db.commit()
        self.active.discard((state,operation))
        if self.fault:
            self.fault('after_commit_before_reply')

    async def uncertain(self,state,operation,digest,error_code):
        try:
            await self.store.execute("""UPDATE trading_oauth_effects SET phase='UNKNOWN',error_code=?,updated_at_unix=?
                WHERE state=? AND operation=? AND request_digest=? AND worker_id=? AND phase='IN_FLIGHT'""",
                (error_code[:100],int(time.time()),state,operation,digest,self.worker))
        finally:
            self.active.discard((state,operation))

    async def applied(self,state,operation,digest,*,native_binding=None):
        row = await self.store.fetchone('SELECT * FROM trading_oauth_effects WHERE state=? AND operation=?',(state,operation))
        if row is not None and row['request_digest']==digest and row['phase']=='APPLIED':
            return self._receipt(row,native_binding=native_binding)
        return None

    async def owns_link(self, state, broker, owner_device_id):
        """Read historical ownership without claiming, replaying or decoding a result.

        Completed links consume pending material. Their original result must
        remain reachable; begin() still verifies the exact request and encrypted
        receipt after owner approval, and never starts another effect for a row.
        """
        row = await self.store.fetchone(
            "SELECT owner_device_id,broker FROM trading_oauth_effects WHERE state=? AND operation='LINK'", (state,))
        if row is None:
            return False
        if not owner_device_id or row['owner_device_id'] != owner_device_id:
            raise HTTPException(403, 'OAuth state belongs to another device')
        if row['broker'] != broker:
            raise HTTPException(400, 'OAuth state belongs to a different broker')
        return True

    async def unresolved_link_target(self, alias,account_control_domain=None):
        """Read uncertainty before classifying an alias as a new-link collision.

        This grants no execution: begin() still arbitrates the exact request,
        original actor and global target in its existing atomic transaction.
        """
        rows=await self.store.fetchall("""SELECT * FROM trading_oauth_effects
            WHERE operation='LINK' AND target_key=? AND phase IN ('IN_FLIGHT','UNKNOWN')""",('account:'+alias,))
        for row in rows:
            try: domain=self._link_envelope(row)['native_binding']['account_control_domain']
            except OAuthEffectUnconfirmed:return True
            if account_control_domain is None or domain==account_control_domain:return True
        return False

    async def unconfirmed(self,state,owner_device_id,*,account_control_domain=None):
        row = await self.store.fetchone("""SELECT * FROM trading_oauth_effects WHERE state=?
            ORDER BY CASE operation WHEN 'LINK' THEN 1 ELSE 0 END DESC LIMIT 1""",(state,))
        if row is None:
            return None
        if row['owner_device_id'] != owner_device_id:
            raise HTTPException(403,'OAuth state belongs to another device')
        binding=None
        if row['operation']=='LINK':
            binding=self._link_envelope(row)['native_binding']
            if binding['account_control_domain']!=account_control_domain:
                raise OAuthTargetBlocked('Original OAuth link native namespace is not selected')
        if row['phase'] == 'APPLIED':
            self._receipt(row,native_binding=binding)
            return None
        observed = (row['phase']=='IN_FLIGHT' and row['worker_id']==self.worker
                    and (state,row['operation']) in self.active)
        result={'ready':False,'operation':row['operation'],
                'status':'IN_PROGRESS' if observed else 'OUTCOME_UNCONFIRMED',
                'native_reconciliation_required':not observed}
        if binding:
            result.update(operation_id=binding['operation_id'],device_id=binding['device_id'],
                action='deriv_oauth_link' if row['broker']=='deriv' else 'ctrader_link',oauth_state=state,
                account_control_domain=binding['account_control_domain'],native_resource_version=binding['resource_version'],
                effect_state='UNKNOWN',reconciliation_required=True)
        return result
