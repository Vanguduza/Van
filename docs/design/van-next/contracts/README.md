# Contracts (OD-19; Rev 1.9)

**Canonical state machines (Rev 1.9):** `VAN_STATE_MACHINES_REV1_9.json` defines six machines: account lifecycle, deposit, withdrawal, transfer, trade order and news armed ticket. They extend the pack's machines with the transitions the independent audit found missing (AUD-03/04/05/10/19).
- `python3 check_state_machines.py` → 0 findings on VAN's machines; on the pack's original it reports 69.
- `python3 check_state_machines.py --selftest` → each of the checker's rules is broken deliberately and caught (8 of 8).

The obligations and forbidden transitions live in the checker, so editing a machine cannot quietly remove them.

## Imported from the Rev 2 pack

**Source:** the owner-supplied `VAN_NEXT_QUANTUM_BLUEPRINT_PACK_REV2_20261015.zip`, SHA-256 `9ee405a10743399eba691f42839e571c11e25d85640039510674bf46e2a06b4d`. The files are copied unchanged and reviewed for blueprint Rev 1.8.

| File | SHA-256 | Pack path | Used by |
|---|---|---|---|
| `ACCOUNTS_FUNDS_TECHNICAL_CONTRACT.md` | `e173fe2a…7866` | `contracts/` | §7.9.0, §7.9.12 |
| `FUNDING_INTENT.schema.json` | `9b81a9bd…5e9f` | `contracts/` | §7.9.12 |
| `STATE_MACHINES.json` | `5ed1bb73…6008` | `development-pack/` | Lineage only; superseded by `VAN_STATE_MACHINES_REV1_9.json` (Rev 1.9) |

**Status:** design candidates, not runtime schemas. No provider money-movement adapter exists or is enabled.

## Naming inconsistencies inside the pack

The pack uses three different vocabularies for the same concepts. Rev 1.8 resolves them as follows:

1. **Funds states.** The master blueprint §5.6 (e.g. `CAPABILITY_CHECKED`, `OWNER_REVIEWED`, `A4_APPROVED`), `FUNDING_INTENT.schema.json` (e.g. `AWAITING_OWNER`, `AUTHORIZED`) and `STATE_MACHINES.json` all differ. `STATE_MACHINES.json` was canonical at Rev 1.8; from Rev 1.9 **`VAN_STATE_MACHINES_REV1_9.json` is canonical**. The schema's `status` enum is reconciled to it in the DU-29c contract.
2. **Capability states.** Master §5.2 uses `SUPPORTED_NATIVE_API …`; the contract §3 uses `AVAILABLE | BROKER_HOSTED | …`. **The contract §3 set is canonical** (blueprint §7.9.12).
3. **Withdrawals and transfers.** `STATE_MACHINES.json` has separate deposit and withdrawal machines and no transfer machine. Rev 1.9 adds `VAN-SM-FUND_TRANSFER`. It settles only when both the source debit and the destination credit are read back, and a missing credit leads to `INVESTIGATION_REQUIRED` (§7.9.12).

## Not imported yet

The pack's other contracts and schemas (`TRADE_CHART_INTELLIGENCE_CONTRACT.md`, `ORB_WORK_GRAPH_CONTRACT.md`, `CHART_OBSERVATION_PACKET`, `PROVENANCE_STATE_ENVELOPE`, `TASK_GRAPH_SNAPSHOT`) have not been reviewed. Each is reviewed when its packet's contract is written (DU-10, DU-05/06, DU-10d, DU-16), and imported only if it holds up.
