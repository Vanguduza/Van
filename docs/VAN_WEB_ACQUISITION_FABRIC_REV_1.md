# VAN Autonomous Web Acquisition Fabric — Rev 1

**Status:** implementation candidate on an isolated branch.  
**Authority:** subordinate to Hermes and the existing VAN Browser Fabric. This document does not supersede Project Truth or the security policy.

## Goal

Turn VAN's Browser Fabric into a durable, adaptive, unattended web-acquisition system without introducing a second authority plane.

The design deliberately absorbs the strongest mature crawler patterns into VAN itself: durable frontier, URL identity/deduplication, priority scheduling, adaptive/per-domain concurrency, bounded retries, checkpoint/resume, session pools, dead-letter handling and pluggable execution.

## Canonical layers

1. **Browser Harness + Hermes** — authority, grants, policy and evidence.
2. **JEV** — advisory ultrafast state/routing accelerator; no authority effect.
3. **Acquisition Frontier** — durable typed work items, leases, retry/dead-letter, domain controls.
4. **Katana adapter** — reconnaissance: route/JS/API/XHR surface discovery.
5. **Scrapling adapter** — primary lightweight/dynamic crawl and adaptive extraction.
6. **Steel adapter** — persistent self-hosted browser/session plane.
7. **Playwright / Browser Harness** — deterministic browser actuation.
8. **Stagehand** — semantic recovery/exploration only when deterministic paths are insufficient.
9. **Network observation** — browser/CDP and approved proxy telemetry for REST/GraphQL/WebSocket discovery.
10. **n8n** — slow orchestration, deferred retries and scheduled jobs; never browser authority.

## Crawlee features absorbed

The core frontier implements:
- durable queue/frontier;
- canonical URL identity and dedupe;
- priority ordering;
- bounded lease/fencing and crash recovery;
- per-domain concurrency and delay controls;
- rate-limit cooldown;
- typed retries with exponential backoff;
- checkpoint references;
- dead-letter convergence into VAN's existing automation dead-letter system;
- durable session-pool metadata;
- pluggable route selection.

Crawlee remains an optional future scale-out backend if qualification shows the internal frontier is insufficient for distributed volume.

## Routing ladder

```text
structured authorized endpoint -> DIRECT_HTTP
unknown site                 -> KATANA_RECON
qualified domain skill       -> HARNESS
semantic interaction needed  -> STAGEHAND
JS/browser/drift             -> SCRAPLING_BROWSER
default                      -> SCRAPLING_HTTP
```

JEV may accelerate signal classification or suggest an admissible route, but routing remains deterministic and inspectable.

## Trust boundary

The default DIAL supplier integration is outside-in. Public information and information visible through credentials explicitly supplied to DIAL are in scope. Supplier DNS, hosting, CDN, CMS, database and infrastructure administration are not prerequisites.

Secrets never enter acquisition work items. Work items carry only profile aliases, opaque network/session references and evidence/checkpoint references.

## Next implementation tranche

Runtime adapters must bind the typed routes to qualified local services:
- Scrapling HTTP/browser worker;
- Katana reconnaissance worker;
- Steel browser/session service;
- existing Browser Harness/Playwright and Stagehand services.

Each adapter must have health/readiness evidence, version pinning, bounded timeouts, output size limits and fail-closed behavior. Successful unknown-site interactions should compile into BrowserWorkflowCapsule/domain-skill candidates and require deterministic replay qualification before HOT reuse.

## Qualification gates

- migration and frontier unit tests green;
- crash/restart lease recovery;
- dedupe and checkpoint replay;
- rate-limit/cooldown simulation;
- session isolation;
- adapter unavailable -> typed retry/dead-letter rather than task loss;
- unknown site -> recon -> extraction;
- dynamic site -> browser route;
- domain drift -> adaptive recovery -> semantic escalation -> deterministic requalification;
- evidence remains digest/provenance-safe;
- trading/VATI authority remains unaffected.
