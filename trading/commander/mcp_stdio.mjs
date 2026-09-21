#!/usr/bin/env node
/**
 * Hermes subordinate MCP shim for the Van trading commander.
 *
 * Speaks MCP (JSON-RPC 2.0 over stdio, one message per line) to Hermes and
 * forwards each tool call as an HMAC-signed request to the commander service on
 * van-trading-core. The token is read from VAN_COMMANDER_TOKEN_FILE (0600) and
 * never appears in tool output. The tool list is whatever the commander
 * publishes: there is no generic shell tool to expose.
 *
 *   VAN_COMMANDER_URL=https://10.0.1.233:9133 VAN_COMMANDER_TOKEN_FILE=~/.van/commander.hermes.token node mcp_stdio.mjs
 */
import crypto from 'node:crypto';
import fs from 'node:fs';
import readline from 'node:readline';

const URL_BASE = (process.env.VAN_COMMANDER_URL || 'http://127.0.0.1:9133').replace(/\/$/, '');
const TOKEN = (process.env.VAN_COMMANDER_TOKEN || (process.env.VAN_COMMANDER_TOKEN_FILE ? fs.readFileSync(process.env.VAN_COMMANDER_TOKEN_FILE, 'utf8').trim() : '')).trim();
const PROTOCOL = '2024-11-05';

function sha256(b) { return crypto.createHash('sha256').update(b).digest('hex'); }
export function signHeaders(token, method, path, body, now = Date.now()) {
  const ts = String(Math.floor(now / 1000));
  const nonce = crypto.randomBytes(12).toString('hex');
  const canonical = `${ts}\n${nonce}\n${method.toUpperCase()}\n${path}\n${sha256(body)}`;
  const sig = crypto.createHmac('sha256', token).update(canonical).digest('hex');
  return { 'x-van-ts': ts, 'x-van-nonce': nonce, 'x-van-signature': sig };
}

async function call(method, path, bodyObj) {
  const body = bodyObj ? Buffer.from(JSON.stringify(bodyObj)) : Buffer.alloc(0);
  const headers = { ...signHeaders(TOKEN, method, path, body), 'content-type': 'application/json' };
  const res = await fetch(URL_BASE + path, { method, headers, body: method === 'POST' ? body : undefined });
  const text = await res.text();
  let data; try { data = JSON.parse(text); } catch { data = { raw: text }; }
  if (!res.ok) throw new Error(`commander ${res.status}: ${data.detail || text.slice(0, 200)}`);
  return data;
}

const out = (msg) => process.stdout.write(JSON.stringify(msg) + '\n');
const reply = (id, result) => out({ jsonrpc: '2.0', id, result });
const fail = (id, code, message) => out({ jsonrpc: '2.0', id, error: { code, message } });

export async function handle(msg) {
  const { id, method, params } = msg;
  if (method === 'initialize') return reply(id, { protocolVersion: PROTOCOL, capabilities: { tools: {} }, serverInfo: { name: 'van-trading-commander', version: '1.0.0' } });
  if (method === 'notifications/initialized' || method === 'ping') return id === undefined ? undefined : reply(id, {});
  if (method === 'tools/list') { const t = await call('GET', '/v1/tools'); return reply(id, { tools: t.tools }); }
  if (method === 'tools/call') {
    const name = params?.name; const args = params?.arguments || {};
    if (!/^[a-z_]+$/.test(String(name))) return fail(id, -32602, 'invalid tool name');
    try {
      const r = await call('POST', `/v1/cmd/${name}`, { args, requested_by: 'hermes' });
      return reply(id, { content: [{ type: 'text', text: JSON.stringify(r.result, null, 2) }], isError: false });
    } catch (e) {
      return reply(id, { content: [{ type: 'text', text: String(e.message) }], isError: true });
    }
  }
  return id === undefined ? undefined : fail(id, -32601, `method not found: ${method}`);
}

if (process.argv[1] && process.argv[1].endsWith('mcp_stdio.mjs')) {
  if (!TOKEN) { console.error('VAN_COMMANDER_TOKEN_FILE (or VAN_COMMANDER_TOKEN) required'); process.exit(2); }
  const rl = readline.createInterface({ input: process.stdin });
  rl.on('line', (line) => { if (!line.trim()) return; let msg; try { msg = JSON.parse(line); } catch { return fail(null, -32700, 'parse error'); } handle(msg).catch((e) => fail(msg.id ?? null, -32000, String(e.message))); });
}
