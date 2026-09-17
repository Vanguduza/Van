import fs from 'node:fs';
import path from 'node:path';

export const DEFAULT_CONTROL_HOME = process.env.DIAL_CONTROL_HOME || '/var/lib/dial-control';

const LAYOUT = [
  'state',
  'checkpoints/active',
  'checkpoints/archive',
  'capsules/active',
  'capsules/archive',
  'memory/hot',
  'memory/warm',
  'memory/cold',
  'memory/features',
  'sessions/hermes',
  'sessions/codex',
  'sessions/claude',
  'retrieval/index',
  'retrieval/cache',
  'evidence-cache',
  'evidence-cache/qualification',
  'evidence-cache/soak',
  'runtime-health',
  'events',
  'operations',
  'operations/projects',
  'missions',
  'approvals',
  'chat-control/idempotency',
  'knowledge/vendor',
  'knowledge/activation',
  'knowledge/activation/by-packet',
  'knowledge/learned/staged',
  'knowledge/learned/approved',
  'knowledge/evidence/qualification',
  'knowledge/evidence/outcomes',
  'knowledge/evidence/outcomes/latest',
  'knowledge/research',
  'knowledge/research/cache',
  'knowledge/research/forecasts',
  'knowledge/research/findings',
  'knowledge/research/challenges',
  'knowledge/graph/generations',
  'knowledge/graph/nodes',
  'knowledge/graph/edges',
  'knowledge/graph/units',
  'knowledge/graph/routes',
  'knowledge/graph/indexes',
  'knowledge/graph/invalidation',
  'knowledge/graph/tombstones',
  'knowledge/activation/manifests',
  'knowledge/activation/traces',
  'knowledge/capsules',
  'knowledge/admission',
  'execution/tasks',
  'execution/leases/active',
  'execution/leases/history',
  'execution/compute',
  'execution/receipts',
  'execution/providers/health',
  'execution/providers/quota',
  'execution/design/quarantine',
  'execution/design/candidates',
  'execution/design/accepted',
  'secrets',
  'work-queue/inbox',
  'work-queue/processing',
  'work-queue/completed',
  'work-queue/failed',
];

function assertRelative(rel) {
  if (!rel || path.isAbsolute(rel)) throw new Error(`state path must be relative: ${rel}`);
  const normalized = path.normalize(rel);
  if (normalized === '..' || normalized.startsWith(`..${path.sep}`)) {
    throw new Error(`state path escapes control root: ${rel}`);
  }
  return normalized;
}

export function resolveControlPath(rel, root = DEFAULT_CONTROL_HOME) {
  return path.join(root, assertRelative(rel));
}

export function ensureControlLayout(root = DEFAULT_CONTROL_HOME) {
  fs.mkdirSync(root, { recursive: true, mode: 0o700 });
  for (const rel of LAYOUT) fs.mkdirSync(resolveControlPath(rel, root), { recursive: true, mode: 0o700 });
  return root;
}

export function readJson(rel, fallback = null, root = DEFAULT_CONTROL_HOME) {
  const target = resolveControlPath(rel, root);
  try {
    return JSON.parse(fs.readFileSync(target, 'utf8'));
  } catch (error) {
    if (error?.code === 'ENOENT') return fallback;
    throw error;
  }
}

export function writeJsonAtomic(rel, value, root = DEFAULT_CONTROL_HOME) {
  ensureControlLayout(root);
  const target = resolveControlPath(rel, root);
  fs.mkdirSync(path.dirname(target), { recursive: true, mode: 0o700 });
  const temp = `${target}.${process.pid}.${Date.now()}.tmp`;
  const payload = `${JSON.stringify(value, null, 2)}\n`;
  fs.writeFileSync(temp, payload, { encoding: 'utf8', mode: 0o600, flag: 'w' });
  fs.renameSync(temp, target);
  try { fs.chmodSync(target, 0o600); } catch {}
  return target;
}

export function appendJsonl(rel, value, root = DEFAULT_CONTROL_HOME) {
  ensureControlLayout(root);
  const target = resolveControlPath(rel, root);
  fs.mkdirSync(path.dirname(target), { recursive: true, mode: 0o700 });
  fs.appendFileSync(target, `${JSON.stringify(value)}\n`, { encoding: 'utf8', mode: 0o600 });
  try { fs.chmodSync(target, 0o600); } catch {}
  return target;
}

export function archiveJson(activeRel, archivePrefix, root = DEFAULT_CONTROL_HOME) {
  const value = readJson(activeRel, null, root);
  if (value == null) return null;
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  return writeJsonAtomic(`${archivePrefix}/${stamp}.json`, value, root);
}
