#!/usr/bin/env node
/**
 * Typed Hermes MCP bridge for VAN Canonical Owner-Agent Runtime Rev 3.1.
 *
 * This process is not an agent and exposes no shell/generic HTTP surface. It
 * forwards a fixed tool allowlist to the gateway's Hermes-internal control API: the
 * owner-runtime surface under /v1/runtime/*, plus the already-governed /v1/browser/*
 * and /v1/automation/* assignment/execute routes some of these tools call directly.
 * The internal-control credential is read locally and never returned in tool output.
 * CANONICAL_OWNER-tier owner-context admission is intentionally NOT exposed; the
 * INFERRED/MODEL_DERIVED memory-candidate tools this shim does carry cannot produce
 * it (the gateway route refuses any other authority/source_trust with 403).
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
  const explicit = expandHome(process.env.VAN_OWNER_RUNTIME_TOKEN_FILE || '');
  if (explicit) {
    // An explicit scoped selector must never fall back to an ambient all-scope token.
    if (!fs.existsSync(explicit) || (fs.statSync(explicit).mode & 0o077) !== 0) return '';
    return fs.readFileSync(explicit, 'utf8').trim();
  }
  if ((process.env.VAN_INTERNAL_CONTROL_TOKEN || '').trim()) return process.env.VAN_INTERNAL_CONTROL_TOKEN.trim();
  const envFile = expandHome(process.env.VAN_GATEWAY_ENV_FILE || '~/.config/van/gateway.env');
  return readEnvValue(envFile, 'VAN_INTERNAL_CONTROL_TOKEN').trim();
}

const TOKEN = loadToken();

const TOOLS = [
  { name: 'mission_control_poll', description: 'Read exact run-bound owner dispatch fence and ordered directions. PAUSED refuses future gateway effects; it does not prove process suspension or cancel an operation already admitted.', inputSchema: { type: 'object', properties: { mission_id: { type: 'string', minLength: 1, maxLength: 256 }, hermes_run_id: { type: 'string', minLength: 1, maxLength: 256 } }, required: ['mission_id', 'hermes_run_id'], additionalProperties: false } },
  { name: 'mission_control_ack', description: 'Record one exact run-bound checkpoint or direction adoption using the current poll generation and original control digest. This is a worker report, not independent verification of stopping or authority to execute.', inputSchema: { type: 'object', properties: { mission_id: { type: 'string', minLength: 1, maxLength: 256 }, hermes_run_id: { type: 'string', minLength: 1, maxLength: 256 }, control_id: { type: 'string', minLength: 1, maxLength: 256 }, generation: { type: 'integer', minimum: 0, maximum: 2147483647 }, payload_digest: { type: 'string', pattern: '^sha256:[a-f0-9]{64}$' }, checkpoint_ref: { type: 'string', minLength: 1, maxLength: 2048 } }, required: ['mission_id', 'hermes_run_id', 'control_id', 'generation', 'payload_digest', 'checkpoint_ref'], additionalProperties: false } },
  { name: 'decision_escalate', description: 'Create or recover one immutable typed owner judgment for this actual bound run. Choices, expiry and referenced evidence are bounded. A decision answer never grants action authority.', inputSchema: { type: 'object', properties: { mission_id: { type: 'string', minLength: 1, maxLength: 128 }, hermes_run_id: { type: 'string', minLength: 1, maxLength: 256 }, request_id: { type: 'string', minLength: 8, maxLength: 128, pattern: '^[A-Za-z0-9][A-Za-z0-9._:-]*$' }, title: { type: 'string', minLength: 1, maxLength: 300 }, body: { type: 'string', minLength: 1, maxLength: 12000 }, choices: { type: 'array', maxItems: 16, items: { type: 'object', properties: { id: { type: 'string', minLength: 1, maxLength: 64, pattern: '^[A-Za-z0-9][A-Za-z0-9._:-]*$' }, label: { type: 'string', minLength: 1, maxLength: 200 }, description: { type: 'string', maxLength: 2000 } }, required: ['id', 'label'], additionalProperties: false } }, evidence: { type: 'array', maxItems: 32, items: { type: 'object', properties: { ref: { type: 'string', minLength: 1, maxLength: 512 }, label: { type: 'string', maxLength: 200 }, kind: { type: 'string', enum: ['REFERENCE', 'MISSION_EVENT'] }, observed_at_unix: { type: ['integer', 'null'], minimum: 0 } }, required: ['ref'], additionalProperties: false } }, blocking: { type: 'boolean' }, expires_at_unix: { type: ['integer', 'null'], minimum: 1 } }, required: ['mission_id', 'hermes_run_id', 'request_id', 'title', 'body'], additionalProperties: false } },
  { name: 'decision_read', description: 'Read one typed judgment linked to this actual run. An owner selection is informational; fresh sealed action authority is still required.', inputSchema: { type: 'object', properties: { decision_id: { type: 'string', minLength: 1, maxLength: 128 }, mission_id: { type: 'string', minLength: 1, maxLength: 128 }, hermes_run_id: { type: 'string', minLength: 1, maxLength: 256 } }, required: ['decision_id', 'mission_id', 'hermes_run_id'], additionalProperties: false } },
  { name: 'runtime_status', description: 'Read VAN owner-runtime health and capability status.', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'mission_result', description: 'Report this Hermes run lifecycle result to the bound Mission. COMPLETED starts gateway verification; this tool cannot assert verified success.', inputSchema: { type: 'object', properties: { hermes_run_id: { type: 'string', minLength: 1, maxLength: 256 }, status: { type: 'string', enum: ['COMPLETED', 'FAILED', 'WAITING_FOR_OWNER', 'WAITING_EXTERNAL'] }, summary: { type: 'string', maxLength: 4000 } }, required: ['hermes_run_id', 'status'], additionalProperties: false } },
  { name: 'resolve_command', description: 'Deterministically resolve a known owner command without granting execution authority.', inputSchema: { type: 'object', properties: { text: { type: 'string' } }, required: ['text'], additionalProperties: false } },
  { name: 'assumption_record', description: 'Record a planning assumption for this Mission. HIGH and CRITICAL assumptions restrict irreversible work; recording never grants authority.', inputSchema: { type: 'object', properties: { mission_id: { type: 'string', minLength: 1, maxLength: 256 }, claim: { type: 'string', minLength: 1, maxLength: 2000 }, source: { type: 'string', minLength: 1, maxLength: 256 }, importance: { type: 'string', enum: ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'] }, confidence: { type: 'number', minimum: 0, maximum: 1 }, testability: { type: 'string', maxLength: 64 }, verification_plan: { type: ['string', 'null'], maxLength: 2000 } }, required: ['mission_id', 'claim', 'source'], additionalProperties: false } },
  { name: 'assumption_blocking', description: 'Read the unresolved HIGH/CRITICAL assumptions blocking irreversible work on this Mission. A worker cannot clear them by supplying evidence-reference strings.', inputSchema: { type: 'object', properties: { mission_id: { type: 'string', minLength: 1, maxLength: 256 } }, required: ['mission_id'], additionalProperties: false } },
  { name: 'premise_record', description: 'Record an assessment of an owner factual premise and cited evidence for reasoning metrics. This records a model claim, does not admit owner truth or authorize execution; unsupported-agreement is derived by the gateway.', inputSchema: { type: 'object', properties: { owner_premise: { type: 'string', minLength: 1, maxLength: 4000 }, van_position: { type: 'string', minLength: 1, maxLength: 4000 }, semantic_class: { type: 'string', enum: ['FACT_VERIFIED', 'FACT_UNVERIFIED', 'OWNER_PREFERENCE', 'OWNER_INSTRUCTION', 'MODEL_INFERENCE', 'HYPOTHESIS', 'FORECAST', 'EXTERNAL_CLAIM', 'PROJECT_TRUTH'] }, evidence_refs: { type: 'array', items: { type: 'string' } }, corrected: { type: 'boolean' }, mission_id: { type: ['string', 'null'], maxLength: 256 } }, required: ['owner_premise', 'van_position', 'semantic_class'], additionalProperties: false } },
  { name: 'context_graph_query', description: 'Query the bounded temporal owner-context graph. This retrieves evidence; it does not decide truth.', inputSchema: { type: 'object', properties: { seed_nodes: { type: 'array', items: { type: 'string' }, minItems: 1, maxItems: 32 }, scope: { type: 'string' }, direction: { type: 'string', enum: ['OUT', 'IN', 'BOTH'] }, predicates: { type: 'array', items: { type: 'string' } }, max_depth: { type: 'integer', minimum: 1, maximum: 3 }, max_edges: { type: 'integer', minimum: 1, maximum: 256 }, allow_inferred: { type: 'boolean' }, min_confidence_permille: { type: 'integer', minimum: 0, maximum: 1000 } }, required: ['seed_nodes'], additionalProperties: false } },
  { name: 'context_lexical_query', description: 'Run deterministic local lexical/entity retrieval over current owner facts and graph edges. No embedding, model inference or remote call is used.', inputSchema: { type: 'object', properties: { query: { type: 'string', minLength: 1, maxLength: 256 }, scope: { type: 'string' }, max_results: { type: 'integer', minimum: 1, maximum: 64 }, allow_inferred: { type: 'boolean' }, include_facts: { type: 'boolean' }, include_edges: { type: 'boolean' } }, required: ['query'], additionalProperties: false } },
  { name: 'context_hot_capsule', description: 'Compile or retrieve a bounded revision-sealed hot-context evidence capsule for an active workstream. This is a cache of evidence references, not a truth store.', inputSchema: { type: 'object', properties: { scopes: { type: 'array', items: { type: 'string' }, minItems: 1, maxItems: 8 }, requirements: { type: 'array', items: { type: 'object' }, maxItems: 32 }, seed_nodes: { type: 'array', items: { type: 'string' }, maxItems: 16 }, lexical_queries: { type: 'array', items: { type: 'string', maxLength: 256 }, maxItems: 8 }, allow_inferred: { type: 'boolean' }, graph_depth: { type: 'integer', minimum: 1, maximum: 2 }, max_graph_edges: { type: 'integer', minimum: 1, maximum: 96 }, max_lexical_hits_per_query: { type: 'integer', minimum: 1, maximum: 24 }, ttl_ms: { type: 'integer', minimum: 1000, maximum: 300000 } }, additionalProperties: false } },
  { name: 'context_readiness', description: 'Resolve exact canonical context requirements and report CURRENT/STALE/MISSING/CONFLICTED.', inputSchema: { type: 'object', properties: { command_id: { type: 'string' }, requirements: { type: 'array', items: { type: 'object' } } }, required: ['command_id', 'requirements'], additionalProperties: false } },
  { name: 'context_snapshot', description: 'Seal an immutable context snapshot after readiness succeeds.', inputSchema: { type: 'object', properties: { command_id: { type: 'string' }, requirements: { type: 'array', items: { type: 'object' } }, graph_evidence_refs: { type: 'array', items: { type: 'string' } }, lexical_evidence_refs: { type: 'array', items: { type: 'string' } }, knowledge_evidence_refs: { type: 'array', items: { type: 'string' } }, live_state_refs: { type: 'array', items: { type: 'string' } }, policy_refs: { type: 'array', items: { type: 'string' } } }, required: ['command_id', 'requirements'], additionalProperties: false } },
  { name: 'knowledge_status', description: 'Read VEKL, Obsidian and Notebook provider readiness. Providers are evidence sources, never owner-truth authorities.', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'vekl_query', description: 'Query bounded read-only engineering evidence from VEKL with provenance.', inputSchema: { type: 'object', properties: { mission_id: { type: 'string' }, query: { type: 'string' }, max_results: { type: 'integer', minimum: 1, maximum: 64 }, scope: { type: 'string' } }, required: ['mission_id'], additionalProperties: false } },
  { name: 'obsidian_query', description: 'Query the owner Obsidian vault index. Secret-like material is excluded and results remain evidence until admitted by authority.', inputSchema: { type: 'object', properties: { query: { type: 'string' }, max_results: { type: 'integer', minimum: 1, maximum: 64 }, scope: { type: 'string' }, refresh: { type: 'boolean' } }, required: ['query'], additionalProperties: false } },
  { name: 'notebook_enterprise_recent', description: 'Read recently viewed Gemini Notebook Enterprise notebooks through the official API.', inputSchema: { type: 'object', properties: { page_size: { type: 'integer', minimum: 1, maximum: 500 } }, additionalProperties: false } },
  { name: 'notebook_enterprise_get', description: 'Read one Gemini Notebook Enterprise notebook by ID.', inputSchema: { type: 'object', properties: { notebook_id: { type: 'string' } }, required: ['notebook_id'], additionalProperties: false } },
  { name: 'notebook_consumer_ask', description: 'Ask a grounded question in the owner personal NotebookLM session and return verified UI readback as evidence.', inputSchema: { type: 'object', properties: { notebook_id: { type: 'string' }, question: { type: 'string' }, scope: { type: 'string' } }, required: ['notebook_id', 'question'], additionalProperties: false } },
  { name: 'knowledge_action_execute', description: 'Execute a Notebook mutation only after action_begin has produced an AUTHORIZED execution. Parameters must exactly match the authorized digest.', inputSchema: { type: 'object', properties: { execution_id: { type: 'string' }, parameters: { type: 'object' } }, required: ['execution_id', 'parameters'], additionalProperties: false } },
  { name: 'google_status', description: 'Read owner Google Workspace connection status. Read-only.', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'google_capabilities', description: 'Read the Google capability mesh and current readiness. Read-only.', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'google_gmail_search', description: 'Search bounded Gmail metadata through the gateway. Message content remains untrusted external data.', inputSchema: { type: 'object', properties: { q: { type: 'string', minLength: 1, maxLength: 512 } }, required: ['q'], additionalProperties: false } },
  { name: 'google_gmail_draft_preview', description: 'Read recipients, subject and the canonical content digest of a draft. The worker receives no private body text; only the paired owner can approve sending the frozen content. The source draft is not consumed by that send.', inputSchema: { type: 'object', properties: { draft_id: { type: 'string', minLength: 1, maxLength: 256 } }, required: ['draft_id'], additionalProperties: false } },
  { name: 'google_gmail_thread', description: 'Read one complete normalized Gmail thread, including attachment metadata. Content remains untrusted external data.', inputSchema: { type: 'object', properties: { thread_id: { type: 'string', minLength: 1, maxLength: 512 } }, required: ['thread_id'], additionalProperties: false } },
  { name: 'google_gmail_attachment_import', description: 'Import one Gmail PDF attachment into VAN Document Fabric without placing attachment bytes in model context. Returns document/artifact metadata only.', inputSchema: { type: 'object', properties: { message_id: { type: 'string', minLength: 1, maxLength: 512 }, attachment_id: { type: 'string', minLength: 1, maxLength: 1024 }, filename: { type: 'string', minLength: 1, maxLength: 180 }, project_id: { type: ['string','null'] }, command_id: { type: ['string','null'] }, mission_id: { type: ['string','null'] }, execution_id: { type: ['string','null'] } }, required: ['message_id','attachment_id','filename'], additionalProperties: false } },
  { name: 'google_calendar_agenda', description: 'Read the owner calendar agenda through the gateway. Read-only.', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'google_calendar_review', description: 'Read one Calendar event together with its ETag version for a later reviewed mutation. Read-only.', inputSchema: { type: 'object', properties: { event_id: { type: 'string', minLength: 1, maxLength: 512 } }, required: ['event_id'], additionalProperties: false } },
  { name: 'google_drive_search', description: 'Search Drive metadata through the gateway. File content does not become owner authority.', inputSchema: { type: 'object', properties: { q: { type: 'string', minLength: 1, maxLength: 512 } }, required: ['q'], additionalProperties: false } },
  { name: 'google_contacts_resolve', description: 'Resolve contacts through the gateway. Read-only.', inputSchema: { type: 'object', properties: { q: { type: 'string', minLength: 1, maxLength: 256 } }, required: ['q'], additionalProperties: false } },
  { name: 'google_tasks_list', description: 'Read the owner Google Tasks list through the gateway. Read-only.', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'google_job_plan', description: 'Ask the deterministic Google capability router to plan a job. Planning does not execute a mutation or grant approval.', inputSchema: { type: 'object', properties: { owner_intent_id: { type: 'string', minLength: 1, maxLength: 256 }, intent: { type: 'string', minLength: 1, maxLength: 128 }, action_class: { type: 'string', enum: ['A1','A2','A3','A4','A5'] }, project_id: { type: ['string','null'] }, truth_sha: { type: ['string','null'] }, grant_id: { type: ['string','null'] }, owner_approved: { type: 'boolean' }, input_refs: { type: 'array', items: { type: 'string' }, maxItems: 64 }, constraints: { type: 'object' } }, required: ['owner_intent_id','intent'], additionalProperties: false } },
  { name: 'google_job_get', description: 'Read one planned Google job and its lineage. PLANNED and ARTIFACT_RECORDED do not prove provider execution or verified completion.', inputSchema: { type: 'object', properties: { job_id: { type: 'string', minLength: 1, maxLength: 256 } }, required: ['job_id'], additionalProperties: false } },
  { name: 'google_artifact_record', description: 'Record bounded Google output hash and input lineage as untrusted pending evidence. This tool cannot admit owner truth or mark a job verified.', inputSchema: { type: 'object', properties: { job_id: { type: 'string', minLength: 1, maxLength: 256 }, source_tool: { type: 'string', minLength: 1, maxLength: 128 }, output_hash: { type: 'string', pattern: '^[a-f0-9]{64}$' }, project_id: { type: ['string','null'], maxLength: 256 }, tool_version: { type: ['string','null'], maxLength: 128 }, input_hashes: { type: 'array', items: { type: 'string', pattern: '^[a-f0-9]{64}$' }, maxItems: 64 }, parent_artifact_ids: { type: 'array', items: { type: 'string', maxLength: 256 }, maxItems: 64 } }, required: ['job_id','source_tool','output_hash'], additionalProperties: false } },
  { name: 'google_action_execute', description: 'Execute a Google Workspace mutation only by execution_id after action_begin has produced AUTHORIZED. This tool has no approval field.', inputSchema: { type: 'object', properties: { execution_id: { type: 'string', minLength: 1, maxLength: 256 }, parameters: { type: 'object' } }, required: ['execution_id','parameters'], additionalProperties: false } },
  { name: 'research_status', description: 'Read gateway-mediated external research readiness.', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'research_search', description: 'Run bounded gateway-mediated research. External evidence remains untrusted until admitted by policy.', inputSchema: { type: 'object', properties: { query: { type: 'string' }, mode: { type: 'string' }, egress_class: { type: 'string' }, max_results: { type: 'integer' }, owner_approved_sensitive_egress: { type: 'boolean' } }, required: ['query'], additionalProperties: false } },
  { name: 'action_begin', description: 'Request gateway authorization for a registered typed action bound to signed command authority.', inputSchema: { type: 'object', properties: { execution_id: { type: 'string' }, command_id: { type: 'string' }, turn_id: { type: ['string', 'null'] }, action_id: { type: 'string' }, principal_type: { type: 'string' }, requested_by: { type: 'string' }, idempotency_key: { type: 'string' }, parameters: { type: 'object' }, snapshot_id: { type: ['string', 'null'] } }, required: ['execution_id', 'command_id', 'action_id', 'principal_type', 'requested_by', 'idempotency_key'], additionalProperties: false } },
  { name: 'action_submitted', description: 'Record provider acceptance/correlation for an authorized action. This is not completion.', inputSchema: { type: 'object', properties: { execution_id: { type: 'string' }, correlation: { type: 'object' }, evidence_pointer: { type: ['string', 'null'] } }, required: ['execution_id'], additionalProperties: false } },
  { name: 'action_verify', description: 'Submit observed postconditions for deterministic gateway verification.', inputSchema: { type: 'object', properties: { execution_id: { type: 'string' }, success: { type: 'boolean' }, correlation: { type: 'object' }, observed_postcondition: { type: 'object' }, evidence_pointer: { type: ['string', 'null'] }, error_code: { type: ['string', 'null'] } }, required: ['execution_id', 'success'], additionalProperties: false } },
  { name: 'action_get', description: 'Read the authoritative execution state for one action execution.', inputSchema: { type: 'object', properties: { execution_id: { type: 'string' } }, required: ['execution_id'], additionalProperties: false } },
  { name: 'context_fact_candidate', description: 'Propose an INFERRED/MODEL_DERIVED owner-fact candidate for later owner review. The gateway route enforces authority=INFERRED and source_trust=MODEL_DERIVED and refuses (403) anything else; this tool can never admit canonical owner truth and is not the "remember that..." path (that is an owner-signed typed action).', inputSchema: { type: 'object', properties: { fact_id: { type: 'string', minLength: 1, maxLength: 256 }, subject: { type: 'string', minLength: 1, maxLength: 512 }, predicate: { type: 'string', minLength: 1, maxLength: 256 }, value: {}, authority: { type: 'string', enum: ['INFERRED'] }, source_trust: { type: 'string', enum: ['MODEL_DERIVED'] }, source_ref: { type: 'string', minLength: 1, maxLength: 512 }, confidence_permille: { type: 'integer', minimum: 0, maximum: 1000 }, confidence_profile_version: { type: 'integer', minimum: 1 }, scope: { type: 'string' }, valid_from_ms: { type: 'integer' }, valid_until_ms: { type: ['integer', 'null'] }, observed_at_ms: { type: 'integer' }, last_verified_at_ms: { type: ['integer', 'null'] }, sensitivity: { type: 'string', enum: ['PUBLIC', 'OWNER_PRIVATE', 'SENSITIVE', 'SECRET'] }, supersedes_fact_id: { type: ['string', 'null'] } }, required: ['fact_id', 'subject', 'predicate', 'value', 'authority', 'source_trust', 'source_ref', 'valid_from_ms', 'observed_at_ms'], additionalProperties: false } },
  { name: 'context_edge_candidate', description: 'Propose an INFERRED/MODEL_DERIVED owner-context edge candidate for later owner review. Same authority gate as context_fact_candidate: authority=INFERRED and source_trust=MODEL_DERIVED only, or the gateway refuses with 403.', inputSchema: { type: 'object', properties: { edge_id: { type: 'string', minLength: 1, maxLength: 256 }, from_node: { type: 'string', minLength: 1, maxLength: 512 }, predicate: { type: 'string', minLength: 1, maxLength: 256 }, to_node: { type: 'string', minLength: 1, maxLength: 512 }, scope: { type: 'string' }, authority: { type: 'string', enum: ['INFERRED'] }, source_trust: { type: 'string', enum: ['MODEL_DERIVED'] }, source_ref: { type: 'string', minLength: 1, maxLength: 512 }, confidence_permille: { type: 'integer', minimum: 0, maximum: 1000 }, confidence_profile_version: { type: 'integer', minimum: 1 }, valid_from_ms: { type: 'integer' }, valid_until_ms: { type: ['integer', 'null'] }, observed_at_ms: { type: 'integer' }, sensitivity: { type: 'string', enum: ['PUBLIC', 'OWNER_PRIVATE', 'SENSITIVE', 'SECRET'] }, supersedes_edge_id: { type: ['string', 'null'] } }, required: ['edge_id', 'from_node', 'predicate', 'to_node', 'authority', 'source_trust', 'source_ref', 'valid_from_ms', 'observed_at_ms'], additionalProperties: false } },
  { name: 'trading_portfolio', description: 'Read-only VATI ledger portfolio read model: accounts, totals, risk, exposure, recent trades and open/potential positions. Hermes cannot place, size, modify, cancel or halt anything through this tool.', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'trading_positions', description: 'Read-only currently open trading positions, from the same portfolio read model the owner Command Centre shows. Evidence for analysis only; never a path to size, modify or close a position.', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'trading_risk', description: 'Read-only VATI Risk Authority read model: concentration and per-position risk. Read-only; VATI remains the sole risk-decision authority.', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'trading_market_state', description: 'Read-only market-state read model for one symbol, or all tracked symbols when omitted. Read-only evidence, not a trade signal.', inputSchema: { type: 'object', properties: { symbol: { type: 'string', maxLength: 32 } }, additionalProperties: false } },
  { name: 'trading_trade_detail', description: 'Read-only detail for one trade intent from the VATI ledger. Read-only evidence for analysis and trade review.', inputSchema: { type: 'object', properties: { trade_intent_id: { type: 'string', minLength: 1, maxLength: 256 } }, required: ['trade_intent_id'], additionalProperties: false } },
  { name: 'trading_status', description: 'Read-only VATI ledger health: chain integrity, event counts, kill-switch state, open ticket count and ledger staleness. Read-only; the halt and ticket-confirm routes are owner-signed (A4) and not reachable from here.', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'reminder_create', description: 'Create a reminder on the owner\'s behalf. `text` must be the owner\'s own words, not a paraphrase or summary -- this is not a memory-admission path and creates no canonical owner fact. The due time is parsed deterministically server-side (no model interprets it).', inputSchema: { type: 'object', properties: { text: { type: 'string', minLength: 1, maxLength: 2000 }, due_expression: { type: 'string', minLength: 1, maxLength: 128 }, mission_id: { type: 'string', maxLength: 256 } }, required: ['text', 'due_expression'], additionalProperties: false } },
  { name: 'suggestion_create', description: 'Surface one evidence-backed suggestion to the owner. This creates an Attention item only; it cannot execute the proposed prompt. source_refs are mandatory and must name evidence VAN can inspect.', inputSchema: { type: 'object', properties: { title: { type: 'string', minLength: 1, maxLength: 300 }, rationale: { type: 'string', minLength: 1, maxLength: 4000 }, proposed_prompt: { type: 'string', minLength: 1, maxLength: 8000 }, source_refs: { type: 'array', items: { type: 'string', minLength: 1, maxLength: 2000 }, minItems: 1, maxItems: 100 }, project_id: { type: ['string', 'null'], maxLength: 256 } }, required: ['title', 'rationale', 'proposed_prompt', 'source_refs'], additionalProperties: false } },
  { name: 'attention_list', description: 'Read the open owner attention queue (post-scoring, post-dedupe, post-budget). Read-only; cannot acknowledge, snooze or resolve an item.', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'briefing_read', description: 'Read the deterministic owner briefing (needs-you-now, today, waiting-on-others, projects-at-risk, messages, recent completions, handled, lower-priority). Read-only; never invents missing data.', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'browser_task_create', description: 'Create the browser task browser_assignment_run then runs. Mirrors backend/van_gateway/browser/api.py\'s CreateTaskBody exactly: no approval or owner-signature field exists on this route. Unlike browser_assignment_run, task creation itself carries no turn_id -- pass command_id (and mission_id, to bind the task as a Mission Activity) so the task is anchored to this run, and supply the assigning turn_id when you call browser_assignment_run with the task_id this returns.', inputSchema: { type: 'object', properties: { profile_alias: { type: 'string', minLength: 1 }, strategy: { type: 'string', enum: ['DIRECT_HTTP', 'HARNESS', 'STAGEHAND'] }, autonomy_tier: { type: 'string', enum: ['L0_API', 'L1_HARNESS_DETERMINISTIC', 'L2_STAGEHAND_CACHED', 'L3_STAGEHAND_OBSERVE', 'L4_STAGEHAND_ACT', 'L5_STAGEHAND_AGENT'] }, action_class: { type: 'string', enum: ['A1', 'A2', 'A3', 'A4', 'A5'] }, target_domain: { type: 'string', minLength: 1 }, goal: { type: 'string', minLength: 1 }, mutating: { type: 'boolean' }, command_id: { type: ['string', 'null'] }, execution_id: { type: ['string', 'null'] }, capability_id: { type: ['string', 'null'] }, mission_id: { type: ['string', 'null'] }, inputs: { type: 'object' } }, required: ['profile_alias', 'strategy', 'autonomy_tier', 'action_class', 'target_domain', 'goal'], additionalProperties: false } },
  { name: 'browser_assignment_run', description: 'Run a bounded browser subagent assignment against an already-created browser task. §379: this is the only way a browser worker runs autonomously; the runner enforces the domain scope, action-class ceiling and step budget given here, not the worker. Set interactive_session_id to use the exact owner-delegated stream target with a supported deterministic plan; this never creates owner delegation. task_id, turn_id and command_id must be this run\'s own -- an assignment with no assigning turn is refused.', inputSchema: { type: 'object', properties: { task_id: { type: 'string', minLength: 1 }, turn_id: { type: 'string', minLength: 1 }, command_id: { type: 'string', minLength: 1 }, goal: { type: 'string', minLength: 1 }, allowed_domains: { type: 'array', items: { type: 'string' }, minItems: 1 }, action_class_ceiling: { type: 'string', enum: ['A1', 'A2', 'A3', 'A4', 'A5'] }, autonomy_tier: { type: 'string', enum: ['L0_API', 'L1_HARNESS_DETERMINISTIC', 'L2_STAGEHAND_CACHED', 'L3_STAGEHAND_OBSERVE', 'L4_STAGEHAND_ACT', 'L5_STAGEHAND_AGENT'] }, max_steps: { type: 'integer', minimum: 1, maximum: 50 }, deadline_ms: { type: ['integer', 'null'] }, max_steps_without_progress: { type: 'integer', minimum: 1, maximum: 10 }, plan: { type: ['object', 'null'] }, interactive_session_id: { type: ['string', 'null'], minLength: 1, maxLength: 128 } }, required: ['task_id', 'turn_id', 'command_id', 'goal', 'allowed_domains'], additionalProperties: false } },
  { name: 'browser_task_status', description: 'Read one browser task and its evidence summary.', inputSchema: { type: 'object', properties: { task_id: { type: 'string', minLength: 1 } }, required: ['task_id'], additionalProperties: false } },
  { name: 'browser_control_grant_issue', description: 'Issue a bounded narrow CDP task grant for an existing Mission browser task on an owner-delegated interactive session. The gateway verifies the actual task, Mission, target, profile lease, delegated control lease and admitted service proxy. This cannot delegate owner control, select arbitrary CDP or reset a previously spent task budget. The proxy fingerprint is a non-secret configured credential fingerprint, never the credential itself.', inputSchema: { type: 'object', properties: { task_id: { type: 'string', minLength: 1, maxLength: 128 }, session_id: { type: 'string', minLength: 1, maxLength: 128 }, target_id: { type: 'string', minLength: 1, maxLength: 128 }, caller_common_name: { type: 'string', minLength: 1, maxLength: 128 }, proxy_principal_sha256: { type: 'string', pattern: '^[0-9a-f]{64}$' }, scope: { type: 'string', enum: ['browser.observe', 'browser.actuate', 'browser.evidence'] }, step_budget: { type: 'integer', minimum: 1, maximum: 50 }, deadline_ms: { type: 'integer', minimum: 1 } }, required: ['task_id', 'session_id', 'target_id', 'caller_common_name', 'proxy_principal_sha256', 'scope', 'step_budget', 'deadline_ms'], additionalProperties: false } },
  { name: 'browser_task_evidence', description: 'Read the sealed evidence records for one browser task (digests only; never raw cookies or credentials).', inputSchema: { type: 'object', properties: { task_id: { type: 'string', minLength: 1 } }, required: ['task_id'], additionalProperties: false } },
  { name: 'automation_route', description: 'Ask the deterministic Automation Fabric router which medium (native/hot workflow/cold generation/browser) serves a goal. Routing only; it does not compile, admit or run anything.', inputSchema: { type: 'object', properties: { goal: { type: 'string', minLength: 1 }, signature: { type: 'object', properties: { goal_class: { type: 'string' }, source_class: { type: 'string' }, destination_class: { type: 'string' }, mutation_class: { type: 'string', enum: ['A1', 'A2', 'A3', 'A4', 'A5'] } }, required: ['goal_class', 'source_class', 'destination_class', 'mutation_class'], additionalProperties: false }, native_capability_id: { type: ['string', 'null'] }, web_only: { type: 'boolean' }, known_browser_capsule_id: { type: ['string', 'null'] }, critical_durable: { type: 'boolean' }, wants_reuse: { type: 'boolean' } }, required: ['goal', 'signature'], additionalProperties: false } },
  { name: 'automation_execute', description: 'Execute an already-admitted automation capability under an existing signed command authority. There is no action-class or approval field: both come from the sealed command record named by command_id, so this tool cannot escalate one.', inputSchema: { type: 'object', properties: { capability_id: { type: 'string', minLength: 1 }, action_id: { type: 'string', minLength: 1 }, command_id: { type: 'string', minLength: 1 }, snapshot_id: { type: 'string', minLength: 1 }, requested_by: { type: 'string', minLength: 1 }, principal_type: { type: 'string' }, inputs: { type: 'object' }, turn_id: { type: ['string', 'null'] }, standing_authority_id: { type: ['string', 'null'] }, mission_id: { type: ['string', 'null'] } }, required: ['capability_id', 'action_id', 'command_id', 'snapshot_id', 'requested_by', 'principal_type'], additionalProperties: false } },
  { name: 'automation_run_status', description: 'Read the persisted status of one automation run by run_id (as returned by automation_execute). Read-only.', inputSchema: { type: 'object', properties: { run_id: { type: 'string', minLength: 1 } }, required: ['run_id'], additionalProperties: false } },
  { name: 'temporal_start', description: 'Start or idempotently recover one critical durable Temporal coordination workflow. Temporal owns durable state/waits only; it never grants trading or owner authority.', inputSchema: { type: 'object', properties: { workflow_id: { type: 'string', minLength: 3, maxLength: 256 }, process_kind: { type: 'string', minLength: 1, maxLength: 128 }, idempotency_key: { type: 'string', minLength: 8, maxLength: 256 }, payload: { type: 'object' }, timeout_seconds: { type: 'integer', minimum: 1, maximum: 2592000 } }, required: ['workflow_id', 'process_kind', 'idempotency_key'], additionalProperties: false } },
  { name: 'temporal_status', description: 'Read the queryable state of one critical durable Temporal workflow.', inputSchema: { type: 'object', properties: { workflow_id: { type: 'string', minLength: 3, maxLength: 256 } }, required: ['workflow_id'], additionalProperties: false } },
  { name: 'temporal_signal', description: 'Signal a durable Temporal workflow with an explicit checkpoint or terminal outcome. This does not itself perform the domain mutation.', inputSchema: { type: 'object', properties: { workflow_id: { type: 'string', minLength: 3, maxLength: 256 }, command: { type: 'string', enum: ['COMPLETE', 'FAIL', 'CANCEL', 'CHECKPOINT'] }, detail: { type: 'string', maxLength: 4000 }, evidence_pointer: { type: ['string', 'null'], maxLength: 2000 }, payload: { type: 'object' } }, required: ['workflow_id', 'command'], additionalProperties: false } },
];

const ROUTES = {
  mission_control_poll: { method: 'POST', path: () => '/v1/runtime/missions/control/poll', body: (a) => a },
  mission_control_ack: { method: 'POST', path: () => '/v1/runtime/missions/control/ack', body: (a) => a },
  decision_escalate: { method: 'POST', path: () => '/v1/runtime/decisions/escalate', body: (a) => a },
  decision_read: { method: 'GET', path: (a) => `/v1/runtime/decisions/${encodeURIComponent(a.decision_id)}?mission_id=${encodeURIComponent(a.mission_id)}&hermes_run_id=${encodeURIComponent(a.hermes_run_id)}` },
  runtime_status: { method: 'GET', path: () => '/v1/runtime/status' },
  mission_result: { method: 'POST', path: () => '/v1/runtime/missions/result', body: (a) => a },
  resolve_command: { method: 'POST', path: () => '/v1/runtime/resolve', body: (a) => a },
  assumption_record: { method: 'POST', path: () => '/v1/runtime/reasoning/assumptions', body: (a) => a },
  assumption_blocking: { method: 'GET', path: (a) => `/v1/runtime/reasoning/assumptions/${encodeURIComponent(a.mission_id)}` },
  premise_record: { method: 'POST', path: () => '/v1/runtime/reasoning/premises', body: (a) => a },
  context_graph_query: { method: 'POST', path: () => '/v1/runtime/context/graph/query', body: (a) => a },
  context_lexical_query: { method: 'POST', path: () => '/v1/runtime/context/lexical/query', body: (a) => a },
  context_hot_capsule: { method: 'POST', path: () => '/v1/runtime/context/hot-capsules', body: (a) => a },
  context_readiness: { method: 'POST', path: () => '/v1/runtime/context/readiness', body: (a) => a },
  context_snapshot: { method: 'POST', path: () => '/v1/runtime/context/snapshots', body: (a) => a },
  knowledge_status: { method: 'GET', path: () => '/v1/runtime/knowledge/status' },
  vekl_query: { method: 'POST', path: () => '/v1/runtime/knowledge/vekl/query', body: (a) => a },
  obsidian_query: { method: 'POST', path: () => '/v1/runtime/knowledge/obsidian/query', body: (a) => a },
  notebook_enterprise_recent: { method: 'GET', path: (a) => `/v1/runtime/knowledge/notebook/enterprise/recent?page_size=${encodeURIComponent(a.page_size || 100)}` },
  notebook_enterprise_get: { method: 'GET', path: (a) => `/v1/runtime/knowledge/notebook/enterprise/${encodeURIComponent(a.notebook_id)}` },
  notebook_consumer_ask: { method: 'POST', path: () => '/v1/runtime/knowledge/notebook/consumer/ask', body: (a) => a },
  knowledge_action_execute: { method: 'POST', path: () => '/v1/runtime/knowledge/actions/execute', body: (a) => a },
  google_status: { method: 'GET', path: () => '/v1/google/status' },
  google_capabilities: { method: 'GET', path: () => '/v1/google/capabilities' },
  google_gmail_search: { method: 'GET', path: (a) => `/v1/google/gmail/search?q=${encodeURIComponent(a.q)}` },
  google_gmail_draft_preview: { method: 'GET', path: (a) => `/v1/google/gmail/drafts/${encodeURIComponent(a.draft_id)}/preview` },
  google_gmail_thread: { method: 'GET', path: (a) => `/v1/google/gmail/thread?thread_id=${encodeURIComponent(a.thread_id)}` },
  google_gmail_attachment_import: { method: 'POST', path: (a) => `/v1/google/gmail/attachment/import-pdf?message_id=${encodeURIComponent(a.message_id)}&attachment_id=${encodeURIComponent(a.attachment_id)}&filename=${encodeURIComponent(a.filename)}${a.project_id ? `&project_id=${encodeURIComponent(a.project_id)}` : ''}${a.command_id ? `&command_id=${encodeURIComponent(a.command_id)}` : ''}${a.mission_id ? `&mission_id=${encodeURIComponent(a.mission_id)}` : ''}${a.execution_id ? `&execution_id=${encodeURIComponent(a.execution_id)}` : ''}` },
  google_calendar_agenda: { method: 'GET', path: () => '/v1/google/calendar/agenda' },
  google_calendar_review: { method: 'GET', path: (a) => `/v1/google/calendar/review?event_id=${encodeURIComponent(a.event_id)}` },
  google_drive_search: { method: 'GET', path: (a) => `/v1/google/drive/search?q=${encodeURIComponent(a.q)}` },
  google_contacts_resolve: { method: 'GET', path: (a) => `/v1/google/contacts/resolve?q=${encodeURIComponent(a.q)}` },
  google_tasks_list: { method: 'GET', path: () => '/v1/google/tasks' },
  google_job_plan: { method: 'POST', path: () => '/v1/google/jobs/plan', body: (a) => a },
  google_job_get: { method: 'GET', path: (a) => `/v1/google/jobs/${encodeURIComponent(a.job_id)}` },
  google_artifact_record: { method: 'POST', path: (a) => `/v1/google/jobs/${encodeURIComponent(a.job_id)}/artifacts`, body: (a) => ({ source_tool: a.source_tool, output_hash: a.output_hash, project_id: a.project_id ?? null, tool_version: a.tool_version ?? null, input_hashes: a.input_hashes || [], parent_artifact_ids: a.parent_artifact_ids || [], trust: 'UNTRUSTED', validation_state: 'PENDING' }) },
  google_action_execute: { method: 'POST', path: () => '/v1/google/actions/execute', body: (a) => a },
  research_status: { method: 'GET', path: () => '/v1/runtime/research/status' },
  research_search: { method: 'POST', path: () => '/v1/runtime/research/search', body: (a) => a },
  action_begin: { method: 'POST', path: () => '/v1/runtime/actions/begin', body: (a) => a },
  action_submitted: { method: 'POST', path: (a) => `/v1/runtime/actions/${encodeURIComponent(a.execution_id)}/submitted`, body: (a) => ({ correlation: a.correlation || {}, evidence_pointer: a.evidence_pointer ?? null }) },
  action_verify: { method: 'POST', path: () => '/v1/runtime/actions/verify', body: (a) => a },
  action_get: { method: 'GET', path: (a) => `/v1/runtime/actions/${encodeURIComponent(a.execution_id)}` },
  context_fact_candidate: { method: 'POST', path: () => '/v1/runtime/context/facts', body: (a) => a },
  context_edge_candidate: { method: 'POST', path: () => '/v1/runtime/context/edges', body: (a) => a },
  trading_portfolio: { method: 'GET', path: () => '/v1/runtime/trading/portfolio' },
  trading_positions: { method: 'GET', path: () => '/v1/runtime/trading/positions' },
  trading_risk: { method: 'GET', path: () => '/v1/runtime/trading/risk' },
  trading_market_state: { method: 'GET', path: (a) => `/v1/runtime/trading/market-state${a.symbol ? `?symbol=${encodeURIComponent(a.symbol)}` : ''}` },
  trading_trade_detail: { method: 'GET', path: (a) => `/v1/runtime/trading/trade/${encodeURIComponent(a.trade_intent_id)}` },
  trading_status: { method: 'GET', path: () => '/v1/runtime/trading/status' },
  reminder_create: { method: 'POST', path: () => '/v1/runtime/reminders', body: (a) => a },
  suggestion_create: { method: 'POST', path: () => '/v1/runtime/suggestions', body: (a) => a },
  attention_list: { method: 'GET', path: () => '/v1/runtime/attention' },
  briefing_read: { method: 'GET', path: () => '/v1/runtime/briefing' },
  browser_task_create: { method: 'POST', path: () => '/v1/browser/tasks', body: (a) => a },
  browser_assignment_run: { method: 'POST', path: () => '/v1/browser/assignments', body: (a) => a },
  browser_task_status: { method: 'GET', path: (a) => `/v1/browser/tasks/${encodeURIComponent(a.task_id)}` },
  browser_control_grant_issue: { method: 'POST', path: () => '/v1/browser/control-producer/grants', body: (a) => a },
  browser_task_evidence: { method: 'GET', path: (a) => `/v1/browser/tasks/${encodeURIComponent(a.task_id)}/evidence` },
  automation_route: { method: 'POST', path: () => '/v1/automation/route', body: (a) => a },
  automation_execute: { method: 'POST', path: () => '/v1/automation/execute', body: (a) => a },
  automation_run_status: { method: 'GET', path: (a) => `/v1/runtime/automation/runs/${encodeURIComponent(a.run_id)}` },
  temporal_start: { method: 'POST', path: () => '/v1/automation/temporal/start', body: (a) => a },
  temporal_status: { method: 'GET', path: (a) => `/v1/automation/temporal/${encodeURIComponent(a.workflow_id)}` },
  temporal_signal: { method: 'POST', path: (a) => `/v1/automation/temporal/${encodeURIComponent(a.workflow_id)}/signal`, body: (a) => ({ command: a.command, detail: a.detail || '', evidence_pointer: a.evidence_pointer ?? null, payload: a.payload || {} }) },
};

async function callRuntime(name, args) {
  if (!TOKEN) throw new Error('owner runtime internal-control credential unavailable');
  const route = ROUTES[name];
  if (!route) throw new Error('tool not allowed');
  const method = route.method;
  const targetPath = route.path(args || {});
  const bodyObj = route.body ? route.body(args || {}) : undefined;
  const options = { method, redirect: 'error', signal: AbortSignal.timeout(90_000),
    headers: { 'x-van-internal-token': TOKEN, 'content-type': 'application/json' } };
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
