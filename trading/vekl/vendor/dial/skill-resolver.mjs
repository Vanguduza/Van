import fs from 'node:fs';
import path from 'node:path';
import {
  APPROVED_SKILL_STATES,
  DEFAULT_REPO,
  loadEngineeringSkillRegistry,
  loadSkillBundleRegistry,
  loadSkillConflictRegistry,
  loadSkillPerformanceRegistry,
} from './skill-registry.mjs';

export const VEKL_POLICY_VERSION = 'vekl-1.0';
export const DEFAULT_MAX_SKILLS = 3;
export const MANDATORY_TASK_CLASSES = new Set([
  'ANDROID_UI_IMPLEMENTATION',
  'ANDROID_RESPONSIVE_LAYOUT',
  'ANDROID_NAVIGATION',
  'ANDROID_SECURITY',
  'ANDROID_PERFORMANCE',
  'ANDROID_RELEASE_OPTIMIZATION',
  'ANDROID_CAMERA',
  'ANDROID_TESTING',
  'ANDROID_DEVICE_VERIFICATION',
]);

const CLASSIFIERS = [
  ['DELIVERY_MAPS', /\b(delivery|courier|fleet).{0,80}\b(map|route|routing|geocod|osrm|maplibre|vroom|nominatim)\b/i],
  ['ANDROID_SECURITY', /\b(android).{0,100}\b(intent|deep[- ]?link|exported|permission|security)\b|\b(intent|deep[- ]?link).{0,100}\bandroid\b/i],
  ['ANDROID_PERFORMANCE', /\b(android).{0,100}\b(perfetto|jank|startup|trace|performance|profil)\b|\b(perfetto|jank).{0,100}\bandroid\b/i],
  ['ANDROID_RELEASE_OPTIMIZATION', /\b(android).{0,100}\b(r8|proguard|shrink|obfuscat|apk size|bundle size)\b/i],
  ['ANDROID_CAMERA', /\b(android).{0,100}\b(camera|camerax|photo|proof of delivery|pod|capture)\b/i],
  ['ANDROID_NAVIGATION', /\b(android|compose).{0,100}\b(navigation|nav3|navigation 3|deep[- ]?link|back stack)\b/i],
  ['ANDROID_TESTING', /\b(android).{0,100}\b(test|emulator|device|adb|instrumentation|espresso|uiautomator)\b/i],
  ['ANDROID_DEVICE_VERIFICATION', /\b(android|adb|emulator|device).{0,100}\b(build|run|verify|screenshot|layout|inspect|test)\b/i],
  ['ANDROID_RESPONSIVE_LAYOUT', /\b(android|compose).{0,100}\b(adaptive|responsive|tablet|foldable|window size|multi[- ]?pane)\b/i],
  ['ANDROID_UI_IMPLEMENTATION', /\b(android|compose|jetpack compose).{0,120}\b(screen|ui|layout|component|surface|edge[- ]?to[- ]?edge|inset)\b/i],
];
// Deterministic task rules keep activation policy inspectable and testable.
CLASSIFIERS.push(
  ['GA_ANALYTICS_ADMIN', /\b(google analytics|ga4).{0,100}\b(admin|property|stream|configure|configuration)\b/i],
  ['GA_ANALYTICS_ADAPTER', /\b(google analytics|ga4).{0,100}\b(data api|report|metric|dimension|adapter|ingest|query)\b/i],
  ['CLOUD_SECURITY_REVIEW', /\b(cloud|oracle|infrastructure|platform).{0,100}\bsecurity review|well[- ]architected security|security posture\b/i],
  ['CLOUD_RELIABILITY_REVIEW', /\b(cloud|oracle|infrastructure|platform).{0,100}\b(reliability|resilien|availability|failover|disaster recovery)\b/i],
  ['CLOUD_PERFORMANCE_REVIEW', /\b(cloud|oracle|infrastructure|platform).{0,100}\b(performance|latency|throughput|capacity)\b/i],
  ['CLOUD_OPERATIONAL_REVIEW', /\b(cloud|oracle|infrastructure|platform).{0,100}\b(operational excellence|runbook|incident|observability|operations review)\b/i],
  ['INFRA_MIGRATION', /\b(migrate|migration|move|replace).{0,80}\b(oracle|cloudflare|supabase|gcp|google cloud|cloud run|gke|firebase)\b/i],
  // Bare `health` and bare `claim` are ordinary engineering English. `health` matched
  // "operational health exception monitor" on a compliance Feature and `claim` matched an
  // implementation note reading "any claim that the agreement wording is legally adequate",
  // so a grocery consent Feature classified HEALTH_SENSITIVE. Clinical context is required.
  ['HEALTH_SENSITIVE', /\b(patient|clinical|diagnos|pharmacy|medical|phi|prescription|icd-?10)\b|\bhealth (record|data|information|claim|scheme|plan|funder|benefit)s?\b|\bclaims? adjudication\b|\bfunder (clearance|remittance|claim)\b|\bdial health\b/i],
  ['SKILL_LIFECYCLE_RESEARCH', /\b(skill registry|agent skill|skills lifecycle|skill revision|skill discovery)\b/i],
);

// The task classes these rules can emit. Exported so the task-class coherence gate compares
// the live rule table against what resources declare instead of a hand-kept copy.
export const CLASSIFIER_TASK_CLASSES = Object.freeze(CLASSIFIERS.map(([id]) => id));

function uniq(values) { return [...new Set(values.filter(Boolean))]; }
function textOf(value) { return String(value ?? '').trim(); }

function simpleGlobMatch(pattern, value) {
  const escaped = String(pattern)
    .replace(/[.+^${}()|[\]\\]/g, '\\$&')
    .replaceAll('**', '§§DOUBLESTAR§§')
    .replaceAll('*', '[^/]*')
    .replaceAll('§§DOUBLESTAR§§', '.*');
  return new RegExp(`^${escaped}$`, 'i').test(String(value).replaceAll('\\', '/'));
}

function wildcardMatch(pattern, value) {
  const escaped = String(pattern).replace(/[.+^${}()|[\]\\]/g, '\\$&').replaceAll('*', '.*');
  return new RegExp(`^${escaped}$`, 'i').test(String(value));
}

export function classifyEngineeringTask({ instruction = '', affectedPaths = [], featureRecord = null } = {}) {
  const recordText = featureRecord
    ? [featureRecord.outcome, featureRecord.implementation_note, featureRecord.aggregate, featureRecord.module, featureRecord.owner]
        .filter(Boolean)
        .join('\n')
    : '';
  const haystack = [instruction, ...(affectedPaths || []), recordText].join('\n');
  const classes = [];
  for (const [taskClass, pattern] of CLASSIFIERS) if (pattern.test(haystack)) classes.push(taskClass);
  if (!classes.length) classes.push('GENERAL_DEVELOPMENT');
  return uniq(classes);
}

function featureRecordFor(repoDir, featureId) {
  if (!featureId) return null;
  try {
    const rows = JSON.parse(fs.readFileSync(path.join(repoDir, 'agent-system/registries/FEATURE_REGISTRY.json'), 'utf8'));
    return Array.isArray(rows) ? rows.find((row) => row.feature_id === featureId) ?? null : null;
  } catch { return null; }
}

function conflictFor(skill, taskClasses, conflicts, metadata) {
  for (const conflict of conflicts) {
    if (!wildcardMatch(conflict.skill_pattern, skill.skill_id)) continue;
    const scope = conflict.dial_scope || [];
    const scoped = scope.includes('*') || scope.some((entry) => taskClasses.includes(entry));
    if (!scoped) continue;
    if (metadata?.owner_approved_architecture_evaluation === true && /architecture evaluation/i.test(conflict.exception || '')) continue;
    if (metadata?.health_lawful_purpose === true && conflict.conflict_id === 'SKC-HEALTH-ADS-001') continue;
    return conflict;
  }
  return null;
}

function performanceFor(performanceRegistry, skillId, taskClasses) {
  const raw = performanceRegistry?.skills?.[skillId] ?? {};
  const classRows = raw.task_classes ?? {};
  let successLift = Number(raw.historical_success_lift || 0);
  for (const taskClass of taskClasses) successLift = Math.max(successLift, Number(classRows?.[taskClass]?.historical_success_lift || 0));
  return Math.max(-1, Math.min(1, successLift));
}

function scoreSkill(skill, taskClasses, affectedPaths, performanceRegistry) {
  const taskMatches = skill.task_classes?.filter((task) => taskClasses.includes(task)).length ?? 0;
  const taskRelevance = taskMatches ? Math.min(1, taskMatches / Math.max(1, taskClasses.length)) : 0;
  const pathMatches = (skill.path_triggers || []).some((pattern) => affectedPaths.some((p) => simpleGlobMatch(pattern, p))) ? 1 : 0;
  const successLift = (performanceFor(performanceRegistry, skill.skill_id, taskClasses) + 1) / 2;
  const evalScore = Number(skill.eval_score ?? 0.5);
  const freshness = skill.last_verified_at ? Math.max(0, 1 - ((Date.now() - Date.parse(skill.last_verified_at)) / (1000 * 60 * 60 * 24 * 365))) : 0.25;
  const toolAvailability = (skill.requires_tools || []).length ? 0.5 : 1;
  const contextCost = Math.min(1, Number(skill.context_cost_estimate || 0) / 20000);
  const riskPenalty = ({ LOW: 0, MEDIUM: 0.03, HIGH: 0.1, CRITICAL: 0.25 })[skill.risk_class] ?? 0.05;
  return (
    0.35 * taskRelevance
    + 0.20 * pathMatches
    + 0.15 * successLift
    + 0.10 * 0.75
    + 0.10 * evalScore
    + 0.05 * freshness
    + 0.05 * toolAvailability
    - 0.10 * contextCost
    - riskPenalty
  );
}

export function resolveEngineeringSkills({
  repoDir = DEFAULT_REPO,
  featureId = null,
  instruction = '',
  affectedPaths = [],
  metadata = {},
  maxSkills = DEFAULT_MAX_SKILLS,
  registry,
  conflicts,
  bundles,
  performanceRegistry,
} = {}) {
  const skills = registry ?? loadEngineeringSkillRegistry(repoDir);
  const conflictRows = conflicts ?? loadSkillConflictRegistry(repoDir);
  const bundleRows = bundles ?? loadSkillBundleRegistry(repoDir);
  const perf = performanceRegistry ?? loadSkillPerformanceRegistry(repoDir);
  const featureRecord = featureRecordFor(repoDir, featureId);
  const taskClasses = classifyEngineeringTask({ instruction, affectedPaths, featureRecord });
  const rejected = [];
  const candidates = [];

  for (const skill of skills) {
    if (!APPROVED_SKILL_STATES.has(skill.approval_state)) {
      if ((skill.task_classes || []).some((task) => taskClasses.includes(task))) rejected.push({ skill_id: skill.skill_id, reason: `NOT_APPROVED:${skill.approval_state}` });
      continue;
    }
    if (!(skill.task_classes || []).some((task) => taskClasses.includes(task))) continue;
    const conflict = conflictFor(skill, taskClasses, conflictRows, metadata);
    if (conflict) { rejected.push({ skill_id: skill.skill_id, reason: `CONFLICT:${conflict.conflict_id}`, conflict }); continue; }
    if (taskClasses.includes('HEALTH_SENSITIVE') && /ads|analytics/i.test(`${skill.skill_id} ${skill.display_name}`) && metadata?.health_lawful_purpose !== true) {
      rejected.push({ skill_id: skill.skill_id, reason: 'HEALTH_SENSITIVE_EXTERNAL_GUIDANCE_BLOCKED' });
      continue;
    }
    const requiredTools = skill.requires_tools || [];
    const availableTools = new Set(metadata?.available_tools || []);
    if (requiredTools.some((tool) => !availableTools.has(tool))) {
      rejected.push({ skill_id: skill.skill_id, reason: 'REQUIRED_TOOL_UNAVAILABLE' });
      continue;
    }
    candidates.push({ skill, score: scoreSkill(skill, taskClasses, affectedPaths, perf) });
  }

  candidates.sort((a, b) => b.score - a.score || a.skill.skill_id.localeCompare(b.skill.skill_id));
  const relevantBundles = bundleRows.filter((bundle) => (bundle.task_classes || []).some((task) => taskClasses.includes(task)));
  const bundleCap = relevantBundles.length ? Math.max(...relevantBundles.map((b) => Number(b.max_skills || maxSkills))) : maxSkills;
  const limit = Math.max(0, Math.min(5, Number(metadata?.max_skills ?? Math.min(maxSkills, bundleCap))));
  const selected = candidates.slice(0, limit).map(({ skill, score }) => ({
    skill_id: skill.skill_id,
    display_name: skill.display_name,
    provider: skill.provider,
    runtime_name: skill.runtime_name,
    upstream_repo: skill.upstream_repo,
    upstream_commit: skill.production_pin,
    content_hash: skill.content_hash,
    snapshot_rel: skill.snapshot_rel,
    approval_state: skill.approval_state,
    task_classes: skill.task_classes || [],
    activation_constraints: skill.activation_constraints || [],
    requires_independent_specialist_review: skill.requires_independent_specialist_review === true,
    reason: `Matched task class ${skill.task_classes.filter((task) => taskClasses.includes(task)).join(', ')}`,
    mode: 'GUIDANCE_ONLY',
    selection_score: Number(score.toFixed(4)),
  }));

  const hasRelevantUnapproved = rejected.some((r) => r.reason.startsWith('NOT_APPROVED'));
  const requiredTaskClasses = taskClasses.filter((task) => MANDATORY_TASK_CLASSES.has(task));
  const missingMandatoryClasses = requiredTaskClasses.filter((task) => !selected.some((skill) => (skill.task_classes || []).includes(task)));
  let resolutionState = 'NO_EXTERNAL_SKILL_REQUIRED';
  if (missingMandatoryClasses.length) resolutionState = 'MANDATORY_APPROVED_SKILL_UNAVAILABLE';
  else if (selected.length) resolutionState = 'SELECTED_APPROVED_SKILLS';
  else if (hasRelevantUnapproved) resolutionState = 'NO_APPROVED_SKILL_AVAILABLE';
  else if (rejected.some((r) => r.reason.startsWith('CONFLICT') || r.reason.includes('BLOCKED'))) resolutionState = 'ALL_MATCHES_BLOCKED_BY_POLICY';

  return {
    policy_version: VEKL_POLICY_VERSION,
    feature_id: featureId,
    task_classes: taskClasses,
    selected_skills: selected,
    rejected,
    relevant_bundles: relevantBundles.map((b) => b.bundle_id),
    resolution_state: resolutionState,
    execution_allowed: missingMandatoryClasses.length === 0,
    mandatory_task_classes: requiredTaskClasses,
    missing_mandatory_task_classes: missingMandatoryClasses,
    max_skills: limit,
    authority: 'NON_AUTHORITATIVE_ENGINEERING_GUIDANCE',
  };
}
