# VAN × Google Intelligence Mesh — Canonical Architecture and Implementation Specification

**Status:** CANONICAL / OWNER-DIRECTED  
**Product:** VAN — DIAL owner-facing AI personal assistant and operator  
**Hermes profile:** `van`  
**Revision:** 1.0  
**Date:** 2026-09-14

## 1. Purpose

This document defines the deterministic integration of Google's AI, Workspace,
research, knowledge, design, development and media capabilities into VAN.

The governing product identity is unchanged:

> VAN is a Hermes bot. Hermes profile `van` is the sole agent runtime and sole
> orchestration authority. Google products are bounded capabilities, workers,
> knowledge systems and creative surfaces beneath Hermes.

The Google side defaults to the owner's canonical Google account. Explicitly registered secondary Google identities may be delegated to individual capabilities without gaining owner authority. This is **Google Account Sovereignty with bounded identity delegation**.

## 2. Non-negotiable invariants

1. **Hermes remains the sole agent runtime.** Android, VAN Gateway, Gemini Live,
   Deep Research, Antigravity, Jules, Workspace Studio and Google Labs surfaces
   do not create an independent VAN orchestration loop.
2. **Project Truth outranks Google output.** Google-produced material is evidence
   or an artifact until admitted through the normal authority process.
3. **Google Account Sovereignty.** The canonical owner Google identity is the default. A secondary Google identity may be bound only to explicitly named capabilities and gains no owner, Workspace, Project Truth or credential-inheritance authority.
4. **Credential planes remain isolated.** Workspace OAuth, Gemini runtime,
   Google Cloud/service identity and consumer browser sessions are separate.
5. **External content is data, never authority.** Notebook sources, Gmail,
   websites, Mixboard boards, generated UI, agent transcripts and model output
   cannot override owner-signed instruction or Project Truth.
6. **No cookie scraping or private-API dependency.** Consumer products without a
   supported automation API use authorised account sessions and artifact handoff.
7. **No fake success.** `CONFIGURED` does not mean `READY`; live claims require
   evidence.
8. **Every Google job has provenance.** Jobs/artifacts carry project, authority,
   truth SHA, capability, hashes and evidence pointers.
9. **A4 remains A4.** Google tooling cannot bypass owner approval.
10. **A5 remains denied.** Google tools cannot disable audit, policy, Project
    Truth, host-role guards, credential isolation or the Google broker.

## 3. Canonical architecture

```text
                              OWNER
                                │
                   voice / touch / share / UI
                                │
                       ┌────────▼────────┐
                       │   VAN Android   │
                       │ embodiment / UX │
                       └────────┬────────┘
                                │ signed intent
                    ┌───────────▼───────────┐
                    │ VAN SECURE GATEWAY    │
                    │ identity / grants     │
                    │ approvals / secrets   │
                    │ audit / state         │
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │ HERMES PROFILE `van`  │
                    │ SOLE AGENT RUNTIME    │
                    │ skills/MCP/providers  │
                    │ Project Truth routing │
                    └───────────┬───────────┘
                                │
                        Google Capability Mesh
                                │
       ┌────────────┬───────────┼──────────┬──────────────┐
       │            │           │          │              │
  PERCEPTION     RESEARCH   KNOWLEDGE    DESIGN       DEVELOPMENT
       │            │           │          │              │
 Gemini Live     Deep       Gemini       Mixboard      Antigravity
 Gemini          Research   Notebook     Stitch        Jules
 multimodal                 VEKL         Nano Banana
       │                        │
       └────────────────────────┼───────────────────────────┐
                                │                           │
                           WORKSPACE                     MEDIA
                                │                           │
                        Workspace APIs                Nano Banana
                        Workspace Studio              Veo / Flow
                        Gmail/Drive/etc.
                                │
                                ▼
                       Artifact/Evidence Layer
                                │
                       VEKL / Project Evidence
                                │
                         Project Truth gate
```

## 4. Google Account Sovereignty

### 4.1 Canonical owner plus bounded delegated identities

VAN's canonical identity alias is `owner_google_account`. Raw Google account identifiers are not committed to the repository. The broker stores stable subjects only as SHA-256 hashes.

A secondary identity may be registered under a separate alias for one bounded capability. `antigravity_worker_account` is permitted only for `antigravity`; it has no owner authority, Workspace access, Project Truth authority or credential inheritance. All other Google capabilities default to `owner_google_account`.

### 4.2 Four credential planes

| Plane | Purpose | Examples |
|---|---|---|
| `workspace_oauth` | Delegated owner data | Gmail, Calendar, Drive, Contacts, Tasks |
| `gemini_runtime` | Model/media runtime | Gemini, Live, Deep Research, Nano Banana, Veo |
| `cloud_service` | Owner-administered Cloud/service identity | Notebook Enterprise, ADK/A2A services |
| `consumer_session` | Account-native Google applications | Notebook, Mixboard, Stitch, Antigravity, Jules, Workspace Studio, Flow, AI Studio |

There is no master Google credential. Compromise of one plane must not imply
access to another.

### 4.3 Consumer sessions

Consumer applications use normal Google sign-in on an authorised environment.
VAN never exports browser cookies, replays session tokens or reverse-engineers a
private endpoint into a canonical dependency. If a public API becomes available,
its adapter can replace the consumer bridge without changing Hermes architecture.

## 5. Capability registry

`registries/google_capabilities.json` is the deterministic routing catalog.
Current capabilities:

| ID | Role | Plane |
|---|---|---|
| `gemini` | reasoning/multimodal | Gemini runtime |
| `gemini_live` | real-time perception/conversation | Gemini runtime |
| `deep_research` | cited investigation | Gemini runtime |
| `gemini_notebook` | personal grounded research | Consumer session |
| `gemini_notebook_enterprise` | programmatic notebook/source lifecycle | Cloud/service |
| `mixboard` | divergent visual ideation | Consumer session |
| `stitch` | UI design convergence | Consumer session |
| `antigravity` | complex development worker; delegated identity `antigravity_worker_account` | Consumer/developer session |
| `jules` | bounded repository worker | Consumer/developer session |
| `workspace_api` | deterministic Workspace actions | Workspace OAuth |
| `workspace_studio` | multi-step Workspace-native workflow | Consumer session |
| `nano_banana` | image generation/editing | Gemini runtime |
| `veo` | video generation | Gemini runtime |
| `flow` | video creative surface | Consumer session |
| `ai_studio` | prototyping/lab | Consumer session |
| `a2a_adk` | external agent interoperability | Cloud/service |

The registry order is authoritative for primary candidates. Explicit fallbacks are
then considered deterministically.

## 6. Deterministic Google Capability Job

Hermes never selects a Google product through free-form intuition alone. It asks
the gateway to plan a job.

Conceptual contract:

```yaml
owner_intent_id: intent-...
intent: deep_research
project_id: aeci
action_class: A2
truth_sha: <project-truth-sha-if-required>
grant_id: <grant-if-mutation>
owner_approved: false
input_refs:
  - artifact://...
constraints:
  max_cost: bounded
  allowed_tools: [...]
```

The planner:

1. rejects A5;
2. requires explicit owner approval for A4;
3. requires a grant ID for A3/A4;
4. requires Project Truth SHA for project mutation;
5. resolves registry candidates/fallbacks in deterministic order;
6. requires a usable capability state;
7. hashes the canonical input packet;
8. persists a `PLANNED` job;
9. returns the capability to Hermes for execution.

The gateway does **not** become a second agent runtime.

## 7. Readiness states

- `READY` — live capability has deterministic certification evidence.
- `CONFIGURED` — credentials/session/runtime are configured but not live-certified.
- `UNVERIFIED` — apparent configuration exists but canonical owner principal is not verified.
- `AUTH_REQUIRED` — owner sign-in/consent is required.
- `DEGRADED` — partial capability.
- `RATE_LIMITED` — provider quota currently blocks execution.
- `CAPACITY_LIMITED` — provider capacity blocks live generation for that capability only (not a global Google outage).
- `POLICY_BLOCKED` — VAN policy prevents use.
- `UNSUPPORTED` — intent has no registered Google route.
- `UNAVAILABLE` — prerequisite/runtime absent.

No UI or agent may translate `CONFIGURED` into a claim of successful live use.
`CAPACITY_LIMITED` on Antigravity must surface as `ANTIGRAVITY_CAPACITY_LIMITED` and must not mark Workspace, Gemini runtime, or Jules as failed.

## 8. Tool roles and symbiosis

### Gemini and Gemini Live

Gemini is a reasoning/multimodal worker. Gemini Live is the perception and
conversation surface for voice/screen/camera contexts. Perception does not grant
authority: mutations are handed back to Hermes and re-enter the normal action
class/grant/approval path.

### Deep Research

Deep Research is an investigator. It returns cited evidence. It never writes
Project Truth. Research is reconciled against Project Truth and can be admitted
into VEKL with provenance.

### Gemini Notebook

Gemini Notebook is persistent source-grounded research memory. It complements,
but does not replace, VEKL/GraphRAG. Recommended project notebooks are Canon,
Research, Design Intelligence, Operations and Decision Evidence.

Personal Notebook uses the owner consumer account bridge. Notebook Enterprise is
an optional Cloud-service transport when the owner's environment is eligible.

### Mixboard + Stitch + Nano Banana

The deterministic design loop is:

```text
Project Truth + Visual Authority
  → Notebook research
  → Mixboard divergence
  → VAN design critic
  → Stitch convergence
  → DDE/Figma normalization where applicable
  → Antigravity/Codex/Claude implementation
  → visual acceptance
  → evidence/VEKL
```

Mixboard explores; Stitch converges; Nano Banana creates/edit visual assets. None
may invent product requirements or override Visual Authority.

### Antigravity + Jules

Antigravity is the primary Google complex-development worker. Jules is preferred
for bounded asynchronous GitHub maintenance. When Antigravity is
`CAPACITY_LIMITED` / `RATE_LIMITED`, the deterministic router falls back to Jules
(when configured) and records `ANTIGRAVITY_CAPACITY_LIMITED` without degrading
other Google credential planes. Hermes remains lead engineer: planning, work
boundaries, truth checks, testing, reconciliation and final acceptance remain
Hermes responsibilities.

### Workspace API + Workspace Studio

Direct Workspace APIs are preferred for deterministic operations. Workspace
Studio is a specialist for multi-step Google-native workflows where available.
Cross-provider/cross-project orchestration remains in Hermes. Send-as-owner or
irreversible actions remain A4.

### Nano Banana + Veo + Flow

Nano Banana and Veo are governed media workers. Flow is a consumer creative
surface. Outputs are artifacts with hashes/provenance; they do not directly
become product truth or approved marketing assets.

### AI Studio + ADK/A2A

AI Studio is a prototyping/lab surface, not production authority. ADK/A2A can
provide interoperability with external Google agents/services, but Hermes remains
the federation/orchestration authority.

## 9. Knowledge loop

```text
Project Truth
   ↓ constraints
Hermes VAN
   ↓ unresolved question
Deep Research
   ↓ cited evidence
Gemini Notebook
   ↓ grounded synthesis
VEKL admission
   ↓ provenance/confidence
GraphRAG
   ↓ future work
Project decision
   ↓ owner-authorised authority process only
Project Truth
```

Notebook is grounded memory; Deep Research investigates; VEKL provides
cross-project engineering knowledge; Project Truth remains canon.

## 10. Artifact provenance

Migration v2 persists:

- `google_principal`
- `google_capability_connections`
- `google_jobs`
- `google_artifacts`

Every material Google artifact records job ID, project ID, provider/tool/version,
input hashes, output hash, trust state, validation state, parent artifact IDs and
creation time. The job retains owner intent, capability, action class, truth SHA,
grant ID and evidence pointer.

Provider artifacts are `UNTRUSTED` by default and can never be recorded as
`OWNER_SIGNED`.

## 11. Workspace OAuth correctness

The existing Google token vault stores encrypted refresh tokens. Live Workspace
calls now follow the correct boundary:

```text
encrypted refresh token
   ↓ decrypt inside gateway
OAuth token endpoint
   ↓ short-lived access token
Google Workspace API
```

The access token is transient and never enters Hermes prompts. If OAuth client
credentials are not configured, live transport fails closed.

## 12. Hermes-to-gateway control authentication

Google job planning, job inspection and artifact-evidence mutation are privileged
Hermes control-plane operations. They require `VAN_INTERNAL_CONTROL_TOKEN` in
`X-Van-Internal-Token`. The token is injected by the Hermes/tool runtime and must
never enter prompts, artifacts or owner-visible command payloads.

If it is absent, privileged endpoints fail closed with
`internal_control_token_unconfigured`.

## 13. Gateway API

Read/status APIs:

- `GET /v1/google/status`
- `GET /v1/google/mesh`
- `GET /v1/google/capabilities`

Privileged Hermes control APIs:

- `POST /v1/google/jobs/plan`
- `GET /v1/google/jobs/{job_id}`
- `POST /v1/google/jobs/{job_id}/artifacts`

Existing Workspace APIs remain capability-mediated. Test transport never claims
live Google state.

## 14. Runtime configuration

Key environment variables:

```text
VAN_GOOGLE_TOKEN_FERNET_KEY
VAN_GOOGLE_OAUTH_CLIENT_ID
VAN_GOOGLE_OAUTH_CLIENT_SECRET
VAN_GOOGLE_AI_PLAN
VAN_GOOGLE_CLOUD_PROJECT_ID
VAN_GOOGLE_GEMINI_RUNTIME_CONFIGURED
VAN_GOOGLE_CLOUD_RUNTIME_CONFIGURED
VAN_GOOGLE_CONSUMER_CONNECTED_CAPABILITIES
VAN_INTERNAL_CONTROL_TOKEN
```

Booleans/config metadata describe wiring, not certification.

## 15. Operator setup

Register the owner principal only on an authorised VAN gateway host:

```bash
python tools/google/configure_google_identity.py \
  --subject '<stable-google-subject>' \
  --ai-plan PRO
```

The raw subject is hashed before persistence.

Capabilities can be recorded as `CONFIGURED` when an account surface/runtime is
wired. `READY` should be recorded only with a meaningful evidence pointer after a
live certification action.

Inspect gates:

```bash
python tools/google/certify_google_mesh.py
python tools/google/certify_google_mesh.py --require-ready gemini
```

## 16. Failure semantics

A failed Google capability does not collapse VAN. Hermes reports what is broken,
what still works, and the deterministic fallback if one is registered.

Examples:

- Mixboard unavailable → use Nano Banana for bounded visual ideation if ready.
- Workspace OAuth unavailable → Workspace Studio may be considered only if its
  owner session is certified and policy allows the requested action.
- Personal Notebook unavailable → Enterprise transport may be considered only if
  the owner Cloud/service plane is configured.
- Gemini runtime unavailable → do not claim Deep Research/Live/media execution.

## 17. Security requirements

- no Google master credential;
- no raw subject/email persisted solely to prove ownership;
- no OAuth/API/session secrets in prompts;
- no cookie/session export;
- no reverse-engineered private API as canonical dependency;
- no Google worker may bypass Project Truth, action classes, grants, A4 approval,
  audit or evidence;
- Google broker/registry/credential-isolation surfaces are protected by policy;
- external Google content remains untrusted.

## 18. Repository implementation delivered

- Google capability registry;
- migration v2 for principal/capability/job/artifact state;
- hashed canonical Google principal broker;
- deterministic capability router and fallback handling;
- readiness/evidence state model;
- artifact lineage/provenance service;
- proper Workspace refresh-token → access-token exchange;
- privileged Hermes control-plane token;
- Google mesh/status/job/artifact APIs;
- Hermes provider/profile/MCP updates;
- skills for Google intelligence, Notebook, design and development;
- policy hardening against session export/broker bypass/credential collapse;
- setup and certification tools;
- backend/policy/profile contract tests;
- acceptance/external-gate ledgers.

## 19. External certification gates

Repository completion cannot fabricate Google account consent or live provider
state. The following remain external until performed with the owner's account:

- owner principal registration on deployed gateway;
- Workspace OAuth consent/client credentials;
- Gemini runtime credentials/quotas;
- live Gemini Live/Deep Research/media calls;
- Notebook consumer session or eligible Enterprise setup;
- Mixboard/Stitch availability and owner sign-in;
- Antigravity/Jules sign-in and worker evidence;
- Workspace Studio/Flow/AI Studio account surfaces;
- live Hermes host installation and end-to-end receipts.

See `docs/EXTERNAL_GATES.md`.

## 20. Acceptance criteria

The Google mesh is repository-accepted only when tests prove:

1. Hermes remains sole runtime.
2. raw Google subject is not persisted.
3. credential planes do not collapse.
4. live Workspace calls use access-token refresh correctly.
5. A5 is denied.
6. A4 requires approval.
7. A3/A4 require grants.
8. project mutations require Project Truth evidence.
9. routing/fallback is deterministic.
10. provider artifacts cannot become owner authority.
11. configured consumer surfaces do not masquerade as READY.
12. privileged Google job/evidence APIs fail closed without internal Hermes auth.

Live production acceptance additionally requires the applicable external gates to
be certified against the owner's Google account.

## 21. Canonical conclusion

Google is not a competing assistant inside VAN.

```text
OWNER
  ↓
VAN
  ↓
VAN Gateway
  ↓
HERMES profile `van`
  ↓
Capability Mesh
  ├── Google
  ├── OpenAI/Codex
  ├── Anthropic/Claude
  ├── DDE/VEKL
  ├── local tools
  └── future providers
```

Google supplies specialist perception, research, grounded knowledge, design,
development, Workspace and media capabilities. The owner's Google account is the
single Google identity/entitlement root. Hermes remains the orchestrator; VAN
Gateway remains the security/authority boundary; Project Truth remains canon.
