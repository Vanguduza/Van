import fs from 'node:fs';
import path from 'node:path';
import { DEFAULT_REPO, loadEngineeringSkillRegistry } from './skill-registry.mjs';

const BASE = 'agent-system/engineering-knowledge/registries';
export const RESOURCE_CLASSES = new Set(['OFFICIAL_DOC','REPOSITORY','RELEASE_NOTES','ISSUE_DISCUSSION','FORUM_QA','SECURITY_ADVISORY','PACKAGE_REGISTRY','SKILL','PLUGIN','TOOL','MCP_SERVER','RULESET','HOOK','WORKFLOW_LOOP','EXAMPLE_REFERENCE']);
export const PASSIVE_RESOURCE_STATES = new Set(['DISCOVERY_APPROVED','REFERENCE_APPROVED','POLICY_APPROVED_CONDITIONAL','APPROVED','ACTIVE']);
export const EXECUTABLE_RESOURCE_CLASSES = new Set(['SKILL','PLUGIN','TOOL','MCP_SERVER','HOOK','WORKFLOW_LOOP']);
export const EXECUTABLE_RESOURCE_STATES = new Set(['APPROVED','ACTIVE']);

function load(repoDir, name, fallback = []) {
  const target = path.join(repoDir, BASE, name);
  try { return JSON.parse(fs.readFileSync(target, 'utf8')); }
  catch (error) { if (error?.code === 'ENOENT') return fallback; throw error; }
}

export function loadEngineeringResourceSources(repoDir = DEFAULT_REPO) {
  const rows = load(repoDir, 'ENGINEERING_RESOURCE_SOURCE_REGISTRY.json');
  if (!Array.isArray(rows)) throw new Error('ENGINEERING_RESOURCE_SOURCE_REGISTRY must be an array');
  return rows;
}

export function loadEngineeringResourceRegistry(repoDir = DEFAULT_REPO) {
  const rows = load(repoDir, 'ENGINEERING_RESOURCE_REGISTRY.json');
  if (!Array.isArray(rows)) throw new Error('ENGINEERING_RESOURCE_REGISTRY must be an array');
  return rows;
}

export function skillAsResource(skill) {
  return {
    resource_id: `skill:${skill.skill_id}`,
    name: skill.display_name || skill.skill_id,
    source_id: skill.provider === 'google-android' ? 'official.android.skills' : (skill.provider === 'google' ? 'official.google.skills' : 'dial.project'),
    resource_class: 'SKILL',
    authority: 'ENGINEERING_GUIDANCE_ONLY',
    status: skill.approval_state,
    activation_mode: 'EXECUTABLE_CAPABILITY',
    locator: skill.snapshot_rel || skill.source_path || skill.skill_id,
    task_classes: skill.task_classes || [],
    technologies: [],
    keywords: [],
    forbidden_effects: skill.forbidden_effects || [],
    requires_tools: skill.requires_tools || [],
    skill_id: skill.skill_id,
    production_pin: skill.production_pin,
    content_hash: skill.content_hash,
    snapshot_rel: skill.snapshot_rel,
    runtime_name: skill.runtime_name,
    activation_constraints: skill.activation_constraints || [],
    requires_independent_specialist_review: skill.requires_independent_specialist_review === true,
  };
}

export function loadAllEngineeringResources(repoDir = DEFAULT_REPO) {
  return [...loadEngineeringResourceRegistry(repoDir), ...loadEngineeringSkillRegistry(repoDir).map(skillAsResource)];
}

export function validateEngineeringResourceRegistries(repoDir = DEFAULT_REPO) {
  const sources = loadEngineeringResourceSources(repoDir);
  const resources = loadEngineeringResourceRegistry(repoDir);
  const failures = [];
  const sourceIds = new Set();
  for (const source of sources) {
    if (!source?.source_id) failures.push('source_id required');
    else if (sourceIds.has(source.source_id)) failures.push(`duplicate source_id: ${source.source_id}`);
    else sourceIds.add(source.source_id);
    if (!/^T[0-4]_/.test(String(source?.trust_tier || ''))) failures.push(`${source?.source_id || '<source>'}: trust_tier invalid`);
    if (!Array.isArray(source?.resource_classes) || !source.resource_classes.length) failures.push(`${source?.source_id || '<source>'}: resource_classes required`);
  }
  const resourceIds = new Set();
  for (const resource of resources) {
    const id = resource?.resource_id || '<resource>';
    if (!resource?.resource_id) failures.push('resource_id required');
    else if (resourceIds.has(resource.resource_id)) failures.push(`duplicate resource_id: ${resource.resource_id}`);
    else resourceIds.add(resource.resource_id);
    if (!sourceIds.has(resource?.source_id)) failures.push(`${id}: unknown source_id ${resource?.source_id}`);
    if (!RESOURCE_CLASSES.has(resource?.resource_class)) failures.push(`${id}: invalid resource_class ${resource?.resource_class}`);
    if (!Array.isArray(resource?.task_classes)) failures.push(`${id}: task_classes must be array`);
    if (!Array.isArray(resource?.forbidden_effects)) failures.push(`${id}: forbidden_effects must be array`);
    if (EXECUTABLE_RESOURCE_CLASSES.has(resource?.resource_class) && resource?.activation_mode === 'EXECUTABLE_CAPABILITY' && EXECUTABLE_RESOURCE_STATES.has(resource?.status)) {
      if (!resource?.content_hash && resource?.source_id !== 'dial.project') failures.push(`${id}: approved executable external resource requires content_hash`);
    }
  }
  return { ok: failures.length === 0, source_count: sources.length, resource_count: resources.length, failures };
}
