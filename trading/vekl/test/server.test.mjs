import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { VeklService, registryFingerprint, startServer } from '../server.mjs';

const home = fs.mkdtempSync(path.join(os.tmpdir(), 'vekl-test-'));

test('dedicated trading VEKL resolves the golden packet with deterministic activation ids and persists them', async () => {
  const svc = await new VeklService({ home }).init();
  const h = svc.health();
  assert.equal(h.ok, true);
  assert.equal(h.resolver_provenance.donor_commit, 'fa7c655f12faf02a2b33cc15799069526bdda3a6');
  assert.equal(h.resolver_provenance.files, 5);
  const req = { instruction: 'Implement MT5 order_send with an atomic protective stop inside a Nautilus ExecutionClient, using symbol_info volume_step and stops level.', affected_paths: ['trading/vati/execution/mt5/execution.py'], requested_by: 'test' };
  const a = svc.resolve(req);
  const b = svc.resolve(req);
  assert.equal(a.activation_id, b.activation_id, 'same packet → same activation id');
  assert.match(a.activation_id, /^vtil-act-[0-9a-f]{24}$/);
  for (const id of ['van.trading.rules.rev2-canon', 'ref.metaquotes.mt5-python', 'ref.nautilus.docs']) assert.ok(a.selected.includes(id), `missing ${id}`);
  assert.ok(!a.selected.includes('ref.deriv.api'));
  assert.equal(a.registry_sha256, registryFingerprint().sha256);
  assert.deepEqual(svc.activation(a.activation_id).selected, a.selected);
  assert.equal(svc.activation('vtil-act-nope'), null);
  const other = svc.resolve({ ...req, instruction: 'Size a Deriv synthetic index Rise/Fall contract by stake and reconcile open contracts after reconnect.' });
  assert.notEqual(other.activation_id, a.activation_id);
  assert.throws(() => svc.resolve({ instruction: '' }), /instruction/);
});

test('HTTP surface: health, validate, resolve, activation lookup, token gate', async () => {
  const { server, port } = await startServer({ port: 0, token: 'secret-token', service: await new VeklService({ home }).init() });
  try {
    const base = `http://127.0.0.1:${port}`;
    const health = await (await fetch(`${base}/health`)).json();
    assert.equal(health.ok, true);
    assert.equal((await fetch(`${base}/registry/validate`)).status, 401, 'token required beyond /health');
    const auth = { authorization: 'Bearer secret-token', 'content-type': 'application/json' };
    const v = await (await fetch(`${base}/registry/validate`, { headers: auth })).json();
    assert.equal(v.ok, true);
    const r = await fetch(`${base}/resolve`, { method: 'POST', headers: auth, body: JSON.stringify({ instruction: 'Study Delta Corporation on the Zimbabwe Stock Exchange: ZiG parallel premium regime, board lot sizing, T+3 settlement, transaction costs and exchange control for a swing position.', affected_paths: ['trading/vati/zse/market.py'] }) });
    const rec = await r.json();
    assert.equal(r.status, 200);
    assert.ok(rec.selected.includes('ref.zse.trading-procedures'));
    const again = await (await fetch(`${base}/activation/${rec.activation_id}`, { headers: auth })).json();
    assert.equal(again.activation_id, rec.activation_id);
    assert.equal((await fetch(`${base}/activation/nope`, { headers: auth })).status, 404);
    assert.equal((await fetch(`${base}/resolve`, { method: 'POST', headers: auth, body: '{}' })).status, 400);
  } finally {
    server.close();
  }
});

test('a modified vendored resolver file is refused', async () => {
  const vendor = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../vendor/dial');
  const target = path.join(vendor, 'state-store.mjs');
  const original = fs.readFileSync(target);
  fs.writeFileSync(target, Buffer.concat([original, Buffer.from('\n// tamper\n')]));
  try {
    await assert.rejects(() => new VeklService({ home: fs.mkdtempSync(path.join(os.tmpdir(), 'vekl-t2-')) }).init(), /PROVENANCE/);
  } finally {
    fs.writeFileSync(target, original);
  }
});
