# Mission provenance — Memory Fabric Rev 1.2 and Jev × OpenMuse Convergence Rev 1

**Recorded:** 2026-09-29, Claude Code session `session_01CSuhPskbCd3shvSXX1P7JT`.
**Authority:** owner instruction supplied directly in that session. See
`auth-20260929-owner-memory-fabric-rev1-2` and `auth-20260929-owner-jev-openmuse-convergence-r1`.
No device, biometric or cryptographic signature is claimed.

## Oracle entrypoint exception (mission-scoped)

`CLAUDE.md` makes the persistent Oracle orchestrator the entrypoint for repository development.
Neither `dial-oracle-control` nor `dial-oracle-status` was available in this session, so the
Oracle gate status is **NOT VERIFIED**. No `PRODUCTION_GREEN` or `DEVELOPMENT_READY_FALLBACK`
result is claimed.

The owner authorized this mission to proceed anyway, as a bounded exception:

- no production deployment, no live Oracle mission-state change, no merge to protected branches;
- the Oracle architecture and `CLAUDE.md` are unchanged;
- the resulting work must be compatible with the Oracle/Hermes execution model before any
  production activation.

## Programmes and branches

| Programme | DDS branch | VAN branch |
|---|---|---|
| A — Memory Fabric Rev 1.2 | `gpt/memory-fabric-rev1-2-dds-20260929` | `gpt/memory-fabric-rev1-2-van-20260929` |
| B — Jev × OpenMuse Rev 1 | `gpt/jev-openmuse-convergence-r1-dds-20260929` | `gpt/jev-openmuse-convergence-r1-van-20260929` |

Programme A must not depend on Programme B. Programme B may consume Programme A's bounded
context interface only.

## Verified starting points (2026-09-29)

| Ref | SHA | Relationship |
|---|---|---|
| DDS `master` | `e2e0c2b7dbd51250306a0850969fbe128d52b426` | base |
| DDS `gpt/jev-service-rev2-1-build-20260925` | `6200f8fcbbbd26387756ad6d3937b0eb979be651` | 177 ahead / 50 behind master |
| VAN `main` | `12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af` | base |
| VAN `gpt/jev-control-centre-20260925` | `f3df7a10e12fc76d25f958e9f19cb0b25c798168` | 123 ahead / 19 behind main |
| VAN `gpt/openmuse-van-convergence-r1` | `a8d3f1930ad9f6d479717ab1a5e161cfd2f87144` | 195 ahead / 0 behind main |

## Upstreams observed (git ls-remote, 2026-09-29)

| Upstream | HEAD | Latest tag | Licence |
|---|---|---|---|
| vectorize-io/hindsight | `1e427025b4d4c01e8ad6385dd04e02102886a5c4` | `v0.10.1` | MIT |
| volcengine/OpenViking | `0f31ece6b8213db36a7619f9212e6f2c39282c7a` | `v0.4.22` | AGPL-3.0 |
| browser-use/jev-ultrafast | `1231850a0bf1a0c0341fe408ef1668dbbfdfac46` | none | MIT |
| browserbase/stagehand | `ad2bf12ea7abd95bb1d6f3a59600842a0954fffb` | `@browserbasehq/stagehand@4.1.0` | MIT |

OpenViking HEAD has moved since the Rev 1.1 review commit `1f4f7039`. These are observations,
not adoption pins; exact-version adoption requires the qualification gates in each blueprint.
