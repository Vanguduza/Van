# Jev Management

Use this skill when the owner asks to inspect, evaluate, enable, disable, bypass, restore,
promote, demote, quarantine, recalibrate, revise, retire or detach the shared DIAL Jev
System-1 judgment service or one of its registered modules.

## Authority model

Jev is evidence, never authority.

- Hermes owns orchestration and owner-command handling.
- The DIAL Development System owns Jev module policy, registry and lifecycle ceilings.
- VAN gateway owns owner-device authority/read-back verification.
- VATI remains sole trading risk, sizing and execution authority.
- DIAL Business services remain business-state authorities.
- A model recommendation never changes production state by itself.

Never bypass a lifecycle ceiling, project switch, data-egress policy, independent review,
fallback requirement or no-Jev equivalence requirement.

## Read paths

Prefer the bounded `dial_jev` MCP tools:

- `jev_status` — registry, global/project state, circuit and module lifecycle.
- `jev_evaluation_packet` — trusted performance/contribution packet for one module.
- `jev_registered_batch` — bounded registered judgments; never free-form authority.
- `jev_subordinate` — transient bounded support inside an active REASONING_MANAGER run.

The Android Jev screen is a projection. It does not carry TypeSafe credentials.

## Performance evaluation

When asked to evaluate a module:

1. Read current Jev status and the module's exact project scope/revision.
2. Obtain `jev_evaluation_packet`.
3. Evaluate marginal contribution against the registered non-Jev baseline, not provider
   accuracy alone.
4. Consider outcome quality, calibration/safety evidence, high-confidence errors, latency,
   provider/fallback rate, cost/capacity savings, operational complexity and effect direction.
5. Choose exactly one recommendation:
   `KEEP`, `RECALIBRATE`, `REVISE`, `DEMOTE`, `QUARANTINE`, `RETIRE`,
   or `DETACH_GLOBAL`.
6. Record it with `jev_record_evaluation_proposal`, preserving the current run id and model
   lineage. The proposal remains `authority_effect=NONE`.
7. A different reasoning lineage must independently review it with
   `jev_record_evaluation_review`. The same lineage must never propose and approve.
8. Even an approved review does not itself mutate lifecycle state. Apply any accepted state
   change only through the existing owner/Hermes control path and verify the postcondition.

## Improvement proposals

A `RECALIBRATE` or `REVISE` recommendation may propose:

- confidence thresholds;
- missing canonical state fields;
- splitting one broad question into atomic questions;
- merging redundant questions;
- Choice/Noul/Score primitive changes;
- rubric or choice-set refinements;
- counterfactual sampling changes;
- data minimisation improvements;
- fallback or timeout improvements.

Do not silently edit a live module. Candidate revisions begin in SHADOW and preserve the old
fallback until independently verified.

## Global detachment

`DETACH_GLOBAL` is valid when aggregate measured marginal contribution does not justify
provider cost, complexity, risk or dependency. Before permanent detachment:

1. bypass globally;
2. prove required workflows use registered non-Jev paths;
3. run logical no-Jev certification;
4. where safe, run physical-detachment certification with the Jev process/provider adapter
   absent;
5. verify VAN, Development System, VATI cognition and DIAL Business required workflows;
6. retain the decision/evidence ledger.

Do not delete evidence simply because Jev is retired.

## Trading

Jev trading modules may only be called as subordinate evidence during an already-active VATI
cognition LLM run. No standalone/background Jev trading loop is permitted. Jev may not set
risk multiplier, position size, leverage, stop, route, mandate, execution instruction or broker
order. A disagreement may increase uncertainty or support REDUCE/ABSTAIN, never increase risk.

## Failure behaviour

If Jev is unavailable, unqualified, bypassed, circuit-open, low-confidence or rejected by DLP:

- continue through the registered non-Jev path;
- surface honest degraded Jev state;
- never invent a Jev answer;
- never convert availability failure into business/VAN/trading unavailability.
