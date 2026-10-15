# Contracts imported from the Rev 2 pack (OD-19)

**Source:** the owner-supplied `VAN_NEXT_QUANTUM_BLUEPRINT_PACK_REV2_20261015.zip`, SHA-256 `9ee405a10743399eba691f42839e571c11e25d85640039510674bf46e2a06b4d`. The files are copied unchanged and reviewed for blueprint Rev 1.8.

| File | SHA-256 | Pack path | Used by |
|---|---|---|---|
| `ACCOUNTS_FUNDS_TECHNICAL_CONTRACT.md` | `e173fe2a…7866` | `contracts/` | §7.9.0, §7.9.12 |
| `FUNDING_INTENT.schema.json` | `9b81a9bd…5e9f` | `contracts/` | §7.9.12 |
| `STATE_MACHINES.json` | `5ed1bb73…6008` | `development-pack/` | Canonical state names: §7.8.6, §7.9.1, §7.9.12 |

**Status:** design candidates, not runtime schemas. No provider money-movement adapter exists or is enabled.

## Naming inconsistencies inside the pack

The pack uses three different vocabularies for the same concepts. Rev 1.8 resolves them as follows:

1. **Funds states.** The master blueprint §5.6 (e.g. `CAPABILITY_CHECKED`, `OWNER_REVIEWED`, `A4_APPROVED`), `FUNDING_INTENT.schema.json` (e.g. `AWAITING_OWNER`, `AUTHORIZED`) and `STATE_MACHINES.json` all differ. **`STATE_MACHINES.json` is canonical**, as the pack's own contract §5 says. The schema's `status` enum is reconciled to it in the DU-29c contract.
2. **Capability states.** Master §5.2 uses `SUPPORTED_NATIVE_API …`; the contract §3 uses `AVAILABLE | BROKER_HOSTED | …`. **The contract §3 set is canonical** (blueprint §7.9.12).
3. **Withdrawals and transfers.** `STATE_MACHINES.json` has separate deposit and withdrawal machines and no transfer machine. A transfer follows the deposit shape and needs both the debit and the credit read back (§7.9.12).

## Not imported yet

The pack's other contracts and schemas (`TRADE_CHART_INTELLIGENCE_CONTRACT.md`, `ORB_WORK_GRAPH_CONTRACT.md`, `CHART_OBSERVATION_PACKET`, `PROVENANCE_STATE_ENVELOPE`, `TASK_GRAPH_SNAPSHOT`) have not been reviewed. Each is reviewed when its packet's contract is written (DU-10, DU-05/06, DU-10d, DU-16), and imported only if it holds up.
