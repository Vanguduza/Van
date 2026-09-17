#!/usr/bin/env node
/**
 * Typed Hermes MCP bridge for VAN Canonical Owner-Agent Runtime Rev 3.1.
 *
 * This process is not an agent and exposes no shell/generic HTTP surface. It
 * forwards a fixed tool allowlist to the gateway's Hermes-internal runtime API.
 * The internal-control credential is read locally and never returned in tool
 * output. Canonical owner-context admission is intentionally NOT exposed.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import readline from 'node:readline';

const PROTOCOL = '2024-11-05';
const URL_BASE = (process.env.VAN_OWNER_RUNTIME_URL || 'http://127.0.0.1:8787').replace(/\/$/, '');

function expandHome(value) {
  if (!value) return value;
  if (value === '~') return os.homedir();
  return value.startsWith('~/') ? path.join(os.homedir(), value.slice(2)) : value;
}

function readEnvValue(filePath, key) {
  if (!filePath || !fs.existsSync(filePath)) return '';
  for (const raw of fs.readFileSync(filePath, 'utf8').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const idx = line.indexOf('=');
    if (idx <= 0 || line.slice(0, idx).trim() !== key) continue;
    let value = line.slice(idx + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    return value;
  }
  return '';
}

function loadToken() {
  if ((process.env.VAN_INTERNAL_CONTROL_TOKEN || '').trim()) return process.env.VAN_INTERNAL_CONTROL_TOKEN.trim();
  const explicit = expandHome(process.env.VAN_OWNER_RUNTIME_TOKEN_FILE || '');
  if (explicit && fs.existsSync(explicit)) return fs.readFileSync(explicit, 'utf8').trim();
  const envFile = expandHome(process.env.VAN_GATEWAY_ENV_FILE || '~/.config/van/gateway.env');
  return readEnvValue(envFile, 'VAN_INTERNAL_CONTROL_TOKEN').trim();
}

const TOKEN = loadToken();

const TOOLS = [
  { name: 'runtime_status', description: 'Read VAN owner-runtime health and capability status.', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'resolve_command', description: 'Deterministically resolve a known owner command without granting execution authority.', inputSchema: { type: 'object', properties: { text: { type: 'string' } }, required: ['text'], additionalProperties: false } },
  { name: 'context_graph_query', description: 'Query the bounded temporal owner-context graph. This retrieves evidence; it does not decide truth.', inputSchema: { type: 'object', properties: { seed_nodes: { type: 'array', items: { type: 'string' }, minItems: 1, maxItems: 32 }, scope: { type: 'string' }, direction: { type: 'string', enum: ['OUT', 'IN', 'BOTH'] }, predicates: { type: 'array', items: { type: 'string' } }, max_depth: { type: 'integer', minimum: 1, maximum: 3 }, max_edges: { type: 'integer', minimum: 1, maximum: 256 }, allow_inferred: { type: 'boolean' }, min_confidence_permille: { type: 'integer', minimum: 0, maximum: 1000 } }, required: ['seed_nodes'], additionalProperties: false } },
  { name: 'context_lexical_query', description: 'Run deterministic local lexical/entity retrieval over current owner facts and graph edges. No embedding, model inference or remote call is used.', inputSchema: { type: 'object', properties: { query: { type: 'string', minLength: 1, maxLength: 256 }, scope: { type: 'string' }, max_results: { type: 'integer', minimum: 1, maximum: 64 }, allow_inferred: { type: 'boolean' }, include_facts: { type: 'boolean' }, include_edges: { type: 'boolean' } }, required: ['query'], additionalProperties: false } },
  { name: 'context_hot_capsule', description: 'Compile or retrieve a bounded revision-sealed hot-context evidence capsule for an active workstream. This is a cache of evidence references, not a truth store.', inputSchema: { type: 'object', properties: { scopes: { type: 'array', items: { type: 'string' }, minItems: 1, maxItems: 8 }, requirements: { type: 'array', items: { type: 'object' }, maxItems: 32 }, seed_nodes: { type: 'array', items: { type: 'string' }, maxItems: 16 }, lexical_queries: { type: 'array', items: { type: 'string', maxLength: 256 }, maxItems: 8 }, allow_inferred: { type: 'boolean' }, graph_depth: { type: 'integer', minimum: 1, maximum: 2 }, max_graph_edges: { type: 'integer', minimum: 1, maximum: 96 }, max_lexical_hits_per_query: { type: 'integer', minimum: 1, maximum: 24 }, ttl_ms: { type: 'integer', minimum: 1000, maximum: 300000 } }, additionalProperties: false } },
  { name: 'context_readiness', description: 'Resolve exact canonical context requirements and report CURRENT/STALE/MISSING/CONFLICTED.', inputSchema: { type: 'object', properties: { command_id: { type: 'string' }, requirements: { type: 'array', items: { type: 'object' } } }, required: ['command_id', 'requirements'], additionalProperties: false } },
  { name: 'context_snapshot', description: 'Seal an immutable context snapshot after readiness succeeds.', inputSchema: { type: 'object', properties: { command_id: { type: 'string' }, requirements: { type: 'array', items: { type: 'object' } }, graph_evidence_refs: { type: 'array', items: { type: 'string' } }, lexical_evidence_refs: { type: 'array', items: { type: 'string' } }, live_state_refs: { type: 'array', items: { type: 'string' } }, policy_refs: { type: 'array', items: { type: 'string' } } }, required: ['command_id', 'requirements'], additionalProperties: false } },
  { name: 'research_status', description: 'Read gateway-mediated external research readiness.', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'research_search', description: 'Run bounded gateway-mediated research. External evidence remains untrusted until admitted by policy.', inputSchema: { type: 'object', properties: { query: { type: 'string' }, mode: { type: 'string' }, egress_class: { type: 'string' }, max_results: { type: 'integer' }, owner_approved_sensitive_egress: { type: 'boolean' } }, required: ['query'], additionalProperties: false } },
  { name: 'action_begin', description: 'Request gateway authorization for a registered typed action bound to signed command authority.', inputSchema: { type: 'object', properties: { execution_id: { type: 'string' }, command_id: { type: 'string' }, turn_id: { type: ['string', 'null'] }, action_id: { type: 'string' }, principal_type: { type: 'string' }, requested_by: { type: 'string' }, idempotency_key: { type: 'string' }, parameters: { type: 'object' }, snapshot_id: { type: ['string', 'null'] } }, required: ['execution_id', 'command_id', 'action_id', 'principal_type', 'requested_by', 'idempotency_key'], additionalProperties: false } },
  { name: 'action_submitted', description: 'Record provider acceptance/correlation for an authorized action. This is not completion.', inputSchema: { type: 'object', properties: { execution_id: { type: 'string' }, correlation: { type: 'object' }, evidence_pointer: { type: ['string', 'null'] } }, required: ['execution_id'], additionalProperties: false } },
  { name: 'action_verify', description: 'Submit observed postconditions for deterministic gateway verification.', inputSchema: { type: 'object', properties: { execution_id: { type: 'string' }, success: { type: 'boolean' }, correlation: { type: 'object' }, observed_postcondition: { type: 'object' }, evidence_pointer: { type: ['string', 'null'] }, error_code: { type: ['string', 'null'] } }, required: ['execution_id', 'success'], additionalProperties: false } },
  { name: 'action_get', description: 'Read the authoritative execution state for one action execution.', inputSchema: { type: 'object', properties: { execution_id: { type: 'string' } }, required: ['execution_id'], additionalProperties: false } },
];

const ROUTES = {
  runtime_status: { method: 'GET', path: () => '/v1/runtime/status' },
  resolve_command: { method: 'POST', path: () => '/v1/runtime/resolve', body: (a) => a },
  context_graph_query: { method: 'POST', path: () => '/v1/runtime/context/graph/query', body: (a) => a },
  context_lexical_query: { method: 'POST', path: () => '/v1/runtime/context/lexical/query', body: (a) => a },
  context_hot_capsule: { method: 'POST', path: () => '/v1/runtime/context/hot-capsules', body: (a) => a },
  context_readiness: { method: 'POST', path: () => '/v1/runtime/context/readiness', body: (a) => a },
  context_snapshot: { method: 'POST', path: () => '/v1/runtime/context/snapshots', body: (a) => a },
  research_status: { method: 'GET', path: () => '/v1/runtime/research/status' },
  research_search: { method: 'POST', path: () => '/v1/runtime/research/search', body: (a) => a },
  action_begin: { method: 'POST', path: () => '/v1/runtime/actions/begin', body: (a) => a },
  action_submitted: { method: 'POST', path: (a) => `/v1/runtime/actions/${encodeURIComponent(a.execution_id)}/submitted`, body: (a) => ({ correlation: a.correlation || {}, evidence_pointer: a.evidence_pointer ?? null }) },
  action_verify: { method: 'POST', path: () => '/v1/runtime/actions/verify', body: (a) => a },
  action_get: { method: 'GET', path: (a) => `/v1/runtime/actions/${encodeURIComponent(a.execution_id)}` },
};

async function callRuntime(name, args) {
  if (!TOKEN) throw new Error('owner runtime internal-control credential unavailable');
  const route = ROUTES[name];
  if (!route) throw new Error('tool not allowed');
  const method = route.method;
  const targetPath = route.path(args || {});
  const bodyObj = route.body ? route.body(args || {}) : undefined;
  const options = { method, headers: { 'x-van-internal-token': TOKEN, 'content-type': 'application/json' } };
  if (bodyObj !== undefined && method !== 'GET') options.body = JSON.stringify(bodyObj);
  const res = await fetch(URL_BASE + targetPath, options);
  const text = await res.text();
  let data; try { data = JSON.parse(text); } catch { data = { detail: text.slice(0, 500) }; }
  if (!res.ok) throw new Error(`owner runtime ${res.status}: ${data.detail || 'request failed'}`);
  return data;
}

const out = (msg) => process.stdout.write(JSON.stringify(msg) + '\n');
const reply = (id, result) => out({ jsonrpc: '2.0', id, result });
const fail = (id, code, message) => out({ jsonrpc: '2.0', id, error: { code, message } });

export async function handle(msg) {
  const { id, method, params } = msg;
  if (method === 'initialize') return reply(id, { protocolVersion: PROTOCOL, capabilities: { tools: {} }, serverInfo: { name: 'van-owner-runtime', version: '3.1.0' } });
  if (method === 'notifications/initialized' || method === 'ping') return id === undefined ? undefined : reply(id, {});
  if (method === 'tools/list') return reply(id, { tools: TOOLS });
  if (method === 'tools/call') {
    const name = String(params?.name || '');
    if (!Object.hasOwn(ROUTES, name)) return fail(id, -32602, 'tool not allowed');
    try {
      const result = await callRuntime(name, params?.arguments || {});
      return reply(id, { content: [{ type: 'text', text: JSON.stringify(result, null, 2) }], isError: false });
    } catch (error) {
      return reply(id, { content: [{ type: 'text', text: String(error.message || error) }], isError: true });
    }
  }
  return id === undefined ? undefined : fail(id, -32601, `method not found: ${method}`);
}

if (process.argv[1] && process.argv[1].endsWith('owner_runtime_stdio.mjs')) {
  if (!TOKEN) {
    console.error('VAN_INTERNAL_CONTROL_TOKEN, VAN_OWNER_RUNTIME_TOKEN_FILE, or VAN_GATEWAY_ENV_FILE credential required');
    process.exit(2);
  }
  const rl = readline.createInterface({ input: process.stdin });
  rl.on('line', (line) => {
    if (!line.trim()) return;
    let msg;
    try { msg = JSON.parse(line); } catch { return fail(null, -32700, 'parse error'); }
    handle(msg).catch((error) => fail(msg.id ?? null, -32000, String(error.message || error)));
  });
}
