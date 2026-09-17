#!/usr/bin/env node
/**
 * Van Trading VEKL service (Rev 5 Part G).
 *
 * A dedicated engineering-knowledge resolver for the trading system so that
 * trading packets never queue behind DIAL's vekl-worker. It runs DIAL's own
 * resolver code, vendored byte-for-byte under vendor/dial (see PROVENANCE.json),
 * against the Van trading registry (trading/vtil/registry). Every resolution is
 * persisted as an activation record with a deterministic activation_id so Sol,
 * Sonnet and the ledger can cite the same provenance.
 *
 *   VEKL_HOME=/var/lib/van-trading/vekl VEKL_PORT=9134 node trading/vekl/server.mjs
 *
 * Loopback only by default. No dependencies beyond Node ≥ 20.
 */
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
export const VAN_ROOT = path.resolve(here, '../..');
const REGISTRY = process.env.VEKL_REGISTRY || path.join(VAN_ROOT, 'trading/vtil/registry');
const VEKL_HOME = process.env.VEKL_HOME || path.join(os.tmpdir(), 'van-trading-vekl');
export const SERVICE_VERSION = 'van-trading-vekl/1.0.0';

function sha256(s) { return crypto.createHash('sha256').update(s).digest('hex'); }

/** Mirror the DIAL repo layout the vendored loaders expect; registry files are symlinked, never copied. */
export function ensureMirror(home = VEKL_HOME, registry = REGISTRY) {
  const repo = path.join(home, 'repo');
  const control = path.join(home, 'control');
  fs.mkdirSync(path.join(repo, 'agent-system/engineering-knowledge'), { recursive: true });
  fs.mkdirSync(path.join(repo, 'agent-system/registries'), { recursive: true });
  fs.mkdirSync(control, { recursive: true });
  const regLink = path.join(repo, 'agent-system/engineering-knowledge/registries');
  if (!fs.existsSync(regLink)) fs.symlinkSync(registry, regLink, 'dir');
  const policyLink = path.join(repo, 'agent-system/registries/TASK_CLASS_SIGNAL_POLICY.json');
  if (!fs.existsSync(policyLink)) fs.symlinkSync(path.join(registry, 'TASK_CLASS_SIGNAL_POLICY.json'), policyLink);
  return { repo, control, activations: path.join(home, 'activations.jsonl') };
}

export function registryFingerprint(registry = REGISTRY) {
  const files = fs.readdirSync(registry).filter((f) => f.endsWith('.json')).sort();
  const h = crypto.createHash('sha256');
  for (const f of files) h.update(f).update('\0').update(fs.readFileSync(path.join(registry, f))).update('\0');
  return { files: files.length, sha256: h.digest('hex') };
}

export async function loadResolver() {
  const base = path.join(here, 'vendor/dial');
  const prov = JSON.parse(fs.readFileSync(path.join(base, 'PROVENANCE.json'), 'utf8'));
  for (const [name, digest] of Object.entries(prov.files)) {
    const actual = sha256(fs.readFileSync(path.join(base, name)));
    if (actual !== digest) throw new Error(`vendored resolver file ${name} does not match PROVENANCE.json (${actual} != ${digest}); refusing to serve`);
  }
  const resolver = await import(pathToFileURL(path.join(base, 'engineering-resource-resolver.mjs')).href);
  const registry = await import(pathToFileURL(path.join(base, 'engineering-resource-registry.mjs')).href);
  return { resolver, registry, provenance: prov };
}

export class VeklService {
  constructor({ home = VEKL_HOME, registry = REGISTRY } = {}) {
    this.home = home; this.registry = registry;
    this.paths = ensureMirror(home, registry);
    this.mods = null;
    this.started_ms = Date.now();
  }

  async init() { this.mods = await loadResolver(); return this; }

  validate() { return this.mods.registry.validateEngineeringResourceRegistries(this.paths.repo); }

  resolve({ instruction = '', affected_paths = [], max_resources = 8, available_tools = [], requested_by = 'unknown', feature_record = null } = {}) {
    if (!instruction || typeof instruction !== 'string') throw new TypeError('instruction (string) is required');
    const out = this.mods.resolver.resolveEngineeringResources({ repoDir: this.paths.repo, root: this.paths.control, instruction, affectedPaths: affected_paths, featureRecord: feature_record, maxResources: max_resources, availableTools: available_tools });
    const fp = registryFingerprint(this.registry);
    const selected = out.selected_resources.map((r) => ({ resource_id: r.resource_id, selection_role: r.selection_role, selection_purpose: r.selection_purpose, corroboration_required: r.corroboration_required === true, resource_class: r.resource_class, status: r.status }));
    const body = { policy_version: out.policy_version, resolver_version: out.resolver_version, task_classes: out.task_classes, selected: selected.map((s) => s.resource_id).sort(), registry_sha256: fp.sha256, donor_commit: this.mods.provenance.donor_commit };
    const activation_id = `vtil-act-${sha256(JSON.stringify(body)).slice(0, 24)}`;
    const record = { activation_id, ...body, selected_resources: selected, instruction_sha256: sha256(instruction), affected_paths, requested_by, resolved_at_ms: Date.now(), service: SERVICE_VERSION };
    fs.appendFileSync(this.paths.activations, JSON.stringify(record) + '\n');
    return record;
  }

  activation(id) {
    if (!fs.existsSync(this.paths.activations)) return null;
    const lines = fs.readFileSync(this.paths.activations, 'utf8').split('\n').filter(Boolean);
    for (let i = lines.length - 1; i >= 0; i -= 1) {
      const rec = JSON.parse(lines[i]);
      if (rec.activation_id === id) return rec;
    }
    return null;
  }

  health() {
    const fp = registryFingerprint(this.registry);
    const v = this.validate();
    return { ok: v.ok, service: SERVICE_VERSION, resolver_provenance: { donor: this.mods.provenance.donor, donor_commit: this.mods.provenance.donor_commit, files: Object.keys(this.mods.provenance.files).length }, registry: { path: this.registry, ...fp, sources: v.source_count, resources: v.resource_count, failures: v.failures }, uptime_ms: Date.now() - this.started_ms };
  }
}

function json(res, code, body) { const s = JSON.stringify(body); res.writeHead(code, { 'content-type': 'application/json', 'content-length': Buffer.byteLength(s) }); res.end(s); }

export async function startServer({ port = Number(process.env.VEKL_PORT || 9134), host = process.env.VEKL_HOST || '127.0.0.1', token = process.env.VEKL_TOKEN || '', service } = {}) {
  const svc = service || await new VeklService().init();
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    if (token && req.headers.authorization !== `Bearer ${token}` && url.pathname !== '/health') return json(res, 401, { error: 'unauthorized' });
    if (req.method === 'GET' && url.pathname === '/health') return json(res, 200, svc.health());
    if (req.method === 'GET' && url.pathname === '/registry/validate') return json(res, 200, svc.validate());
    if (req.method === 'GET' && url.pathname.startsWith('/activation/')) { const rec = svc.activation(url.pathname.slice('/activation/'.length)); return rec ? json(res, 200, rec) : json(res, 404, { error: 'unknown activation' }); }
    if (req.method === 'POST' && url.pathname === '/resolve') {
      let buf = '';
      req.on('data', (c) => { buf += c; if (buf.length > 65536) req.destroy(); });
      req.on('end', () => { try { json(res, 200, svc.resolve(JSON.parse(buf || '{}'))); } catch (e) { json(res, 400, { error: String(e.message || e) }); } });
      return undefined;
    }
    return json(res, 404, { error: 'not found' });
  });
  await new Promise((resolve) => server.listen(port, host, resolve));
  return { server, port: server.address().port, service: svc };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  startServer().then(({ port }) => console.log(JSON.stringify({ listening: port, home: VEKL_HOME, registry: REGISTRY }))).catch((e) => { console.error(e); process.exit(1); });
}
