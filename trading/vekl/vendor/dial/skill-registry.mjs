import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
export const DEFAULT_REPO = path.resolve(here, '../..');
const KNOWLEDGE_REL = 'agent-system/engineering-knowledge';

export const APPROVED_SKILL_STATES = new Set(['APPROVED', 'ACTIVE']);
export const TERMINAL_SKILL_STATES = new Set(['SUPERSEDED', 'DEPRECATED', 'REVOKED']);

function loadJson(repoDir, rel, fallback = null) {
  const target = path.join(repoDir, rel);
  try { return JSON.parse(fs.readFileSync(target, 'utf8')); }
  catch (error) {
    if (error?.code === 'ENOENT' && fallback !== null) return fallback;
    throw error;
  }
}

export function knowledgePaths(repoDir = DEFAULT_REPO) {
  const root = path.join(repoDir, KNOWLEDGE_REL);
  return {
    root,
    skill_registry: path.join(root, 'registries/ENGINEERING_SKILL_REGISTRY.json'),
    conflict_registry: path.join(root, 'registries/SKILL_CONFLICT_REGISTRY.json'),
    performance_registry: path.join(root, 'registries/SKILL_PERFORMANCE_REGISTRY.json'),
    bundle_registry: path.join(root, 'registries/SKILL_BUNDLE_REGISTRY.json'),
  };
}

export function loadEngineeringSkillRegistry(repoDir = DEFAULT_REPO) {
  const rows = loadJson(repoDir, `${KNOWLEDGE_REL}/registries/ENGINEERING_SKILL_REGISTRY.json`, []);
  if (!Array.isArray(rows)) throw new Error('ENGINEERING_SKILL_REGISTRY must be an array');
  return rows;
}

export function loadSkillConflictRegistry(repoDir = DEFAULT_REPO) {
  const rows = loadJson(repoDir, `${KNOWLEDGE_REL}/registries/SKILL_CONFLICT_REGISTRY.json`, []);
  if (!Array.isArray(rows)) throw new Error('SKILL_CONFLICT_REGISTRY must be an array');
  return rows;
}

export function loadSkillBundleRegistry(repoDir = DEFAULT_REPO) {
  const rows = loadJson(repoDir, `${KNOWLEDGE_REL}/registries/SKILL_BUNDLE_REGISTRY.json`, []);
  if (!Array.isArray(rows)) throw new Error('SKILL_BUNDLE_REGISTRY must be an array');
  return rows;
}

export function loadSkillPerformanceRegistry(repoDir = DEFAULT_REPO) {
  return loadJson(repoDir, `${KNOWLEDGE_REL}/registries/SKILL_PERFORMANCE_REGISTRY.json`, { schema_version: 1, skills: {} });
}

export function validateSkillRecord(record) {
  const failures = [];
  if (record?.schema_version !== 1) failures.push('schema_version must be 1');
  if (!/^[a-z0-9][a-z0-9._-]+$/i.test(String(record?.skill_id || ''))) failures.push('skill_id invalid');
  if (record?.authority !== 'ENGINEERING_GUIDANCE_ONLY') failures.push('authority must be ENGINEERING_GUIDANCE_ONLY');
  if (!Array.isArray(record?.task_classes)) failures.push('task_classes must be an array');
  if (!Array.isArray(record?.forbidden_effects)) failures.push('forbidden_effects must be an array');
  if (!String(record?.approval_state || '')) failures.push('approval_state required');
  if (APPROVED_SKILL_STATES.has(record?.approval_state)) {
    if (!record?.production_pin && record?.provider !== 'dial') failures.push('approved vendor skill requires production_pin');
    if (!record?.content_hash) failures.push('approved skill requires content_hash');
    if (!record?.snapshot_rel) failures.push('approved skill requires snapshot_rel');
    if (!record?.runtime_name) failures.push('approved skill requires runtime_name');
  }
  return failures;
}

export function validateEngineeringSkillRegistry(repoDir = DEFAULT_REPO) {
  const rows = loadEngineeringSkillRegistry(repoDir);
  const ids = new Set();
  const failures = [];
  for (const row of rows) {
    const id = row?.skill_id || '<missing>';
    if (ids.has(id)) failures.push(`duplicate skill_id: ${id}`);
    ids.add(id);
    for (const failure of validateSkillRecord(row)) failures.push(`${id}: ${failure}`);
  }
  return { ok: failures.length === 0, skill_count: rows.length, approved_count: rows.filter((r) => APPROVED_SKILL_STATES.has(r.approval_state)).length, failures };
}

export function getEngineeringSkill(skillId, repoDir = DEFAULT_REPO) {
  return loadEngineeringSkillRegistry(repoDir).find((row) => row.skill_id === skillId) ?? null;
}
