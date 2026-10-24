"""Resume consumed exact owner receipts after a gateway crash, never renew consent."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time

from fastapi import HTTPException

from van_gateway.trading.accounts import _trading_path
from van_gateway.trading.strategies import owner_authority_key_id
_trading_path()
from vati.app.runtime_control_protocol import RecoveryIntent, RecoveryProof

LOG = logging.getLogger(__name__)
RECEIPT_PREFIX = 'owner_approval_receipt:'
DELIVERED_PREFIX = 'runtime_recovery_delivered:'
CURSOR = 'runtime_recovery_dispatch_cursor_v1'


class RuntimeRecoveryDispatcher:
    def __init__(self, *, store, auth, promotions):
        self.store, self.auth, self.promotions = store, auth, promotions
        self._lock = asyncio.Lock()

    async def _run(self, name, args):
        if self.promotions.control is None:
            raise HTTPException(503, 'native runtime recovery dispatcher unavailable')
        return await asyncio.to_thread(self.promotions.control.run, name, args)

    async def _deliver(self, key, saved):
        from van_gateway.trading.runtime_controls import RuntimeRecoveryOperation
        if not isinstance(saved, dict) or not isinstance(saved.get('context'), dict):
            raise ValueError('original recovery receipt is unreadable')
        context = saved['context']
        if set(context) != {'intent','proof'}:
            return False  # Another owner-approval domain does not belong to this outbox.
        intent = RecoveryIntent.from_mapping(context['intent'])
        proof = RecoveryProof.from_mapping(context['proof'])
        if (key != RECEIPT_PREFIX+proof.operation_id or saved.get('operation_id') != proof.operation_id
            or saved.get('device_id') != intent.device_id or saved.get('intent_digest') != intent.intent_digest
            or type(saved.get('expires_at_unix')) is not int or saved['expires_at_unix'] != proof.expires_at_unix):
            raise ValueError('original recovery receipt identity differs')
        owner = await self.auth.require_device(intent.device_id)
        if owner_authority_key_id(owner.public_key_pem) != proof.key_id:
            raise ValueError('original owner device key changed')
        # Authentication of this immutable receipt is not current authority.
        # Native enqueue checks its own clock and records expired originals as
        # terminal no-effect refusals. It never extends an approval's lifetime.
        proof.verify_signature(intent, {proof.key_id:owner.public_key_pem})
        try:
            result = await self._run('runtime_recovery_operation',
                {'operation_id':proof.operation_id,'device_id':intent.device_id})
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            await asyncio.to_thread(self.promotions.ensure_owner_authority,
                device_id=intent.device_id, public_key_pem=owner.public_key_pem)
            # Recheck after a possibly slow enrollment, immediately before IO.
            current = await self.auth.require_device(intent.device_id)
            if current.public_key_pem != owner.public_key_pem:
                raise ValueError('original owner device key changed during dispatch')
            result = await self._run('runtime_recovery_request', context)
        native = RuntimeRecoveryOperation.model_validate(result)
        if (native.operation_id != proof.operation_id or native.intent.model_dump(by_alias=True) != intent.body()
            or native.expires_at_unix != proof.expires_at_unix
            or native.authority_ref != proof.verify_signature(intent,{proof.key_id:owner.public_key_pem})
            or not re.fullmatch('[0-9a-f]{64}',native.native_event_ref)
            or (native.phase == 'REQUESTED') != (native.result is None)):
            raise ValueError('native original recovery receipt differs')
        value = json.dumps({'schema':'van.runtime-recovery-delivery/1','operation_id':proof.operation_id,
            'native_event_ref':native.native_event_ref,'phase':native.phase},sort_keys=True,separators=(',',':'))
        await self.store.execute('INSERT OR REPLACE INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)',
            (DELIVERED_PREFIX+proof.operation_id,value,int(time.time()*1000)))
        return True

    async def reconcile_once(self, *, limit=50):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('runtime recovery dispatch batch must be bounded')
        async with self._lock:
            cursor = await self.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(CURSOR,))
            after = cursor['value'] if cursor else ''
            query = '''SELECT r.key,r.value FROM runtime_meta r
                LEFT JOIN runtime_meta d ON d.key = ? || substr(r.key, ?)
                WHERE r.key GLOB ? AND d.key IS NULL AND r.key > ? ORDER BY r.key LIMIT ?'''
            args = (DELIVERED_PREFIX,len(RECEIPT_PREFIX)+1,RECEIPT_PREFIX+'*',after,limit)
            rows = await self.store.fetchall(query,args)
            if not rows and after:
                rows = await self.store.fetchall(query,args[:3]+('',limit))
            report = {'examined':len(rows),'delivered':0,'deferred':0,'other_domains':0}
            for row in rows:
                try:
                    done = await self._deliver(row['key'],json.loads(row['value']))
                    report['delivered' if done else 'other_domains'] += 1
                except Exception:
                    # Durable receipt remains intact. Never label uncertain IO
                    # failed/no-effect and never leak proofs into logs.
                    report['deferred'] += 1
                await self.store.execute('INSERT OR REPLACE INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)',
                    (CURSOR,row['key'],int(time.time()*1000)))
            return report

    async def run(self):
        while True:
            try:
                report = await self.reconcile_once()
                if report['deferred']:
                    LOG.warning('runtime recovery dispatch deferred for %d original receipts', report['deferred'])
            except Exception:
                LOG.warning('runtime recovery dispatch unavailable; original receipts retained')
            await asyncio.sleep(5)
