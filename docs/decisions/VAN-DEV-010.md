# VAN-DEV-010 — Connected: DIAL development fabric (backend half)

**Design authority:** DIAL `VAN-DEVCC-R1` §2.1 (Infrastructure → **Connected**, new "DIAL
development fabric" section), §3.1 (`degraded[]` mapping), §6.11. **Depends on:** VAN-DEV-001.

**Status: backend IMPLEMENTED (repository); Android section is a separate unit of work.**

### What the backend provides

1. **The read.** `GET /v1/dial-dev/infrastructure` → DIAL `GET /v1/dev/infrastructure`
   (Hermes, manager slots, Orca version/drift/daemon scope, SPMRF, OpenViking, VEKL, ARTEMIS,
   capability ladder per tool `INSTALLED → AUTHENTICATED → LIVE_QUALIFIED → ORCHESTRATED →
   INTEGRATED`, Oracle gate), relayed byte for byte in the §3.1 envelope. The gateway adds no
   ladder state of its own: a capability VAN cannot see is not reported as anything.
2. **Degraded mapping.** Nine new `DegradedCode`s with catalogue entries
   (`backend/van_gateway/degraded/registry.py`), so a DIAL fault appears on VAN's `/health`
   and `/v1/degraded` as a DIAL fault and degrades only the Development Control Centre:

   | Code | Raised by |
   |---|---|
   | `DIAL_DEV_UNAVAILABLE` | VAN cannot reach DIAL, or DIAL refuses VAN's credential / answers 5xx / malformed |
   | `DIAL_DEV_EVENT_STREAM_DOWN` | VAN-DEV-002's event stream is disconnected |
   | `DIAL_ORCA_DEGRADED` | envelope `degraded[].subsystem` = `ORCA` |
   | `DIAL_SPMRF_DEGRADED` | `SPMRF` |
   | `DIAL_OPENVIKING_DEGRADED` | `OPENVIKING` |
   | `DIAL_VEKL_DEGRADED` | `VEKL` |
   | `DIAL_ARTEMIS_DEGRADED` | `ARTEMIS` |
   | `DIAL_ZUUL_DEGRADED` | `ZUUL` |
   | `DIAL_HERMES_DEGRADED` | `HERMES`, `HERMES_DIAL`, `DIAL_HERMES` (DIAL's Hermes — not VAN's profile) |

   Subsystem names are matched case- and punctuation-insensitively. The latest projection
   envelope is authoritative for the seven subsystem codes (set if listed, cleared if not);
   the two link codes are VAN's own observation and are cleared only by a successful DIAL
   answer or a connected stream. A subsystem VAN does not know is not guessed into a code; the
   device still sees DIAL's row verbatim in the envelope.

### Requirements and their proofs

| ID | Requirement | Proof |
|---|---|---|
| VAN-DEV-010-R1 | Every new code is catalogued; `/health` survives any of them | `backend/tests/test_degraded_catalog_is_exhaustive.py` (parametrised over every `DegradedCode`) |
| VAN-DEV-010-R2 | `degraded[]` maps to codes, reaches the device unchanged, and clears | `backend/tests/test_dial_dev_proxy.py::TestEnvelopePassThrough::test_degraded_rows_map_onto_vans_degraded_model_and_clear` |
| VAN-DEV-010-R3 | Infrastructure read is proxied to the right DIAL path | `test_dial_dev_proxy.py::TestEnvelopePassThrough::test_every_read_reaches_its_dial_path_and_returns_the_envelope_unchanged[/v1/dial-dev/infrastructure…]` |

### Open point

Latest-envelope-wins means that if DIAL's endpoints ever reported different `degraded[]`
sets, the registry would follow whichever was read last. The design implies one global set per
projection revision; if DIAL scopes `degraded[]` per endpoint, the mapping should read only
`/infrastructure`.

```yaml
unit_id: VAN-DEV-010
design_ref: DIAL VAN-DEVCC-R1 §§2.1, 3.1, 6.11
implementation_status: BACKEND_REPOSITORY_COMPLETE_LIVE_UNVERIFIED
owner_signature_status: PENDING
owner_signature_evidence_ref: null
project_truth_authorization: PENDING_OWNER_RECORD
```
