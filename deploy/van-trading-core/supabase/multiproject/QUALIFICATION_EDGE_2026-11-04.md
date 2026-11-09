# Edge Functions native qualification — 4 November 2026

## Verdict and exact scope

**PASS: 185 Python tests, 209 real-service checks, and 16 Docker Compose configuration/model checks.** Zero test failures/errors/skips in the final unit suite. This advances the isolated multi-project candidate beyond shared Realtime without changing the existing architecture.

The **209** Edge checks include the original 101 database/Auth/REST core checks and synthetic native Edge tests. The earlier published **345** combined Auth/REST/Storage/Realtime checks remain valid separate evidence; they overlap and must not be summed. Neither one proves all five services were running together in a single native fixture.

## Native environment

Tests ran as UID 1000 via the connected authorized Commander on **`dial-control`**, within the existing disposable workspace. One temporary PostgreSQL 17.11 server held two independent project databases and a synthetic legacy fixture; real Auth 2.196.0, PostgREST 14.17, Nginx 1.24.0 and one native Edge Runtime v1.76.2 process ran only on private loopback endpoints. No Docker daemon, sudo, system package upgrade, live VAN/OCI, Nissan GTR Cloud connection, credential import or production effect occurred. All successful-run processes were terminated, and the fixture's temporary data was deleted.

The native Edge binary came from the pinned upstream amd64 OCI layer. Its SHA-256 was `ff195e6fb5e6df5fd87eef5603cbe8bcc9c7cea7d74f2027c7a7daa1608bcbb0`; the pinned image manifest was `sha256:b331c6422f4f4bebd6052357da5f3c87610128c8cb530390ca024eb68cf4bf2e`. Cryptographic release-signature verification and ARM64 qualification were **not** claimed. The Node24/esbuild worker bundle was reproduced byte-for-byte; the private output bundle hash matched the one exercised by the native runtime.

## Native verification

Actual Deno workers executed synthetic function requests and returned project-scoped identity and REST data. Wrong-project signing secrets, service-role credentials, API keys, forged host/tenant headers and foreign function imports were denied. Native per-worker permission tests refused reads of the trusted manager registry and another project's source, file modification, process execution, privileged environment variables, foreign/internal network access, remote imports and worker-factory access.

Timeout and CPU-bound functions were constrained; the test also observed that a worker can retain its native capacity after the HTTP deadline until its final settlement, and required bounded read-only reconciliation before another CPU-limit check. One deliberately effectful function wrote a synthetic row then raised an exception; the system returned failure without disclosing its private canary or replaying the mutation. This is essential for at-most-once claim integrity.

Project isolation persisted after an Edge Runtime restart. Rejected cross-tenant requests did not alter the synthetic legacy database. Native health did not become public. One restricted main process held the two projects' private registry entries; that shared trust domain is not equivalent to independent containers or machines.

## Model tests

The generated Compose overlay was merged with the exact donor at `cd4aab5377f2f1a6734a6cde7d6b8a7635a9a19d`; **16/16 effective checks** passed using Docker Compose parsing only. No containers were pulled, built or started. The image is pinned to an amd64-only digest, and target architecture verification remains mandatory.

The model retained all original services, the unchanged database, original functions volume mounts and healthcheck, zero public Edge ports and a separate read-only private main and registry. It removed legacy single-project function credentials from the shared main environment and required an exact new private registry hash. Project keys are passed only to qualified per-function worker instances.

## Failed attempts and corrective evidence

Earlier native runs returned FAIL at 101, 145 and 148 checks before the first successful 207-check run. The fresh post-unit-test run returned FAIL at the CPU-bound assertion after a native operation's native capacity remained reserved; an additional source change introduced a bounded read-only capacity reconciliation before the CPU test. Another attempt still failed under native CPU timing for one project; its evidence is retained and no prior PASS was relabelled. The subsequent full fresh execution passed **209** checks with all processes cleaned up.

The final source includes the original SHA-pinned compiled native worker, the compiler, offline source/unit contracts, retained failure attempts and correct status. It is not a guarantee that every native timing will behave identically under production load. Additional soak/load tests are required.

## Evidence and outstanding qualification

Under `evidence/2026-11-04-edge/`: `native-result.json`, `native-run.txt`, `unit-tests.txt`, `compose-model.json`, `compose-model.txt`, `upstream-provenance.json`, `attempts.json` and a source/evidence SHA-256 manifest. No private registry, project JWT, DB URL, customer data or executable OCI layer is committed.

The native validation excludes actual donor container activation on `van-trading-core`, target ARM64/AMD64 matching, Root-signed admission, complete combined Storage/Realtime/Edge process coexistence, production tenancy secrets, CRM/payment/webhook functions, scheduler and R2 integrations, unified live Envoy/TLS, full backup/restore, Studio/Supavisor and GTR migration.

**Keep VAN PR #102 draft. No live VAN/VATI or Nissan GTR production state was changed.**

Documentation correction: the native executable digest above was reconciled with the retained raw runtime receipt; the executable and historical JSON evidence were not changed.
