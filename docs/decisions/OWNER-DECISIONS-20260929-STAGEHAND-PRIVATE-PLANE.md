OWNER DECISIONS — STAGEHAND / PRIVATE PLANE / PROGRAMME B GATES
2026-09-29 (owner message in Claude Code session session_01ELKqm4GCPmPvF3ggKkgB1J; no device or cryptographic signature claimed)

These decisions close OQ-STAGEHAND-HOST, OQ-STAGEHAND-SIGNED-INGRESS, OQ-VAN-PRIVATE-PLANE-HOST,
OQ-STAGEHAND-MODEL and OQ-STAGEHAND-VERSION-AT-ADOPTION.
They also classify the health-gate and verifier/executor findings as mandatory Programme B
remediation, not optional follow-up work.

1. STAGEHAND PRODUCTION HOST — DECIDED
Stagehand must run in a dedicated VAN browser/automation trust zone: van-browser-core.
It must NOT run in production on: van-trading-core, dial-control, van-private-core.
The current repository placement under deploy/van-trading-core/browser/** is historical packaging,
not the final production placement. Design the migration to van-browser-core.
Stagehand and the Harness-owned Chromium may co-reside on van-browser-core, subject to the existing
browser lease/isolation rules.
van-browser-core must have no direct authority over: VATI Risk Authority; Execution Router; broker
credentials; trading secrets; Owner Model database; owner-private Hindsight; owner-private
OpenViking; Project Truth mutation.
Cross-zone access must use bounded authenticated interfaces only.
Do not provision Stagehand temporarily on van-trading-core merely because van-browser-core is not
ready. If van-browser-core is unavailable: STAGEHAND = PRODUCTION_DISABLED.
The deterministic browser path and any independently qualified Jev lane may continue according to
their own policy.

2. STAGEHAND SIGNED INGRESS — DECIDED
Do NOT waive the signed-ingress production requirement.
The 2026-09-18 instruction remains valid owner intent and remains sufficient authority for
repository implementation of Stagehand as a Hermes-managed browser subagent.
It must continue to be represented truthfully as: OWNER_INTENT_APPROVED
It must NOT be rewritten as: device-authenticated; biometric; cryptographically signed;
replay-protected production ingress.
The unresolved production status is: SIGNED_INGRESS_PENDING
No fabricated evidence may be created.
This gate does NOT block: repository implementation; tests; convergence; Stagehand integration; PR
preparation; non-production qualification.
It DOES block production activation where VAN policy requires signed owner ingress.

3. VAN PRIVATE PLANE — DECIDED
Provision a dedicated trust zone: van-private-core
Its canonical responsibilities are: Owner Cognitive Model; owner_model_revision;
correction/invalidation outbox; owner-private Hindsight; owner-private OpenViking projection;
personal-context resolver.
It must NOT host: generic browser automation; Stagehand; Chromium; Jev browser execution; VATI order
execution; broker adapters.
Only bounded authenticated APIs may cross into this plane.
The personal-context resolver must enforce: requested owner revision == authoritative current
owner_model_revision. If authoritative revision cannot be verified: PERSONAL_CONTEXT_UNAVAILABLE.
Do not serve stale cached owner context.
Provisioning/infrastructure availability may remain an external deployment gate, but the repository
topology and contracts must be implemented against this placement now.

4. STAGEHAND MODEL PROVIDER — DECIDED
Canonical provider: Anthropic. Canonical model family: Claude Sonnet 5.
Target Stagehand model: anthropic / claude-sonnet-5
Rationale: Stagehand is a Hermes-managed specialist worker/subagent, not the DIAL manager. Sonnet
therefore fits the existing worker role rather than introducing a separate browser-only model policy.
PIN RULE: Do not silently treat claude-sonnet-5 as an immutable model revision if the provider
exposes it only as a floating alias. Before PRODUCTION activation, determine whether Anthropic
exposes an immutable snapshot/revision identifier for the exact Sonnet 5 model used. If an immutable
provider revision exists: pin it and record it. If it does not: record the provider limitation;
retain the exact configured model family/name; keep the production qualification gate pending where
deterministic model pinning is mandatory.
Do NOT silently downgrade to another Sonnet model merely because an older Stagehand example names it.
If Stagehand 4.1.0 cannot actually operate with Sonnet 5: reproduce the incompatibility; report it;
keep Stagehand production-disabled; do not substitute a different model without another explicit
decision.
Provider credentials remain gateway/runtime-held and must never enter page content, prompts as
data, browser memory, Jev payloads or repository files.

5. STAGEHAND VERSION — DECIDED
Adopt @browserbasehq/stagehand 4.1.0 as the Programme B production target version.
Canonical source identity for this adoption is the RELEASED 4.1.0 artifact, not upstream
default-branch HEAD. The repository already records: package version 4.1.0; exact package-lock
resolution; npm integrity
sha512-PJikMBVoaCRh6TFD7GcmeISmsMq4IwUu1BD5FOsGUVDUxrVqZomWa6W6dF+a/zu4xRZu2Z2xX1nXVMDaCuZWsw==
and upstream release commit cd7b230778cf92269e4cb90e80d97f5113781c51.
Do NOT describe ad2bf12e... as Stagehand 4.1.0. That SHA is later unreleased upstream work and is
not the adopted artifact. Correct the DDS Programme B blueprint and any provenance tables that
currently pair ad2bf12e with 4.1.0.
Production pin status becomes fully qualified only after the live runtime reports the expected
4.1.0 artifact and passes the runtime canary.

6. HEALTH GOVERNANCE BUG — MUST FIX
backend/van_gateway/automation/health.py governance_state() declares
production_activation_permitted = true when required decision files contain no literal
"owner_signature_status: PENDING". That ignores reconciliation_20260929.production_gate.status:
PENDING. This is a real governance bypass in the health/readiness projection. Fix it.
Do NOT special-case this by grepping for one Stagehand string forever. Prefer an explicit
machine-readable production activation gate model. The health surface must report production
activation permitted only when all required governance AND production gates are satisfied.
Required regressions: (owner intent = approved, production gate = PENDING) => false;
(signed owner decision + live qualification pending) => false; (all required gates GREEN) => true.
Do not mark Programme B green while health.py contradicts Project Truth.

7. STAGEHAND SUCCESS-WITHOUT-VERIFICATION — BLOCKER
No browser lane may self-certify success. Canonical lifecycle: lane proposes/acts -> task state =
VERIFYING -> independent postcondition verifier -> VERIFIED_SUCCESS -> COMPLETED | NOT_SATISFIED ->
retry/fallback | UNVERIFIABLE -> degraded/escalation. done=True, GOAL_ACHIEVED, an empty control
set, model prose or Stagehand success must never directly produce completed/succeeded.
Regression tests: Stagehand returns no controls; Stagehand says done; postcondition false; verifier
unavailable. None may produce VERIFIED_SUCCESS.

8. STAGEHAND DIRECT ACTUATION — BLOCKER
Required: Stagehand -> typed action proposal -> Browser Router / policy -> Browser Harness / Browser
Control Agent -> Chromium -> independent verifier. Stagehand must not hold an independent actuation
authority. Where Stagehand's library API internally assumes actuation, adapt or wrap it so the
Programme B production path extracts a bounded proposal and execution is performed through the
Harness-owned path. If Stagehand 4.1.0 cannot support this separation safely: do not fake
compliance; keep its autonomous actuation mode outside production; use it only for
observation/planning/extraction where appropriate; report the limitation. Do not weaken the single
browser ledger or single executor invariant to make Stagehand easier to integrate.

9. CANONICAL BROWSER ROUTER ORDER (locked)
1. deterministic typed Playwright/CDP through Browser Harness
2. dial-jev PROPOSE_ACTION, only for B2-eligible observations
3. Stagehand semantic fallback on van-browser-core
4. owner takeover / policy refusal
All machine lanes feed Browser Harness / Browser Control Agent -> same governed Chromium ->
independent verifier. Jev never executes. Stagehand never self-certifies. Owner takeover preempts
automation.

10. Continue D–H. H accepted as a valid append-only reconciliation checkpoint; its findings remain
blockers until closed. Fix health.py as part of Programme B before independent review I. Push every
verified checkpoint immediately after tests pass.
