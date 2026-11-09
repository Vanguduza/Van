# Shared Realtime and combined fabric — isolated qualification

## Verdict

**PASS: 164 unit tests; 345 actual native real-service checks; 18 effective Compose/model checks.** No unit failures/errors/skips. The tests used the exact uncommitted candidate source verified by SHA-256 after the final run, then retained in the evidence set. This qualification does not authorize production deployment.

Execution venue: `dial-control`, existing connected Remote Desktop Commander, ordinary user UID 1000. No privileged operation, Docker daemon, firewall change, system package installation, connection to VAN production, account migration, or service replacement occurred. Every temporary process was stopped and the successful fixture was removed.

## Native runtime

- **One PostgreSQL 17.11 cluster**, with separate application databases and a synthetic legacy database.
- Supabase Auth 2.196.0, PostgREST 14.17, Nginx 1.24.0.
- One upstream Storage v1.74.0 service and independent project Storage metadata.
- One privately staged patched Realtime **v2.152.0** process, from upstream commit `c8b27c7a37a5c60fee5b5a11632231d8e2c0a8c9`.
- One shared tenant registry for Realtime on that PostgreSQL server, separate from Storage's control registry. No new PostgreSQL server, no project-specific Realtime processes and no donor service replacement.
- Realtime's original native replication source SHA-256 `8bf4a4a66683e6ae3348234d24551a6d06fef0059364335017fcb043b6236c5a` produced patched source SHA-256 `246686ac944ac3a342d34527d0de38e2b2bdce290bbe2156ade23e898025c81d` by exact-source amendment. The native test reported patched BEAM module SHA-256 `3855a2681cbbf5f57e93d9e3abe931bca7056dc1d7cb8f4478c5336b63354dc2`.

## Tested behavior

Two different project identities joined private Realtime WebSocket channels through their own gateways, observed database-change subscriptions, broadcast and presence, and did not receive each other's private messages. Database and channel RLS denied unauthorized joins. Foreign JWTs, service/API keys, hostnames, forged forwarding headers, unexpected tenant namespaces and requests for management APIs were refused.

The real native release registered each tenant and used its own database scope and short-lived PostgreSQL replication slots. A source-bound fix ensured that `realtime.messages` broadcast replication-slot identifiers did not collide across project databases in the same PostgreSQL cluster. The test observed temporary-slot release on shutdown and re-established valid channels and broadcast after a shared-service restart.

Both projects retained functional Storage access, original signed Storage downloads, per-project HBA boundaries and REST RLS while shared Realtime was active. The synthetic legacy fixture remained unchanged.

The **345-check combined run** includes core Auth/REST/database checks plus shared Storage and shared Realtime checks. The previously recorded standalone **192-check Realtime** and **245-check Storage** runs and independent **157-check logical-recovery** drill are separate checkpoints with overlapping assertions; do not sum them.

The tested final-source suite: `realtime-unit-verified-02.log` **164/164**. Model check: `realtime-compose-verified-03.json` **18/18**. Real combined run: `fabric-result-03.json` **345/345**, with source-hash matching, cleanup complete and zero production effects. Prior failed Realtime attempts are retained by state in `attempts.json`, not rewritten as passes.

## Source/model checks

The effective Compose merge retains the original service set and PostgreSQL service, changes only the expected shared Realtime/Storage configuration, and adds project Auth/REST/gateways in the existing installation. Realtime's image remains an **invalid placeholder** in the model check; image build and ARM64 target are explicitly unverified. The memory-limit model assertion was repaired to interpret Compose's actual string-form size values and require the specified effective limit; this was a test-harness correction, not a relaxation of runtime resource limits.

The exact pinned original Realtime module was separately patched in memory, and its generated SHA-256 matched the derivative-build script's expected hash. The Dockerfile describes a candidate build and is not a production image receipt.

## Evidence custody

Committed files under `evidence/2026-11-04-realtime/` contain the last exact-source JSON report, raw passing logs, model report, source/result identity manifest and nonsecret history of earlier outcomes. Runtime files, private databases, signing secrets, JWTs, Auth data and session credentials are not committed. Evidence from the prior core, recovery and Storage milestones is preserved.

This native rehearsal is **not** Root-signed admission, Zuul release approval, target-container/ARM64 execution, or a complete disaster-recovery certification. The live estate status currently reports `ROOT_INGRESS_RECORD_EXPIRED` and `ROOT_PRE_DISPATCH_ADMISSION_BUSY`, so actual VAN inventory and deployment are not claimed.

## Remaining deliverables

Production target observation, exact upstream image qualification, native admission and rollout; production HBA/wal/CDC quotas, Vault/tenant credential custody, user revocation, websocket/TLS and backpressure tests; one canonical systemd/Compose boot and recovery model; coordinated encrypted off-host PostgreSQL/Storage/Realtime recovery; Edge Functions, Studio, Supavisor, Nissan GTR schema/history/Auth/Storage/R2/payment integration and reversible cutover. REA is optional research rather than a blocker.

**Disposition: isolated multi-project Auth/REST/Storage/Realtime integration passed; PR #102 stays draft until production gates are met.**
