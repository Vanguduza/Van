#!/usr/bin/env node
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import readline from 'node:readline';
import { execFileSync, spawn } from 'node:child_process';

const BEGIN = 'SPMRF_REVIEW_RESULT_BEGIN';
const END = 'SPMRF_REVIEW_RESULT_END';
const MODEL = process.env.VAN_SPMRF_CODEX_MODEL || 'gpt-5.6-sol';
const HOME = os.homedir();
const CODEX = process.env.VAN_SPMRF_CODEX_BIN || path.join(HOME, '.local/share/van/spmrf/codex/node_modules/.bin/codex');
const CACHE = process.env.VAN_SPMRF_CACHE || path.join(HOME, '.cache/van-spmrf');
const ALLOWED = new Map([
  ['https://github.com/Vanguduza/dial-new.git', 'dial-new'],
  ['https://github.com/Vanguduza/Van.git', 'Van'],
]);

function run(cwd, command, args, options = {}) {
  return execFileSync(command, args, {
    cwd,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    maxBuffer: 32 * 1024 * 1024,
    ...options,
  }).trim();
}
function normalizeUrl(url) {
  let value = String(url || '').trim();
  if (/^git@github\.com:/.test(value)) value = `https://github.com/${value.slice('git@github.com:'.length)}`;
  if (value && !value.endsWith('.git')) value += '.git';
  return value;
}
function prepareWorktree(packet) {
  const url = normalizeUrl(packet.repository_url);
  const name = ALLOWED.get(url);
  if (!name) throw new Error(`repository not allowed for Trading review: ${url || 'missing'}`);
  if (!/^[a-f0-9]{40}$/.test(String(packet.repository_sha || ''))) throw new Error('invalid repository SHA');
  fs.mkdirSync(CACHE, { recursive: true, mode: 0o700 });
  const mirrors = path.join(CACHE, 'mirrors');
  const worktrees = path.join(CACHE, 'worktrees');
  fs.mkdirSync(mirrors, { recursive: true, mode: 0o700 });
  fs.mkdirSync(worktrees, { recursive: true, mode: 0o700 });
  const mirror = path.join(mirrors, name);
  if (!fs.existsSync(path.join(mirror, '.git'))) {
    run(mirrors, 'git', ['clone', '--filter=blob:none', '--no-checkout', url, name]);
  } else {
    const observed = run(mirror, 'git', ['remote', 'get-url', 'origin']);
    if (normalizeUrl(observed) !== url) throw new Error('cached review mirror origin mismatch');
  }
  run(mirror, 'git', ['fetch', '--prune', '--no-tags', 'origin', '+refs/heads/*:refs/remotes/origin/*']);
  try { run(mirror, 'git', ['cat-file', '-e', `${packet.repository_sha}^{commit}`]); }
  catch { run(mirror, 'git', ['fetch', '--no-tags', 'origin', packet.repository_sha]); }
  const target = fs.mkdtempSync(path.join(worktrees, `${name}-`));
  run(mirror, 'git', ['worktree', 'add', '--detach', target, packet.repository_sha]);
  const observedSha = run(target, 'git', ['rev-parse', 'HEAD']);
  if (observedSha !== packet.repository_sha) throw new Error('Trading review worktree SHA mismatch');
  return { mirror, target };
}
function cleanupWorktree(mirror, target) {
  try { execFileSync('git', ['worktree', 'remove', '--force', target], { cwd: mirror, stdio: 'ignore' }); }
  catch { try { fs.rmSync(target, { recursive: true, force: true }); } catch {} }
}
function buildPrompt(packet) {
  return [
    'DIAL SHARED PROJECT MEMORY FABRIC — INDEPENDENT TRADING-CORE CHATGPT REVIEW',
    'You are the independently authenticated ChatGPT/Codex reviewer on van-trading-core.',
    'The checkpoint author is another harness. Review the exact detached repository SHA. Do not edit files or take external side effects.',
    'Use the supplied repository-understanding delta to avoid rediscovering the entire project. Inspect only affected or dependency-relevant source needed to validate the claims.',
    'Project Truth and source evidence outrank the handover summary.',
    'Return ONLY JSON: {"verdict":"PASS|COMMENT|CHANGES_REQUIRED|BLOCK","summary":"...","findings":[{"severity":"CRITICAL|HIGH|MEDIUM|LOW|INFO","category":"...","file":"... or null","line":123,"claim":"...","evidence":"..."}]}',
    `Checkpoint: ${packet.checkpoint_id}`,
    `SHA: ${packet.repository_sha}`,
    `Base: ${packet.base_sha || 'none'}`,
    `Author: ${packet.author_harness}`,
    `Feature: ${packet.feature_id || 'unscoped'}`,
    packet.summary ? `Summary: ${packet.summary}` : '',
    packet.claims?.length ? `Claims:\n- ${packet.claims.join('\n- ')}` : '',
    packet.tests?.length ? `Tests:\n- ${packet.tests.join('\n- ')}` : '',
    packet.delta_context ? `Repository understanding delta:\n${packet.delta_context}` : '',
  ].filter(Boolean).join('\n\n');
}
function parseReview(text) {
  const raw = String(text || '').trim();
  const options = [
    raw,
    raw.replace(/^\`\`\`(?:json)?\s*/i, '').replace(/\s*\`\`\`$/, ''),
    raw.slice(raw.indexOf('{'), raw.lastIndexOf('}') + 1),
  ].filter(Boolean);
  for (const candidate of options) {
    try {
      const value = JSON.parse(candidate);
      if (value && typeof value === 'object') return value;
    } catch {}
  }
  throw new Error('Trading ChatGPT reviewer returned invalid JSON');
}
function normalize(value) {
  const allowed = new Set(['PASS', 'COMMENT', 'CHANGES_REQUIRED', 'BLOCK']);
  const verdict = String(value?.verdict || 'COMMENT').toUpperCase();
  return {
    verdict: allowed.has(verdict) ? verdict : 'COMMENT',
    summary: String(value?.summary || '').slice(0, 8000),
    findings: (Array.isArray(value?.findings) ? value.findings : []).slice(0, 100).map((f) => ({
      severity: String(f?.severity || 'INFO').toUpperCase(),
      category: String(f?.category || 'GENERAL').slice(0, 120),
      file: f?.file ? String(f.file).slice(0, 500) : null,
      line: Number.isFinite(Number(f?.line)) ? Number(f.line) : null,
      claim: String(f?.claim || f?.message || '').slice(0, 4000),
      evidence: f?.evidence ? String(f.evidence).slice(0, 4000) : null,
    })),
  };
}

async function codexReview(cwd, prompt) {
  if (!fs.existsSync(CODEX)) throw new Error(`Codex runtime missing: ${CODEX}`);
  const auth = run(cwd, CODEX, ['login', 'status']);
  if (!/Logged in using ChatGPT/i.test(auth)) throw new Error('Trading Core Codex is not authenticated using ChatGPT subscription OAuth');

  const child = spawn(CODEX, ['app-server', '--listen', 'stdio://'], {
    cwd,
    stdio: ['pipe', 'pipe', 'pipe'],
    env: { ...process.env, OPENAI_API_KEY: '', CODEX_API_KEY: '' },
  });
  const rl = readline.createInterface({ input: child.stdout, crlfDelay: Infinity });
  let nextId = 1;
  const pending = new Map();
  let finalMessage = '';
  let completed = null;
  let reroute = null;
  let stderr = '';
  child.stderr.setEncoding('utf8');
  child.stderr.on('data', (chunk) => { stderr += chunk; if (stderr.length > 10000) stderr = stderr.slice(-10000); });

  function send(message) { child.stdin.write(`${JSON.stringify(message)}\n`); }
  function request(method, params = {}) {
    const id = nextId++;
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject });
      send({ id, method, params });
    });
  }
  const done = new Promise((resolve) => {
    rl.on('line', (line) => {
      let msg;
      try { msg = JSON.parse(line); } catch { return; }
      if (msg.id != null && pending.has(msg.id)) {
        const waiter = pending.get(msg.id);
        pending.delete(msg.id);
        if (msg.error) waiter.reject(Object.assign(new Error(msg.error.message || 'Codex RPC error'), { rpc: msg.error }));
        else waiter.resolve(msg.result);
        return;
      }
      if (msg.method === 'model/rerouted') reroute = msg.params ?? msg;
      if (msg.method === 'item/agentMessage/delta') finalMessage += msg.params?.delta ?? '';
      if (msg.method === 'item/completed' && msg.params?.item?.type === 'agentMessage') finalMessage = msg.params.item.text ?? finalMessage;
      if (msg.method === 'turn/completed') { completed = msg.params?.turn ?? msg.params ?? null; resolve(); }
    });
    child.on('exit', resolve);
  });
  const timer = setTimeout(() => child.kill('SIGTERM'), 20 * 60 * 1000);
  try {
    await request('initialize', {
      clientInfo: { name: 'van_spmrf_reviewer', title: 'VAN SPMRF Reviewer', version: '1.0.0' },
      capabilities: { experimentalApi: true },
    });
    send({ method: 'initialized' });
    const started = await request('thread/start', {
      model: MODEL,
      cwd,
      ephemeral: true,
      approvalPolicy: 'never',
      permissions: ':read-only',
      allowProviderModelFallback: false,
    });
    const thread = started?.thread;
    if (!thread?.id) throw new Error('Trading reviewer thread/start did not return thread id');
    await request('turn/start', {
      threadId: thread.id,
      input: [{ type: 'text', text: prompt }],
      model: MODEL,
      effort: 'high',
      approvalPolicy: 'never',
      permissions: ':read-only',
    });
    await done;
    if (completed?.error) throw new Error(`Trading review failed: ${JSON.stringify(completed.error)}`);
    const resolved = reroute?.toModel ?? reroute?.to_model ?? thread.model ?? thread.modelId ?? MODEL;
    if (reroute || resolved !== MODEL) throw new Error(`Trading ChatGPT reviewer identity mismatch: requested ${MODEL}, resolved ${resolved}`);
    return {
      ...normalize(parseReview(finalMessage)),
      model_provenance: {
        provider_family: 'openai',
        runtime: 'codex_app_server',
        account_alias: 'chatgpt-secondary',
        requested_model: MODEL,
        resolved_model: resolved,
        identity_proven: true,
        thread_id: thread.id,
      },
    };
  } finally {
    clearTimeout(timer);
    if (!child.killed) child.kill('SIGTERM');
    rl.close();
    void stderr;
  }
}

async function main() {
  const packetFile = process.argv[2];
  if (!packetFile) throw new Error('usage: van-spmrf-review-worker <packet.json>');
  const packet = JSON.parse(fs.readFileSync(packetFile, 'utf8'));
  const prepared = prepareWorktree(packet);
  try {
    const review = await codexReview(prepared.target, buildPrompt(packet));
    const body = {
      schema_version: 1,
      harness_id: 'chatgpt-trading',
      checkpoint_id: packet.checkpoint_id,
      reviewed_repository_sha: packet.repository_sha,
      ...review,
    };
    const encoded = Buffer.from(JSON.stringify(body), 'utf8').toString('base64');
    process.stdout.write(`${BEGIN}\n${encoded}\n${END}\n`);
  } finally {
    cleanupWorktree(prepared.mirror, prepared.target);
  }
}
main().catch((error) => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
