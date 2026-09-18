# Expert review — VAN Browser Intelligence, Autonomous Research, Trading Enhancement & Automation Fabric Rev 1.2

**Status:** Review. Not an authority document; it does not amend Rev 1.2, `docs/SECURITY_POLICY.md`, `docs/PROJECT_TRUTH_PROTOCOL.md`, `trading/architecture/stack_lock.json`, or any other locked authority.
**Reviewed document:** `VAN_BROWSER_INTELLIGENCE_AUTOMATION_FABRIC_REV_1_2_ATOMIC_IMPLEMENTATION_BLUEPRINT.md` (Rev 1.2, 364 numbered sections across five parts, 9613 lines), supplied by the owner.
**Repository state considered:** `main` @ `3da7982`, and `origin/gpt/rev3-1-owner-runtime-20260917` @ `87f5a22` (230 commits ahead of `main`, unmerged).
**Reviewed at:** 2026-09-17.

## Verdict

Rev 1.2 is the most operationally literate blueprint VAN has received. Its central judgement — that n8n is a
peripheral integration fabric with **no authority**, that workflow generation is *capability acquisition* rather
than routine execution, and that the HOT/WARM/COLD ladder makes the system cheaper with use — is correct, and the
HOT/WARM/COLD model is a genuinely good idea that nothing else in VAN currently supplies. Part II is real
engineering: §152's migration numbering, §223's refusal to build a parallel authorization ledger, §35's
`MAX(step action classes)` rule and §344's prohibited-shortcut list all read like they were written by someone
who has the repository open.

The problems are not in the architecture. They are in the four places where Rev 1.2 asserts a dependency on
something the repository does not contain, and in the one place where it repeats — verbatim in structure — the
failure that `docs/VAN_OWNER_AGENT_RUNTIME_REV3_EXPERT_REVIEW.md` raised as B1 and B4 against Rev 3 and which
has not yet been closed: **it expands the credential, egress and agent-loop surface without amending the locked
authority that governs those surfaces, and without adding a single external-gate row.** Under
`PROJECT_CANONICAL_STATE.json → policy.agent_self_authorization_forbidden` that is an owner decision, not an
implementation decision, and an implementation agent handed this document would have to make it silently.

Five findings are blocking. All five are fixable inside the document; none require re-architecting.

---

## Blocking findings

### B1 — The stated implementation baseline names a branch that does not exist, and Part II is written against an unmerged branch

Part II's preamble fixes the baseline at:

```text
87f5a225b12a8c6b5a1dc1758cd6fc8dabb0fd00
```

and names the branch `gpt/rev3-1-full-knowledge-runtime-20260917`. The SHA is real. The branch name is not —
`git ls-remote --heads origin` returns exactly two heads plus this review's branch, and that SHA is the tip of
`gpt/rev3-1-owner-runtime-20260917`. An agent following §137 step 2 ("identify current certified Rev 3.1
authority head") by branch name finds nothing.

The larger problem is what §137 then asks the agent to inspect:

```text
6.  backend/van_gateway/context/*
7.  backend/van_gateway/action/*
8.  backend/van_gateway/command/*
9.  backend/van_gateway/runtime_api.py
```

None of these exist on `main`. All four exist only on the Rev 3.1 branch, which is 230 commits ahead and
unmerged, while `PROJECT_CANONICAL_STATE.json` declares `canonical_integration_branch: "main"`. So Part II —
every ActionRuntime integration, every context-snapshot binding, the entire §152 migration numbering — presupposes
a merge that has not happened and that this document never names as a precondition.

Separately: the Rev 3.1 architecture document itself is in neither branch. `docs/` contains
`VAN_OWNER_AGENT_RUNTIME_REV3_EXPERT_REVIEW.md` but not the `VAN_CANONICAL_OWNER_AGENT_RUNTIME_ARCHITECTURE_REV3.md`
it reviews, and no Rev 3.1 revision of it. Rev 1.2 cites "Rev 3.1" as an authority 40+ times against a document
the repository cannot produce.

**Required correction.** Fix the branch name. Add an explicit Phase A precondition: *Rev 3.1 is merged to `main`,
or this work is branched from Rev 3.1 and both merge together.* Land the Rev 3.1 architecture document in `docs/`
so "Rev 3.1 §n" citations resolve. Until the branch name is right, §137 and §138 are not executable.

### B2 — The plan widens the credential, egress and ingress surface without amending the locked authority that governs it

Rev 1.2 mentions `SECURITY_POLICY`, `PROJECT_TRUTH_PROTOCOL` and `PROJECT_CANONICAL_STATE.json` exactly once each
— as read-only items 3–5 of §137's inspection list. It mentions `docs/EXTERNAL_GATES.md` zero times. It never
proposes an amendment to any of them.

Against that, the plan introduces:

- an n8n-held encrypted credential store for "integration credentials" (§45) — a **new credential plane**, where
  `SECURITY_POLICY.md → Google Account Sovereignty` enumerates the permitted planes exhaustively and
  `→ Capability broker` defines how grants work;
- an externally reachable webhook ingress (§15) and an editor access path (§210), where the policy's
  *Android production gateway ingress* section fixes the layered-bearer model and `EXTERNAL_GATES.md` treats
  public ingress as an unresolved gate;
- a general outbound egress surface under domain policy (§106, §205–207), where the only certified egress
  precedent is `ExaResearchService`, gated behind an explicit `exa_egress_enabled` flag;
- browser sessions and profiles (§182–185) that will hold owner-authenticated cookies — material the policy's
  *Secrets* section names explicitly ("browser cookies/session tokens") as never-log, never-prompt-inject.

`docs/SECURITY_POLICY.md` is listed in `PROJECT_CANONICAL_STATE.json → canonical_state.locked_authorities`, and
that same policy block sets `agent_self_authorization_forbidden: true` and
`owner_instruction_is_project_truth_authority: true`. An agent handed Rev 1.2 as-is must either stop, or amend a
locked authority on its own initiative. This is the same shape as B1/B4 in the Rev 3 review; that review's
recommended change list items 1 and 4 are still open.

**Required correction.** Add a section to Part II that states, as a named diff, what Rev 1.2 requires of
`SECURITY_POLICY.md` — specifically its *Capability broker*, *Secrets* and *Hermes execution boundary* sections —
and route it to the owner as an amendment before Phase B begins. Add the corresponding `EXTERNAL_GATES.md` rows
(see M4). Nothing in Phases B–I should start before that amendment is signed.

### B3 — n8n's licence class is never declared, and the §4 stack-lock entry fails three existing tests as written

`trading/tests/test_stack_lock.py` is executable governance. The §4 layer object breaks it three ways:

1. `latency_tier: T2/T3`. `test_one_canonical_choice_per_layer` asserts
   `l["latency_tier"] in {"T0","T1","T2","T3"}`. `"T2/T3"` is not a member. Pick one — T3, with a documented
   T2 exception for HOT owner-interactive calls, matches §56.
2. `licence_class`, `adoption_phase` and `pin_status` are absent. The same test asserts `licence_class` is in
   `ALLOWED_LICENCE_CLASSES` and `adoption_phase` is an `int >= 1`; `test_nothing_is_pinned_before_adoption_gate`
   asserts `pin_status`. Compare any existing layer object for the full required shape.
3. **The licence itself is never discussed.** n8n does not ship under an OSI-approved licence — it is
   source-available under the Sustainable Use License, with an additional enterprise licence for some features.
   That maps to `SOURCE_AVAILABLE`, which is in `DECISION_REQUIRED`, which means
   `test_non_permissive_licences_require_owner_decision` will fail unless the layer's `constraints` contain the
   string `"owner-signed adoption decision"` — and stack-lock principle 5 requires that decision to actually
   exist. §277 addresses *paid-edition* independence, which is a different question, and concludes the
   architecture must not depend on paid features. It never reaches the licence class of the free edition.

The same gap applies to Stagehand and to whatever Browser Harness turns out to be (B5).

**Required correction.** Replace §4's fragment with a complete layer object matching the existing schema, declare
`licence_class` for n8n, Stagehand and Browser Harness, and record the owner-signed adoption decision for every
`SOURCE_AVAILABLE` or `VERIFY_AT_ADOPTION` entry *before* §194's deployment work, not after.

### B4 — An AUTOMATION-principal run cannot obtain command authority under the Rev 3.1 code

This is the most consequential technical finding, and it is an integration gap rather than a design error.

§223 is right to route automation through the existing Action Runtime, and §224's `ActionDefinition` JSON is
valid against the real model — `PrincipalType.AUTOMATION` and `OriginChannel.AUTOMATION` already exist in
`backend/van_gateway/models.py`, so the principal has a home. But `ActionRuntime.begin` is reached through
`CommandAuthorityService.authorize_action` (`backend/van_gateway/command/authority.py`), which requires, for
every execution:

- a sealed `CommandAuthorityRecord` for the `command_id` — absent it raises `command_authority_missing`;
- a non-null `snapshot_id` **equal** to the record's (`context_snapshot_mismatch`);
- matching `turn_id`, `requested_by` and `principal_type`;
- and a lookup of `record.device_id` in `devices`, refusing if the row is missing or revoked
  (`device_or_grant_revoked`).

§159's invocation payload carries `command_id`, `turn_id` and `context_snapshot_id`, so the shape is right. What
the blueprint never states is **who seals the authority record for a scheduled or event-driven run in which no
owner device participates** — which is precisely the case §16 ("VAN's event nervous system"), §92 (standing
automation) and §227 exist to serve. §227's `StandingAutomationIntent` stores an `owner_approval_ref`, but no
mechanism turns that into a per-fire `CommandAuthorityRecord`, and the record type is device-bound by
construction.

Two secondary consequences follow:

- `capability_grants` in `storage/db.py` is device-bound (`device_id TEXT NOT NULL`), whereas §160's grant is
  run-bound. §152's migration adds no grant or nonce table, so §161's replay check has nowhere to persist state.
- `ActionRuntime.revoke_privileged_for_device` cascades revocation by `requested_by` across classes A2–A4. Rev 1.2
  never specifies what `requested_by` an automation run carries, so owner revocation either misses automation runs
  entirely or cancels them all. Both are defensible; neither is stated.

**Required correction.** Add a section specifying standing-intent → per-fire authority derivation: which
`device_id` the record binds to (the approving device, presumably), how the context snapshot is compiled without a
live turn, the expiry, the `requested_by` value, and how device revocation cascades to standing automations. If
the answer is a non-device authority record, define it as a distinct type with its own table in §152 and its own
tests — do not widen `CommandAuthorityRecord` silently.

### B5 — "Browser Harness" is a pinned, licence-classed, resource-budgeted dependency with no definition anywhere

Browser Harness appears 13 times. Every occurrence is referential: §138 requires a "Browser Harness version pin"
in the PR body, §196 requires an "exact commit/tag", §194's compose skeleton runs it, §358 certifies it, §188
specifies its adapter, Part V names it a non-negotiable boundary. §87 says the "Stagehand/Browser Harness
architecture from Rev 1.0 remains fully preserved" — but Rev 1.0 is not in the repository and was not supplied,
and `git grep -i` returns **zero** matches for `stagehand` or `browser.harness` anywhere in the tree.

An implementation agent cannot pin a commit, assign a licence class, or budget RAM for a component with no named
upstream and no specification.

**Required correction.** Either name it — upstream project, licence, version — or declare it a VAN-owned component
and give it a specification section at the same depth §186–189 give the Stagehand adapter. If Rev 1.0 defines it,
Rev 1.0 must be supplied and cited, and its relevant sections carried forward the way Rev 3 carried Voice Rev 2.

---

## Material findings

### M1 — Temporal is routed to but has never been built

§5's capability router, §6, §86 and §325 all terminate critical durable processes at Temporal. In
`trading/architecture/stack_lock.json` the `durable_workflows` layer is `adoption_phase: 11`,
`pin_status: "UNPINNED_VERIFY_AT_ADOPTION"`, `build_status: "not started"`. The Temporal branch of the router is
dead code on the day it ships.

§6 already supplies the honest fallback — "Temporal / native VAN state machine". Make that the Phase A–I behaviour,
mark the Temporal branch explicitly deferred to adoption phase 11, and say what happens to a
`critical durable process` classification in the meantime.

### M2 — VEKL is trading-scoped and borrowed from DIAL; §52 widens it without saying so

§1 defines VEKL as "governed owner/project/automation knowledge" and §52 has it store WorkflowIR patterns,
`AutomationPatternDescriptors`, anti-patterns and performance evidence. In the repository, VEKL is `trading/vekl`
— a vendored DIAL resolver (`vendor/dial/`, `PROVENANCE.json`, pinned commit) stack-locked as
`trading_knowledge_layer` = "VTIL on borrowed DIAL VEKL infrastructure", `licence_class: INTERNAL`,
`pin_status: PIN_TO_DIAL_COMMIT_AT_ADOPTION`, carrying the constraint *"separate registry namespace from DIAL
engineering VEKL"*. There is no owner/project VEKL instance.

So §52 either (a) writes VAN automation knowledge into a trading-scoped, DIAL-borrowed service, or (b) implies a
second VEKL instance that no section introduces. Neither is stated.

**Correction.** Name the instance and the namespace, and say whether a VAN automation namespace is admissible under
the DIAL borrow or requires the fork the stack lock already contemplates ("may be forked into a dedicated VEKL
instance if … evidence justifies it").

Worth noting in the document's favour: §53's Zie619 ladder is already grounded in code.
`trading/vekl/vendor/dial/engineering-resource-resolver.mjs:266,354` already recognises
`community.zie619.n8n_workflows` and flags it `untrusted_external_reference`. Rev 1.2 should cite that as the
enforcement point rather than restating the rule in prose.

### M3 — Stagehand L4/L5 is a second inference locus and, as written, a second agent loop

§6's fourth web-only tier is "bounded autonomous Stagehand discovery" and §88's ladder tops out at
"L5 bounded Stagehand agent". That is model-driven action selection running in a Node worker.

`docs/SECURITY_POLICY.md` — locked — states: *"Hermes profile `van` is the sole agent runtime. Android, the
gateway, Gemini Live, Deep Research, Antigravity, Jules, Workspace Studio and other provider surfaces do not form
independent VAN agent loops."* §37 gets this exactly right for n8n AI Agent nodes and then grants the same
capability to Stagehand two pages earlier without addressing the policy.

The document also never answers, for the Stagehand worker, the four questions `ExaResearchService` already answers
for Exa: which model credential it holds, where that credential lives, whether egress is enabled by default, and
what state it reports when unconfigured.

**Correction.** Either cap the production ladder at L3 (observe → deterministic action) with L4/L5 behind an
explicit owner-gated flag, or raise the ladder as a `SECURITY_POLICY.md` amendment under B2. Then give the worker
the Exa treatment: gateway-held credential, default-off egress, explicit unconfigured state.

### M4 — No external-gate rows, no degraded-code wiring, no CONFIGURED/READY discipline

`docs/EXTERNAL_GATES.md` is where VAN records everything that needs owner credentials or a live environment, and
its rules are unambiguous: *"`CONFIGURED` is not `READY`"*, and *"`READY` requires an evidence pointer"*. The n8n
runtime, the `van_n8n` database, the Stagehand worker, browser profiles, and any live broker or webmail browser
canary are all exactly that kind of gate. Rev 1.2 adds no rows. §343 instead invents a parallel gate vocabulary
(`N8N_RUNTIME`, `BROWSER_SECURITY`, `VATI_T0_ISOLATION`, …) with no mapping to the existing ledger, which is how a
governance surface forks.

§345 is right that unavailable environments mean "finish repository-side work, create certification script,
document exact external gate" — it just never says the gate is documented *in `EXTERNAL_GATES.md`*.

Separately, §100 proposes five degraded states but leaves them as prose. They need to become members of
`DegradedCode` in `backend/van_gateway/models.py` with entries in `backend/van_gateway/degraded/registry.py`.

**Correction, and the strongest constructive recommendation in this review:** model the entire n8n and Stagehand
surface on `backend/van_gateway/research/exa.py`. That service is the repository's certified pattern for an
external dependency — credential locus pinned to the gateway, a boolean egress enable that fails closed, a
secret-pattern rejector on outbound content, and a `status()` returning
`UNCONFIGURED / CONFIGURED_EGRESS_DISABLED / CONFIGURED / READY` where READY requires a recorded evidence pointer.
Reusing it satisfies the EXTERNAL_GATES rules, the Truth Protocol's fail-closed contract and §99's
no-cascading-failure requirement in one move, and it is already tested.

In the document's favour: §100's required four fields — "broken / still works / will not do / restore action" —
are exactly `DegradedCapability`'s shape and exactly the Truth Protocol's fail-closed contract. Rev 1.2 should say
so and reuse the type rather than describing it.

### M5 — The n8n → Gateway callback has no authentication design that fits the existing surface

§42's VAN Capability node "calls VAN Gateway" and §160–161 define a short-lived grant with nonce and replay
checks. But every Rev 3.1 runtime route in `runtime_api.py` is gated solely by `verify_internal_control`
(`X-Van-Internal-Token`), and `SECURITY_POLICY.md` states that credential "is not accepted as a general external
bearer". §14 correctly says Hermes gets no unrestricted n8n credentials; the reciprocal — what n8n presents to the
gateway — has a token format but no route family, no middleware, and no storage.

§139's package map has `automation/router.py` but §220–222 specify the endpoints' bodies, not their auth, and §152
adds no nonce or grant table.

**Correction.** Name the route family and its auth middleware, define the grant/nonce table in §152, and state
whether these routes live under `/v1/runtime` (internal-token) or a new prefix with grant-only auth.

### M6 — The deployment sections assume Compose; the Trading Core VM is systemd-first with a Supabase-managed Postgres

§191–194 describe a Docker Compose topology and §12 expresses isolation as generic "CPU weight / bounded quota".
The actual VM is systemd-first: `deploy/van-trading-core/systemd/vati-{commander,supabase,vekl,session@,mt5-pull}.service`
plus `bootstrap.sh` and `qualify.sh`. Compose appears only for the Supabase donor
(`deploy/van-trading-core/supabase/docker-compose.yml`, with `DONOR_PROVENANCE.json` and an append-only role
provisioned from `init/01_vati_ledger.sql.tpl`).

That has two consequences the blueprint should absorb rather than work around. §12's isolation is enforced through
systemd slices and directives (`CPUWeight=`, `CPUQuota=`, `MemoryMax=`, `IOWeight=`) on units that already exist —
which is *better* than the blueprint's generic framing, and testable via §358. And §8's `van_n8n` database lands
inside a donor-provisioned Supabase cluster with its own migration lifecycle, so "separate database, separate role,
separate backup policy" needs to be expressed against that donor, or n8n needs its own Postgres instance and the
blueprint should say which.

**Correction.** Rewrite §7, §12 and §191–198 against systemd units and the Supabase donor, and decide explicitly:
`van_n8n` as a database inside the donor cluster, or a separate pinned Postgres.

### M7 — Part IV's acceptance rows are mostly unmeasurable

"n8n load cannot violate VATI safety envelope", "Restore proven", "Manual n8n workflow edits detected" and
"No new route bypasses signed command authority" carry no thresholds and name no artifacts. VAN's established
convention is a named evidence pointer — see every resolved row in `EXTERNAL_GATES.md` and the
`artifacts/google/*_attestation.json` receipts.

**Correction.** Give each Part IV row a numeric threshold where one applies and an artifact path where one does
not, e.g. VATI decision-cycle p99 delta under n8n load, and `artifacts/runtime/van_automation_*_attestation.json`.

### M8 — §57's SLOs and §354's harness ignore the certification pattern already in the tree

The Rev 3.1 branch already carries `docs/project-state/REV31_CONTEXT_RETRIEVAL_CERTIFICATION.md` and a
reproducible, CI-executed context-latency benchmark — built for exactly the kind of p95 claim §57 makes about
registry lookup and capability routing. §354 should extend that harness and record into that certification format
rather than introducing a parallel one.

---

## Minor

- §152 correctly begins at migration 6 against `SCHEMA_VERSION = 5`, and its "renumber only, do not merge two
  semantic migrations" instruction matches how `MIGRATIONS` is structured. Good.
- §35's `workflow class = MAX(step action classes)` is consistent with `_RANK` and the
  `action_class_escalation_denied` check in `command/authority.py`. Say so explicitly — it makes the rule testable
  rather than aspirational.
- §226's approval binding is a strict superset of `CommandAuthorityRecord`. Frame it as extending that record
  (adding `workflow_artifact_id` and `workflow_version`), not as a new challenge type; §226's invalidation-on-version-change
  rule then falls out of the existing `command_authority_conflict` path.
- §139 adds `hermes/skills/{automation-fabric,browser-intelligence,trading-browser-research}`.
  `tests/hermes/test_profile_layout.py` asserts the profile layout; new skills must be registered there and in the
  installer, or CI fails.
- §359's proposed CI jobs have no mapping to `.github/workflows/van-ci.yml`, which today runs `pytest -q`,
  `pytest -q tests/contracts`, and the Android/visual jobs. Name the file.
- Nothing in Parts II–III records the change in `docs/IMPLEMENTATION_LEDGER.md` or
  `docs/project-state/LOCAL_CHANGE_LEDGER.jsonl`, which every prior VAN change carries.
- §69's `ResearchPriorityEngine` integration is well grounded — the engine and `ResearchTask` are real
  (`trading/vati/learning/priority.py`), as is the meta-learned tool-value bound. Cite the module.
- §51 and §240's admission model is likewise real: `trading/vati/vtil/admission.py` already enforces
  no-self-admission and T4-requires-evidence, with induced-failure tests. Cite it rather than restating it.
- Note the two VTIL locations — `trading/vati/vtil/` (the admission ledger) and `trading/vtil/` (registries).
  §137 step 14 says "inspect VTIL admission implementation" without disambiguating.

---

## Recommended Rev 1.3 change list, in order

1. **Fix the baseline.** Correct the branch name to `gpt/rev3-1-owner-runtime-20260917`, make "Rev 3.1 merged to
   `main`" an explicit Phase A precondition, and land the Rev 3.1 architecture document in `docs/`. (B1)
2. **Write the authority diff.** State what Rev 1.2 requires of `SECURITY_POLICY.md` and route it to the owner
   before Phase B. Nothing in Phases B–I starts first. (B2)
3. **Complete the stack-lock entry and settle the licences.** A schema-valid layer object, a declared
   `licence_class` for n8n, Stagehand and Browser Harness, and the owner-signed adoption decision every
   `SOURCE_AVAILABLE` entry requires. (B3)
4. **Specify standing-intent → command authority derivation**, the automation `requested_by` value, revocation
   cascade, and the grant/nonce table in §152. (B4)
5. **Define Browser Harness**, or supply Rev 1.0 and carry its sections forward. (B5)
6. **Add the `EXTERNAL_GATES.md` rows and the `DegradedCode` members**, and model n8n/Stagehand on
   `ExaResearchService`'s credential/egress/READY pattern. (M4)
7. **Design the n8n → Gateway callback auth** as a named route family with middleware and storage. (M5)
8. **Rewrite the deployment sections against systemd and the Supabase donor**, and decide the `van_n8n` locus. (M6)
9. **Cap the Stagehand ladder at L3** pending an owner decision on L4/L5. (M3)
10. **Name the VEKL instance and namespace**, and cite the Zie619 enforcement point already in the resolver. (M2)
11. **Mark the Temporal branch deferred** with the native-state-machine fallback. (M1)
12. **Make Part IV measurable** — thresholds and artifact paths — and extend the existing Rev 3.1 certification
    harness rather than inventing one. (M7, M8)

Items 1–5 are blocking. Items 2, 3, 4, 6 and 9 are the security- and governance-relevant ones. Item 1 gates the
rest, because until the baseline resolves, no instruction in Part II can be executed as written.

---

## What Rev 1.2 gets right, and should keep

Worth stating plainly so a revision does not erode it.

The core architectural judgement is correct and should not be reopened: n8n as a peripheral fabric with
`authority: none`, the explicit SHALL-NOT list in §2, the §18 rule that an external event may never become an
owner command, and the §68 T0 firewall. These match the repository's existing boundaries — stack-lock principle 4
("no network broker, workflow engine or LLM sits inside" the tick-to-order path) and the single-order-sender gate
— rather than competing with them.

The HOT/WARM/COLD ladder and §24's framing of workflow generation as *capability acquisition rather than routine
execution* is the most valuable idea in the document, and §32's insistence that the owner never pays generation
latency when a direct path exists is the right instinct applied correctly.

§20–21's WorkflowIR — refusing to let an LLM emit production n8n JSON, and refusing to let n8n topology become
project truth — is the same discipline the repository already applies through `stack_lock.json` and the admission
ledgers. §50's `AutomationWorkflowArtifact` keeping lineage independent of n8n's workflow IDs is exactly right.

§223's "do not create an automation-specific parallel authorization ledger" is the single best sentence in Part II,
and §224's `ActionDefinition` examples are valid against the real model — including `AUTOMATION`, which the Rev 3.1
`PrincipalType` already provides. §152's migration discipline, §40's static analyser as *code rather than prompt
instructions*, §41's deny-by-default community nodes, §46's credential aliases, and §54's extract-patterns-not-workflows
rule are all correct and implementable as written.

§344 and §345 read like they were written from VAN's own culture: no placeholders, no fake success, no TODO-backed
production path, no silent feature thinning, and finish repository-side work when an external environment is
unavailable. That is the repository's induced-failure and fail-closed convention stated back accurately.

Those parts are why Rev 1.2 is worth correcting rather than replacing. The five blocking findings are all
documentation-level: every one can be closed inside the blueprint plus one owner decision, without changing a
line of the architecture.
