import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const TRADING = path.resolve(here, '../..');
const TOKEN = 'k'.repeat(40);
const VAN_VENV_PYTHON = path.join(os.homedir(), '.local', 'share', 'van', 'venv', 'bin', 'python');
const PYTHON = process.env.VAN_TEST_PYTHON || process.env.PYTHON || (fs.existsSync(VAN_VENV_PYTHON) ? VAN_VENV_PYTHON : 'python3');

function freePort() { return new Promise((r) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => r(p)); }); }); }
async function waitHealth(url, ms = 20000) { const t0 = Date.now(); while (Date.now() - t0 < ms) { try { const r = await fetch(url + '/health'); if (r.ok) return; } catch {} await new Promise((r) => setTimeout(r, 200)); } throw new Error('commander did not start'); }

test('MCP stdio shim exposes only the commander tool list and forwards signed calls', async () => {
  const port = await freePort();
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'cmd-'));
  fs.mkdirSync(path.join(tmp, 'hb'));
  const py = spawn(PYTHON, ['-c', `
import os, uvicorn
from commander.app import CommanderSettings, create_app
def runner(argv, t): return (0, 'inactive\\n', '')
st = CommanderSettings(token='${TOKEN}', ledger='${tmp}/l.sqlite', heartbeat_dir='${tmp}/hb', log_dir='${tmp}/log', data_dir='${tmp}', vekl_url='http://127.0.0.1:1', runner=runner, units=('vati-vekl.service',))
uvicorn.run(create_app(st), host='127.0.0.1', port=${port}, log_level='warning')
`], { env: { ...process.env, PYTHONPATH: TRADING }, stdio: ['ignore', 'ignore', 'pipe'] });
  let pyErr = ''; py.stderr.on('data', (d) => { pyErr += d; });
  let shim;
  try {
    await waitHealth(`http://127.0.0.1:${port}`).catch((e) => { throw new Error(e.message + ' ' + pyErr.slice(-500)); });
    shim = spawn(process.execPath, [path.join(here, '../mcp_stdio.mjs')], { env: { ...process.env, VAN_COMMANDER_URL: `http://127.0.0.1:${port}`, VAN_COMMANDER_TOKEN: TOKEN }, stdio: ['pipe', 'pipe', 'inherit'] });
    const lines = [];
    let buf = '';
    shim.stdout.on('data', (d) => { buf += d; let i; while ((i = buf.indexOf('\n')) >= 0) { lines.push(JSON.parse(buf.slice(0, i))); buf = buf.slice(i + 1); } });
    const ask = async (msg) => { const n = lines.length; shim.stdin.write(JSON.stringify(msg) + '\n'); const t0 = Date.now(); while (lines.length <= n) { if (Date.now() - t0 > 15000) throw new Error('no reply'); await new Promise((r) => setTimeout(r, 20)); } return lines[n]; };
    const init = await ask({ jsonrpc: '2.0', id: 1, method: 'initialize', params: {} });
    assert.equal(init.result.serverInfo.name, 'van-trading-commander');
    const list = await ask({ jsonrpc: '2.0', id: 2, method: 'tools/list' });
    const names = list.result.tools.map((t) => t.name);
    assert.deepEqual(names, ['status', 'ledger_status', 'services', 'restart_service', 'tail_log', 'run_backtest', 'vekl_resolve', 'halt', 'doctor', 'accounts']);
    assert.ok(!names.some((n) => /shell|exec|process/.test(n)));
    const st = await ask({ jsonrpc: '2.0', id: 3, method: 'tools/call', params: { name: 'status', arguments: {} } });
    assert.equal(st.result.isError, false);
    const parsed = JSON.parse(st.result.content[0].text);
    assert.equal(parsed.ledger.events, 0);
    assert.equal(parsed.units[0].unit, 'vati-vekl.service');
    const bad = await ask({ jsonrpc: '2.0', id: 4, method: 'tools/call', params: { name: 'restart_service', arguments: { unit: 'sshd.service' } } });
    assert.equal(bad.result.isError, true);
    assert.match(bad.result.content[0].text, /403/);
    const halt = await ask({ jsonrpc: '2.0', id: 5, method: 'tools/call', params: { name: 'halt', arguments: {} } });
    assert.equal(halt.result.isError, true);
    const unknown = await ask({ jsonrpc: '2.0', id: 6, method: 'resources/list' });
    assert.equal(unknown.error.code, -32601);
    const acct = await ask({ jsonrpc: '2.0', id: 7, method: 'tools/call', params: { name: 'account_credentials', arguments: { alias: 'x', secrets: { token: 'never' } } } });
    assert.equal(acct.result.isError, true);
    assert.match(acct.result.content[0].text, /403/);
  } finally {
    if (shim) shim.kill();
    py.kill('SIGTERM');
  }
});
