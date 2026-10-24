# Stagehand placement assessment — 2026-09-29

**Status:** RECOMMENDATION ONLY. No deploy file, systemd unit or topology is changed by this
document. Moving Stagehand changes canon (Rev 1.5 §13.1 and
`VAN-ADOPT-REMOTE-BROWSER-STREAMING-001.yaml` `unchanged_by_this_decision`), so adoption needs an
owner decision. This feeds component `deployment_host_approved` of
`STAGEHAND_PRODUCTION_ADOPTION_RECONCILED` in `VAN-ADOPT-STAGEHAND-001.yaml`.

**Authority for writing it:** owner instruction of 2026-09-29
(`auth-20260929-owner-jev-openmuse-convergence-r1`). Nothing here is signed or approved.

## 1. What runs where today (from the repository)

| Fact | Source |
|---|---|
| `vati-stagehand.service` runs as `van-browser` on van-trading-core, `Requires=vati-browser-harness.service` | `deploy/van-trading-core/systemd/vati-stagehand.service` |
| Stagehand binds loopback only (`127.0.0.1:9140`) and refuses a non-loopback bind | `stagehand_service.mjs` L27-35 |
| Stagehand reaches Chromium only through the Harness CDP handoff file and accepts only `http://127.0.0.1:<port>` | `stagehand_service.mjs` `readCdpEndpoint` L209-222 |
| Browser profiles, secrets and evidence live under `/var/lib/van-trading/browser/*` on the trading VM | `runtime.env.example` L14-18 |
| van-trading-core is 2 OCPU / 12 GB ARM64 and also hosts vati-commander, vati-vekl, vati-session@*, vati-supabase (authority store) and broker secrets | `deploy/van-trading-core/README.md` |
| Canon keeps Stagehand + Harness on private Trading Core; Chromium moves to a dual-homed Browser Stream Host reached via the Browser Control Agent (mTLS); raw CDP never crosses hosts | Rev 1.5 §13.1-13.2; streaming decision |
| `stagehand_or_harness_on_stream_host: forbidden` | `VAN-ADOPT-REMOTE-BROWSER-STREAMING-001.yaml` |
| "Trading Core isolation" gate is PENDING_LIVE | `docs/EXTERNAL_GATES.md` L61 |
| Programme A residency: dial-control = engineering only, never OWNER_PRIVATE/TRADING_PRIVATE at rest; van-trading-core = VATI/trading, not owner-private banks; VAN private plane = owner data | Memory Fabric Rev 1.2 §10 (DDS branch `gpt/memory-fabric-rev1-2-dds-20260929`; not yet canonical in this repo) |

Note: the VAN repository has no host-role registry naming a "VAN private plane" host. That role
is defined only by the Programme A blueprint; no such host is known to be provisioned.

## 2. Assessment

Ratings: **fit** / **conditional** / **conflict**.

| Criterion | dial-control | Browser Stream Host | trading host (current) | VAN private plane |
|---|---|---|---|---|
| Trust-zone separation from VATI/broker credentials | fit | fit | **conflict** — co-resident with commander, sessions, authority store, broker secrets; a prompt-injected page drives a process on the host that authorises trades | fit |
| Owner-session data residency (Google/NotebookLM profiles, cookies) | **conflict** — Programme A forbids owner-private at rest; Hermes PATH 2 memory processes session content | conditional — profiles land here under §13.5 option A, but only as Chromium's store, not Stagehand's | **conflict** — owner-private profiles at rest on the trading host, against Programme A §10 | fit |
| Network exposure | private, but shared with engineering Hermes/agents | **conflict** — public media interface; canon forbids Stagehand here | private; model-provider egress originates from the trading VM | private-only; model egress leaves from an owner-data host (egress policy per SECURITY_POLICY "External egress") |
| Browser Control Agent / same-Chromium | needs BCA client (cross-host) | same host as Chromium, but forbidden | today: loopback CDP. Rev 1.5 target: cross-host via BCA — **same open problem as any other host** | cross-host via BCA |
| Latency | VCN hop | best (co-located) | best today; one VCN hop in Rev 1.5 target | one VCN hop |
| Programme A topology | **conflict** | n/a (media host) | **conflict** (owner data on trading) | fit |

Two findings hold regardless of host:

1. **Same-Chromium gap.** Stagehand local mode needs a CDP URL, and this worker accepts only
   loopback. In the Rev 1.5 target, Chromium is on the Stream Host and raw CDP may not cross
   hosts, so Stagehand on *any* host other than the Stream Host needs a BCA-backed transport
   (e.g. a loopback CDP-subset shim on the Stagehand host that translates to the narrow BCA API).
   This does not exist yet. Staying on trading core does not avoid it.
2. **Latency is not the deciding factor.** Rev 1.5 states Stagehand is not in the touch-to-photon
   loop; model calls dominate a Stagehand step. A private VCN hop is small by comparison. This
   is an expectation, not a measurement; step 5 below measures it.

## 3. Recommendation

**Target: a dedicated private browser-worker role on the VAN private plane** — Stagehand and
Browser Harness together (the unit `Requires=` Harness), no public interface, reaching the
visible Chromium on the Stream Host only through the Browser Control Agent over mTLS.

Reasons: it is the only candidate with no conflict on trust-zone separation, owner-data
residency and Programme A topology. dial-control and the Stream Host are excluded by residency
and by explicit canon. The trading host is where it is today and is workable for repository
closure, but it keeps owner-private sessions and an untrusted-content-driven worker next to
trading authority, and its isolation gate is unproven.

Interim (until the owner decides and the host exists): keep the current trading-core unit, with
`production_default_max_tier` and domain admission as recorded, and do not admit owner-session
profiles beyond what canaries need.

## 4. Migration plan (not executed)

1. **Owner decision** on target host and on superseding Rev 1.5 §13.1's placement line; record it
   as a new decision (do not edit the streaming decision in place).
2. **Provision** the VAN private plane browser-worker host (private VCN only; no public IP).
3. **Build the BCA transport** for Stagehand (and Harness) — loopback CDP-subset shim or a
   Stagehand adapter over the BCA API — with the BCA's session/lease/generation/step-budget checks.
4. **Profiles:** implement Rev 1.5 §13.5 option A (encrypted, Stream-Host-mounted); the worker
   host stores metadata/leases only. Owner-private bytes leave `/var/lib/van-trading/browser`.
5. **Qualify side by side:** run the same observe/extract/act canary on the current trading-core
   worker and the new worker through the same harness; print both step latencies and both
   trading-core CPU envelopes (feeds "Trading Core isolation").
6. **Cut over** by switching the gateway's worker endpoint; disable, do not delete, the
   trading-core units.
7. **Decommission** trading-core browser units and scrub `/var/lib/van-trading/browser/{profiles,secrets}`
   only after a clean soak.

**Rollback:** re-point the gateway to the trading-core endpoint and re-enable its units (steps 6
kept them installed). Profiles remain on the Stream Host volume in both states, so rollback moves
no owner data.

**Must be proven before cut-over:** raw CDP not reachable from the worker host except via BCA
(port scan + BCA refusal of out-of-lease calls); no broker/VATI credential or route reachable from
the worker host; no owner-private browser bytes at rest on trading core or dial-control; the
canary passes with evidence token-free; measured step latency within the owner's accepted bound;
rollback exercised once.

## 5. Owner-only actions

- choose the target host (this document recommends the VAN private plane);
- approve provisioning (cost/hardware);
- approve superseding the Rev 1.5 §13.1 placement line;
- accept or waive the signed-ingress component of the Stagehand production gate.
