# VAN private plane — `van-private-core` topology (2026-09-29)

**Authority:** owner decisions of 2026-09-29, §3 "VAN PRIVATE PLANE — DECIDED", given as an
owner instruction in Claude Code session `session_01ELKqm4GCPmPvF3ggKkgB1J`.
Authorization id `auth-20260929-owner-van-private-core`, class `OWNER_EXPLICIT`.
No device or cryptographic signature is claimed. The integrator reconciles this record with
the parallel Programme B record for the same owner message.

**Programme:** A — Memory Fabric Rev 1.2. Nothing here imports or depends on Programme B
(Jev, browser router, Stagehand migration).

## What the repository now implements

| Responsibility (§3) | Code | Store | Status |
|---|---|---|---|
| Owner Cognitive Model | `backend/van_gateway/understanding/owner_model.py` | `owner_cognitive_model`, `owner_model_episodes` | implemented |
| `owner_model_revision` | `owner_model.py` (`_bump_revision`, `current_revision`) | `owner_model_revisions` | implemented |
| correction/invalidation outbox | `owner_model_outbox.py` | `owner_model_outbox` | implemented |
| owner-private Hindsight | — | `/var/lib/van-private-core/hindsight-owner` | placement only (outbox target `HINDSIGHT_OWNER`) |
| owner-private OpenViking projection | — | `/var/lib/van-private-core/openviking-owner` | placement only (outbox target `OPENVIKING_OWNER_PROJECTION`) |
| personal-context resolver | `personal_context.py` (producer), `personal_context_resolver.py` (fence) | — | implemented |

- **Deploy package:** `deploy/van-private-core/` — `topology.json` (machine-readable
  placement, ingress, must-not-host list), `systemd/van-private-core.service`,
  `runtime.env.example`, `qualify.sh`, `README.md`.
- **Bounded authenticated API:** `backend/van_gateway/private_core/app.py` serves exactly
  `GET /v1/private-core/owner-model/revision` and `GET /v1/private-core/personal-context`,
  behind mutual TLS (private CA, `--ssl-cert-reqs 2`) and the scoped internal credential
  (`understanding`). The unit refuses an empty or wildcard bind.
- **Resolver rule:** requested revision == authoritative `owner_model_revisions` row read at
  resolve time, else `PERSONAL_CONTEXT_UNAVAILABLE` (reasons: invalid request, store
  unreachable, revision missing, mismatch, changed during resolve, integrity). The cache has
  no TTL and no fallback on error; the outbox `PERSONAL_CONTEXT_CACHE` target drops entries.
- **Contract:** `tests/contracts/test_van_private_core_topology.py` fails if the zone
  package names browser automation, Stagehand, Chromium, Jev, VATI or broker code; if the
  private-core app's import closure pulls any of them in; if any module outside the declared
  set touches the protected tables; if trading, services, the trading-core or browser-stream
  deploy packages, or the gateway's browser/automation/computer-use/trading packages reach
  the plane at all; or if the in-process consumer list grows.

## External and split gates (not closed by this change)

| Gate | What remains | Why it is not closable in the repository |
|---|---|---|
| **G-PC-1** Host provisioning | A `van-private-core` host (VM or equivalent) on the private overlay, service account `van-private`, `/var/lib/van-private-core` on an encrypted volume, `qualify.sh` returning GREEN. | Infrastructure. `qualify.sh` has never run; no host exists. |
| **G-PC-2** Private-core PKI and credential | A CA private to this plane, server cert, client certs for each authorized caller (gateway, Hermes), and the `understanding` scoped token delivered from a secret file. | Secrets must be minted on the host/operator side, never committed. No PKI script is added yet; the browser-stream `make-stream-pki.sh` is the pattern to follow. |
| **G-PC-3** Gateway split | Today the Owner Model still runs **in-process inside van-gateway** against the gateway's SQLite file: `understanding/api.py` (owner confirm/correct/reject/observe routes), `reasoning/calibration.py` and `evolution/vaneval.py` (aggregate counts only, via `OwnerCognitiveModel.integrity_counts()`). Each must become a client of the private-core API, and the Owner Model tables must move to the private-core store with a data migration. The contract test pins this list so it can shrink but not grow. | Requires write routes on the private-core API (owner-authenticated confirm/correct/forget), a migration of existing rows, and a deployed host to point at. |
| **G-PC-4** Governance executors | `context/forget.py` (owner right-to-forget) and `ops/retention.py` (retention classes) name the protected tables and must execute on the zone that owns the store once split. `storage/db.py` holds the schema and forget trigger. | Same as G-PC-3: they follow the store. |
| **G-PC-5** Owner-private Hindsight and OpenViking | No owner-private Hindsight or OpenViking service or client exists in this repository — only outbox targets. Both need exact-version qualification before adoption (Hindsight MIT; OpenViking **AGPL-3.0**, which needs a licence decision), loopback-only binding on this host, and real outbox handlers. | External dependencies; DEC-039 makes upstream repositories reference-only until an explicit owner dependency decision. |

## Verification

Commands and exit codes are in the unit L handoff report for this change; the contract test
and `backend/tests/test_personal_context_resolver.py` /
`backend/tests/test_van_private_core_service.py` are the executable record.
