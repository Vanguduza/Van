# Automation & Browser Fabric — Rev 1.3 implementation preflight

Generated per Rev 1.3 §420 before any implementation code crossing an authority boundary.
This artifact records resolved governance state. It does **not** grant approval for anything it
records as `PENDING_OWNER`.

**Generated at:** 2026-09-17
**Blueprint:** VAN Browser Intelligence, Autonomous Research, Trading Enhancement & Automation Fabric — Rev 1.3
**Preceding review:** `docs/VAN_BROWSER_INTELLIGENCE_AUTOMATION_FABRIC_REV_1_2_EXPERT_REVIEW.md`

---

## 1. Resolved implementation base (§137)

| Item | Value |
|---|---|
| Resolved implementation-base SHA | `96aa69ac4e2d3ad7428e6bd091bab5fa7e416c07` |
| Canonical integration head (`main`) at branch creation | `3da79829dee584dd30ea9d2702a15ec464154ba4` |
| Certified owner-runtime lineage (Rev 3.1) | `87f5a225b12a8c6b5a1dc1758cd6fc8dabb0fd00` |
| Trading-core bootstrap hardening (work in progress) | `8a6a3a033c5ee61d33043e0ca449fe662f213b19` |
| `PROJECT_CANONICAL_STATE.json` digest (sha256, first 16) | `50f380460819c99d` |
| Stack-lock revision | `5.1.0` |
| Schema version before migration | `5` |
| Schema version after migration | `6` |

### 1.1 Ancestry evidence (§137.8, §410)

```text
git merge-base origin/main origin/gpt/rev3-1-owner-runtime-20260917
  = 3da79829dee584dd30ea9d2702a15ec464154ba4   (== origin/main)

origin/main is an ancestor of the Rev 3.1 lineage : YES
Rev 3.1 lineage is contained in origin/main      : NO
Rev 3.1 commits ahead of main                    : 230
Rev 3.1 commits behind main                      : 0

origin/gpt/trading-bootstrap-hardening-20260917 ahead of main : 1
origin/gpt/trading-bootstrap-hardening-20260917 behind main   : 0
```

`main` is a strict ancestor of the Rev 3.1 lineage, so reconciling Rev 3.1 into the canonical
integration branch is a fast-forward with no divergent history to resolve. Both feature lineages
merge into this base with **zero conflicts**, verified by trial merge before commit.

### 1.2 Branch-name observation (§137 anchor note, Rev 1.2 review finding B1)

Rev 1.2 named the baseline branch `gpt/rev3-1-full-knowledge-runtime-20260917`. At the time of the
Rev 1.2 review that ref was not published and `git ls-remote --heads origin` returned only `main`.
It is now published and resolves to the same commit as `gpt/rev3-1-owner-runtime-20260917`:

```text
gpt/rev3-1-full-knowledge-runtime-20260917 -> 87f5a225b12a8c6b5a1dc1758cd6fc8dabb0fd00
gpt/rev3-1-owner-runtime-20260917          -> 87f5a225b12a8c6b5a1dc1758cd6fc8dabb0fd00
```

Both names are operational labels for one certified SHA. Rev 1.3 §137 is correct that neither name
is authority; the SHA and its ancestry are. The Rev 1.2 review finding is recorded as **resolved by
observation** rather than by correction.

### 1.3 Required Rev 3.1 interface existence (§137.9)

Verified by behavior at the resolved base:

| Required interface | Present | Location |
|---|---|---|
| Owner Context Kernel / `ContextSnapshot` | YES | `backend/van_gateway/context/{models,service,retrieval}.py` |
| `ActionDefinition` + `ActionRuntime` | YES | `backend/van_gateway/action/{models,service,registry}.py` |
| `CommandAuthorityService` | YES | `backend/van_gateway/command/authority.py` |
| A4 owner approval service | YES | `backend/van_gateway/approval/service.py` |
| Hermes owner-runtime bridge | YES | `backend/van_gateway/hermes/bridge.py`, `runtime_api.py` |
| Research gateway pattern | YES | `backend/van_gateway/research/exa.py` |
| Schema migration framework | YES | `backend/van_gateway/storage/db.py` (`SCHEMA_VERSION`, `MIGRATIONS`) |

None of these exist on `origin/main` alone. Implementation against `main` in isolation would have
forced a parallel authorization ladder, which Rev 1.3 §223 prohibits.

### 1.4 Reconciliation status

```text
REV31_RECONCILED_IN_IMPLEMENTATION_BASE
```

Not `BLOCKED_REV31_RECONCILIATION`: the reconciliation has been performed explicitly in this branch
and is visible as two merge commits, so the branch **is** the proposed merge result that §410
requires CI to certify. It is not a claim that `main` already contains Rev 3.1 — it does not. Merge
to `main` remains subject to the normal Project Truth process (§429 step 18).

### 1.5 Merge-result certification finding (§410)

§410 requires CI on the **actual proposed merge result**, not on an isolated
owner-runtime branch. Doing that surfaced one regression that neither lineage shows alone:

```text
tests/scenarios/test_acceptance_scenarios.py::test_scenario_17_destructive_a4
  origin/main                          PASS
  gpt/rev3-1-owner-runtime-20260917    FAIL
  this reconciled base                 FAIL (inherited)
```

Rev 3.1 tightened A4: `orchestrator.py` now denies a destructive command that does not
resolve to an exact typed action, because a biometric approval must bind to an exact
`action_id` and parameter digest. The free-text scenario `"wipe staging"` therefore returns
`denied` where main returned `approval_required`.

This is **stricter, not weaker** — the runtime is right and the main-era assertion was stale.
The scenario has been updated to assert the denial and its reason, and a second case
(`test_scenario_17b_typed_a4_reaches_owner_approval`) proves a typed A4 action still reaches
the approval gate. Recorded here because it is a Rev 3.1 lineage behaviour change reconciled
by this branch, not a Rev 1.3 change.

Full suite on the reconciled base: **580 passed, 2 skipped**.
`tests/hermes/test_profile_layout.py::test_install_profile_preserves_runtime_state_and_secrets`
requires `rsync`, which the authoring container lacks; it fails identically before and after
this branch's changes and passes where `rsync` is present.

---

## 2. Work-in-progress reconciliation

`gpt/trading-bootstrap-hardening-20260917` already lands the Automation/Browser Fabric **deployment
and configuration** layer that Rev 1.3 §§7–14, §191–198 and §346 specify:

```text
config/automation/{policy,domains,resource_policy}.yaml
config/automation/{node_allowlist.json,credentials.yaml.example}
config/browser/{profiles,domains}.yaml
deploy/van-trading-core/automation/{docker-compose.yml,bootstrap-automation-fabric.sh,
                                    qualify-automation-runtime.sh,provision-api.py,runtime.env.example}
deploy/van-trading-core/automation/postgres/init/01-create-n8n-db.sh
deploy/van-trading-core/browser/{package.json,package-lock.json,bootstrap-browser-runtime.sh,runtime.env.example}
```

This preflight therefore treats the deployment layer as **existing contract**, and scopes the work
in this branch to the gateway application layer plus governance. Duplicating `config/automation/*`
or the compose stack is out of scope and would fork the deployment contract.

Contracts consumed from that branch, not redefined here:

| Contract | Source |
|---|---|
| Credential classes `C0_OWNER_ROOT` … `C4_LOW_RISK_INTEGRATION` | `config/automation/credentials.yaml.example` |
| Node allowlist / denylist, `deny_by_default` | `config/automation/node_allowlist.json` |
| `cold_auto_admit`, workflow limits, verification rules | `config/automation/policy.yaml` |
| Domain + SSRF policy, internal-service access | `config/automation/domains.yaml` |
| Browser profile persistence/mutation policy | `config/browser/profiles.yaml` |
| Browser domain observe/extract/mutate/download policy | `config/browser/domains.yaml` |
| Pinned runtime identities (n8n 2.39.7, Stagehand 4.1.0, Playwright 1.63.0, Node 22) | `deploy/van-trading-core/*/runtime.env.example`, `browser/package.json` |

---

## 3. Governance status (§365, §368)

| Decision gate | Artifact | Status |
|---|---|---|
| n8n `SOURCE_AVAILABLE` adoption | `docs/decisions/VAN-ADOPT-N8N-001.yaml` | `PENDING_OWNER` |
| Stagehand adoption | `docs/decisions/VAN-ADOPT-STAGEHAND-001.yaml` | `PENDING_OWNER` |
| Browser Harness adoption | `docs/decisions/VAN-ADOPT-BROWSER-HARNESS-001.yaml` | `PENDING_OWNER` |
| Security Policy amendment | `docs/decisions/VAN-AMEND-SECURITY-POLICY-001.md` | `PENDING_OWNER` |
| External Gates additions | `docs/EXTERNAL_GATES.md` (Automation & Browser Fabric table) | `RECORDED_PENDING_LIVE` |
| Stack-lock promotion | `trading/architecture/proposed/automation_browser_fabric_layers.json` | `PENDING_OWNER` |

No artifact in this branch sets `owner_signature_status` to anything but `PENDING`. Per §365 an
implementation agent must create these and surface them; it must not mark them owner-signed.

### 3.1 Why the stack lock is not mutated here

§366 states plainly: *"Stack-lock mutation is blocked until the repository records the required
owner-approved decision."* The three proposed layers are therefore held in
`trading/architecture/proposed/automation_browser_fabric_layers.json` and validated by
`trading/tests/test_automation_browser_stack_proposal.py` against the **same** schema assertions
that `trading/tests/test_stack_lock.py` applies to admitted layers, plus the §413 assertions.

On owner approval, promotion is a mechanical move of the three objects into
`trading/architecture/stack_lock.json` — the tests then apply unchanged.

---

## 4. Schema (§411)

```text
next unused schema version at implementation time = 6
```

Migration 6 carries, in one semantic migration:

```text
automation_capabilities
automation_artifacts
automation_runs
automation_external_events
automation_standing_intents
standing_automation_authorities
automation_run_nonces
browser_tasks
browser_evidence
browser_profiles
```

---

## 5. Dependency observations (Appendix A — re-verify at adoption)

| Dependency | Observed | Licence | Class | Pin status |
|---|---|---|---|---|
| n8n | 2.39.7 (deployment branch) / 2.39.6 (Rev 1.3 design note) | Sustainable Use License | `SOURCE_AVAILABLE` | `UNPINNED_VERIFY_AT_ADOPTION` |
| Stagehand | 4.1.0 | MIT | `PERMISSIVE` | `UNPINNED_VERIFY_AT_ADOPTION` |
| Browser Harness (`browser-use/browser-harness`) | 0.1.13 | MIT | `PERMISSIVE` | `UNPINNED_VERIFY_AT_ADOPTION` |
| Playwright | 1.63.0 | Apache-2.0 | `PERMISSIVE` | pinned in `browser/package.json` |

Rev 1.3 Appendix A records n8n 2.39.6; the deployment branch pins 2.39.7. The manifest
(`registries/automation_browser_dependencies.json`) records the deployment value as authoritative
for this branch, per Appendix A: *"the adopted versions and digests recorded in VAN release
evidence are authoritative for a deployment."* Both remain `UNPINNED_VERIFY_AT_ADOPTION` until the
adoption gate records a digest.

---

## 6. Allowed work in this branch

Per §368 — *"Before approval, repository-side implementation may build fail-closed code behind
disabled feature/config gates"* — the following is in scope:

```text
governance artifacts (proposal state only)
schema migration 6
StandingAutomationAuthority + derived per-run CommandAuthorityRecord
durable nonce / run-grant replay protection
Automation Fabric gateway package (IR, validator, compiler, registry, dispatch, verifier, events)
Browser Fabric gateway package (tasks, leases, evidence, policy, adapters)
ExternalRuntimeStatus readiness contract for n8n / Stagehand / Browser Harness
degraded-state codes and registry entries
contract tests, security tests, authority tests, nonce tests
certification scripts that fail closed without live runtimes
dependency manifest
```

All external effects default **off**: every new setting governing egress, ingress, n8n dispatch,
browser attachment and standing-automation execution ships disabled.

## 7. Blocked work in this branch

```text
marking any adoption decision or amendment owner-signed
mutating trading/architecture/stack_lock.json
mutating docs/SECURITY_POLICY.md body text
declaring any external gate READY
enabling egress / ingress / browser attachment by default
installing or starting n8n, Stagehand or Browser Harness runtimes
any live broker, webmail or authenticated-profile canary
```

These are owner-gated (§365) or require a live environment this repository's CI cannot truthfully
certify (`docs/EXTERNAL_GATES.md` preamble).
