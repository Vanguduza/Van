#!/usr/bin/env node
/**
 * VTIL borrow probe (Rev 2.1 §E.4).
 *
 * Runs DIAL's own VEKL resource resolver, unmodified, against the Van trading
 * registry by mirroring the two directory names DIAL hard-codes. Proves the
 * "borrow DIAL VEKL infrastructure" claim with a command, not a sentence.
 *
 *   DIAL_REPO=/path/to/dial-new node trading/vtil/tools/resolve_probe.mjs
 *
 * Exit 0 only when every golden case selects all must_include resources and
 * none of must_exclude, and the registry validates under DIAL's validator.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const VAN = path.resolve(here, '../../..');
const DIAL = path.resolve(process.env.DIAL_REPO || path.join(VAN, '..', 'dial-new'));
const REG = path.join(VAN, 'trading/vtil/registry');

function mirror() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'vtil-mirror-'));
  const repo = path.join(root, 'repo');
  fs.mkdirSync(path.join(repo, 'agent-system/engineering-knowledge'), { recursive: true });
  fs.mkdirSync(path.join(repo, 'agent-system/registries'), { recursive: true });
  fs.symlinkSync(REG, path.join(repo, 'agent-system/engineering-knowledge/registries'), 'dir');
  fs.symlinkSync(path.join(REG, 'TASK_CLASS_SIGNAL_POLICY.json'), path.join(repo, 'agent-system/registries/TASK_CLASS_SIGNAL_POLICY.json'));
  const control = path.join(root, 'control');
  fs.mkdirSync(control, { recursive: true });
  return { repo, control };
}

const GOLDEN = [
  { case_id: 'VT-001', instruction: 'Build the NFP shock vector and reaction-analogue retrieval for EURUSD using point-in-time payrolls vintages.',
    affected_paths: ['trading/vati/nfp/shock_vector.py'],
    must_include: ['van.trading.rules.rev2-canon', 'ref.bls.employment-situation', 'ref.alfred.vintages'],
    must_exclude: ['ref.deriv.api', 'ref.metaquotes.mt5-python', 'ref.lean.docs'] },
  { case_id: 'VT-002', instruction: 'Implement MT5 order_send with an atomic protective stop inside a Nautilus ExecutionClient, using symbol_info volume_step and stops level.',
    affected_paths: ['trading/vati/execution/mt5/execution.py'],
    must_include: ['van.trading.rules.rev2-canon', 'ref.metaquotes.mt5-python', 'ref.nautilus.docs'],
    must_exclude: ['ref.bls.employment-situation', 'ref.cftc.cot', 'ref.deriv.api'] },
  { case_id: 'VT-003', instruction: 'Size a Deriv synthetic index Rise/Fall contract by stake and reconcile open contracts after reconnect.',
    affected_paths: ['trading/vati/execution/deriv/execution.py'],
    must_include: ['van.trading.rules.rev2-canon', 'ref.deriv.api'],
    must_exclude: ['ref.bls.employment-situation', 'ref.fomc.statements', 'ref.metaquotes.mt5-python'] },
  { case_id: 'VT-004', instruction: 'Model gold regime from real yields, FOMC expectations and COT positioning; add CVOL and VIX term structure as forward-looking volatility state.',
    affected_paths: ['trading/vati/intelligence/regimes/gold.py'],
    must_include: ['ref.fomc.statements', 'ref.cftc.cot', 'ref.cme.cvol', 'ref.cboe.vix-term-structure', 'ref.wgc.gold-demand'],
    must_exclude: ['ref.deriv.api', 'ref.metaquotes.mt5-python'] },
];

async function main() {
  const resolverUrl = pathToFileURL(path.join(DIAL, 'agent-system/orchestration/engineering-resource-resolver.mjs')).href;
  const registryUrl = pathToFileURL(path.join(DIAL, 'agent-system/orchestration/engineering-resource-registry.mjs')).href;
  const { resolveEngineeringResources, classifyEngineeringResourcesTask } = await import(resolverUrl);
  const { validateEngineeringResourceRegistries } = await import(registryUrl);
  const { repo, control } = mirror();
  const validation = validateEngineeringResourceRegistries(repo);
  const report = { dial_repo: DIAL, dial_resolver: 'engineering-resource-resolver.mjs (unmodified)', registry_validation: validation, cases: [] };
  let failures = validation.ok ? 0 : 1;
  for (const c of GOLDEN) {
    const out = resolveEngineeringResources({ repoDir: repo, root: control, instruction: c.instruction, affectedPaths: c.affected_paths, maxResources: 8 });
    const ids = out.selected_resources.map((r) => r.resource_id);
    const missing = c.must_include.filter((id) => !ids.includes(id));
    const leaked = c.must_exclude.filter((id) => ids.includes(id));
    const community = out.selected_resources.filter((r) => r.corroboration_required).map((r) => r.resource_id);
    const ok = !missing.length && !leaked.length;
    if (!ok) failures += 1;
    report.cases.push({ case_id: c.case_id, ok, policy_version: out.policy_version, resolver_version: out.resolver_version, task_classes: out.task_classes, selected: ids, roles: Object.fromEntries(out.selected_resources.map((r) => [r.resource_id, `${r.selection_role}/${r.selection_purpose}`])), missing, leaked, community_corroboration_only: community });
  }
  report.status = failures ? 'RED' : 'GREEN';
  console.log(JSON.stringify(report, null, 2));
  process.exit(failures ? 1 : 0);
}
main().catch((e) => { console.error(e); process.exit(2); });
