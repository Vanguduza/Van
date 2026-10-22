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


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class OAuthClaim:
    fresh: bool
    digest: str
    material: dict | None = field(repr=False)
    receipt: dict | None = field(repr=False)


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

    def _receipt(self, row):
        try:
            result = json.loads(self.cipher.decrypt(row['receipt_enc'].encode()))
            if (not isinstance(result,dict) or result.get('schema')!='van.oauth-effect-receipt/1'
                or any(result.get(key)!=row[key] for key in ('state','operation','request_digest','broker','owner_device_id'))
                or not isinstance(result.get('result'),dict)):
                raise ValueError('invalid or unbound receipt')
            return result['result']
        except Exception:
            raise OAuthEffectUnconfirmed('OAuth receipt cannot be read; native reconciliation required') from None

    async def begin(self,state,operation,broker,payload,*,owner_device_id=None,validate=None):
        if operation not in {'CALLBACK','LINK'} or broker not in {'deriv','ctrader'}:
            raise ValueError('invalid native OAuth operation')
        digest = fingerprint({'state':state,'operation':operation,'broker':broker,'payload':payload})
        async with self.store.connection() as db:
            await db.execute('BEGIN IMMEDIATE')
            cursor = await db.execute('SELECT * FROM trading_oauth_effects WHERE state=? AND operation=?',(state,operation))
            existing = await cursor.fetchone()
            if existing is not None:
                if owner_device_id is not None and existing['owner_device_id'] != owner_device_id:
                    raise HTTPException(403,'OAuth state belongs to another device')
                if existing['broker'] != broker or existing['request_digest'] != digest:
                    raise HTTPException(409,'OAuth operation conflicts with its original request')
                if existing['phase'] == 'APPLIED':
                    result = self._receipt(existing)
                    await db.commit()
                    return OAuthClaim(False,digest,None,result)
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
                cursor = await db.execute("SELECT state FROM trading_oauth_effects WHERE target_key=? AND phase IN ('IN_FLIGHT','UNKNOWN') LIMIT 1",(target,))
            else:
                cursor = await db.execute('SELECT state FROM trading_oauth_effects WHERE target_key=? LIMIT 1',(target,))
            if await cursor.fetchone() is not None:
                raise OAuthTargetBlocked('OAuth target has a prior effect requiring reconciliation; a new state cannot bypass it')
            now = int(time.time())
            await db.execute('''INSERT INTO trading_oauth_effects
                (state,operation,broker,owner_device_id,request_digest,target_key,phase,worker_id,created_at_unix,updated_at_unix)
                VALUES (?,?,?,?,?,?,'IN_FLIGHT',?,?,?)''',(state,operation,broker,owner,digest,target,self.worker,now,now))
            await db.commit()
        self.active.add((state,operation))
        return OAuthClaim(True,digest,pending,None)

    async def complete(self,state,operation,digest,receipt,*,patch=None,consume=False):
        if not isinstance(receipt,dict):
            raise ValueError("native OAuth completion requires a structured receipt")
        async with self.store.connection() as db:
            await db.execute('BEGIN IMMEDIATE')
            cursor = await db.execute('SELECT * FROM trading_oauth_effects WHERE state=? AND operation=?',(state,operation))
            row = await cursor.fetchone()
            if row is None or row['request_digest'] != digest or row['phase'] != 'IN_FLIGHT' or row['worker_id'] != self.worker:
                raise HTTPException(409,'OAuth claim is no longer owned by this worker')
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

    async def applied(self,state,operation,digest):
        row = await self.store.fetchone('SELECT * FROM trading_oauth_effects WHERE state=? AND operation=?',(state,operation))
        if row is not None and row['request_digest']==digest and row['phase']=='APPLIED':
            return self._receipt(row)
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

    async def unconfirmed(self,state,owner_device_id):
        row = await self.store.fetchone("""SELECT * FROM trading_oauth_effects WHERE state=?
            ORDER BY CASE operation WHEN 'LINK' THEN 1 ELSE 0 END DESC LIMIT 1""",(state,))
        if row is None:
            return None
        if row['owner_device_id'] != owner_device_id:
            raise HTTPException(403,'OAuth state belongs to another device')
        if row['phase'] == 'APPLIED':
            self._receipt(row)
            return None
        observed = (row['phase']=='IN_FLIGHT' and row['worker_id']==self.worker
                    and (state,row['operation']) in self.active)
        return {'ready':False,'operation':row['operation'],
                'status':'IN_PROGRESS' if observed else 'OUTCOME_UNCONFIRMED',
                'native_reconciliation_required':not observed}
