import test from 'node:test';
import assert from 'node:assert/strict';
import {Admission} from './admission.mjs';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

test('global and subject caps hold while requests wait without executing',async()=>{
  const g=new Admission({global:2,perSubject:1,pending:4,pendingPerSubject:2,waitMs:200});
  const a=await g.acquire('a'),b=await g.acquire('b');let admitted=false;
  const waiting=g.acquire('a').then(release=>{admitted=true;return release;});
  await sleep(10);assert.equal(admitted,false);assert.equal(g.active,2);
  a();const done=await waiting;assert.equal(g.active,2);done();b();assert.equal(g.active,0);
});
test('another subject is not blocked by a queued request from a busy subject',async()=>{
  const g=new Admission({global:2,perSubject:1,pending:4,pendingPerSubject:2,waitMs:200});
  const a=await g.acquire('a');const queued=g.acquire('a');const b=await g.acquire('b');
  assert.equal(g.active,2);b();assert.equal(g.active,1);a();const release=await queued;release();assert.equal(g.active,0);
});
test('pending bound refuses excess work rather than executing it',async()=>{
  const g=new Admission({global:1,perSubject:1,pending:1,pendingPerSubject:1,waitMs:200});
  const first=await g.acquire('a');const waiting=g.acquire('a');
  await assert.rejects(g.acquire('b'),/CAPACITY_BUSY/);assert.equal(g.queue.length,1);
  first();(await waiting)();assert.equal(g.active,0);
});
test('expired queue entry cannot later execute',async()=>{
  const g=new Admission({global:1,perSubject:1,pending:1,pendingPerSubject:1,waitMs:15});
  const release=await g.acquire('a');await assert.rejects(g.acquire('b'),/CAPACITY_BUSY/);
  assert.equal(g.queue.length,0);assert.equal(g.active,1);release();assert.equal(g.active,0);
});
test('cancelled pending request is removed without consuming authority',async()=>{
  const g=new Admission();const first=await g.acquire('a'),second=await g.acquire('a');
  const abort=new AbortController();const pending=g.acquire('a',abort.signal);
  abort.abort();await assert.rejects(pending,/REQUEST_ABORTED/);assert.equal(g.queue.length,0);
  first();second();assert.equal(g.active,0);
});
test('active disconnect does not release original work prematurely',async()=>{
  const g=new Admission({global:1,perSubject:1,pending:1,pendingPerSubject:1,waitMs:200});
  const abort=new AbortController();const release=await g.acquire('a',abort.signal);abort.abort();
  assert.equal(g.active,1);const waiting=g.acquire('b');release();(await waiting)();assert.equal(g.active,0);
});
test('release is idempotent and cannot create extra slots',async()=>{
  const g=new Admission();const release=await g.acquire('a');release();release();
  assert.equal(g.active,0);assert.equal(g.bySubject.size,0);
});
test('invalid limits and already-aborted requests fail closed',async()=>{
  for(const global of [0,-1,1.5,NaN])assert.throws(()=>new Admission({global}),/INVALID_LIMIT/);
  const g=new Admission();const aborted=new AbortController();aborted.abort();
  await assert.rejects(g.acquire('a',aborted.signal),/REQUEST_ABORTED/);
  await assert.rejects(g.acquire(''),/INVALID_SUBJECT/);assert.equal(g.active,0);
});
