# Shared pooling and project-aware administration — isolated qualification

## Final result

**224 Python tests passed; eight Node admission-control tests passed; 248 real native/API/browser assertions passed; 26 complete Compose-model checks passed.** The final source suite had no test failures, errors or skips. The final native result reports PASS, successful tracked-process cleanup and zero production changes. Source identities were checked against the actual result before publication.

The native result is `admin-result-11.json`, retained as `evidence/2026-11-04-management/native-result.json`. It continues the source from `7e8a5d7ec12ecb391e8af19b1de4af53b03988b9`. Earlier isolated passes and failures are preserved in the attempt register; none is relabelled as a successful later revision.

The 248 assertions include existing database/Auth/REST checks, real Supavisor session/transaction behavior, real Meta/Studio HTTP administration and eighteen browser assertions. The earlier 345-check Storage/Realtime exercise, 209-check Edge exercise and 157-check logical-recovery exercise overlap this baseline and are **not additive acceptance counts**.

## Actual execution and versions

The authorized connected Commander ran the work as ordinary UID 1000 on `dial-control`, in a private, disposable fixture. It used one new PostgreSQL 17.11 server, two synthetic project databases, a separate fixture pooler registry, and a synthetic legacy database. Supabase Auth 2.196.0, PostgREST 14.17, Nginx 1.24.0, Supavisor 2.9.12, Postgres Meta 0.99.0 and the original compiled Studio `2026.09.07-sha-7996410` were actual services, not labelled HTTP stubs.

Supavisor source: `e8719d9ac5a43604c46d2d9e15bb34c76dea8f12`. Postgres Meta source: `f380cc5be21edef4e77d9838c732d1f20af0b3c0`. Studio and pooler native files were extracted from exact official amd64 OCI layers without using the Docker daemon. No system package was installed. Native Node 22.23.2 was extracted from the Studio image after the initial Node 24 attempt failed because the Meta dependency's packaged native profiler did not match that ABI. The original Meta TypeScript build passed, and original upstream source trees remained unchanged.

A pinned-source test adapter compiled Supavisor's application module in memory solely to bind all native listeners to `127.0.0.1`; its exact upstream source digest and adapter source are retained. Pooling/authentication business logic and release files were not patched. The original distributed-server launch had failed in the unprivileged environment. The final rehearsal runs one native node without claiming distributed-cluster behavior or production network qualification.

No production VAN/VATI or Nissan GTR database, service, credential, systemd unit, network rule, cgroup budget or live container was changed. Root estate inspection remained refused with `OWNER_METADATA_EXPIRED`; no privileged alternative was used to bypass that gate. REA was not used or required.

## Pooler assertions

Two native tenants used separate database credentials through both session and transaction pooling. The actual current database and current SQL role matched the selected project; transactions worked. Another project's password, username/tenant combination and requested startup database could not select another database. Raw pooled logins could not cross the HBA boundary. Attempts to become the cluster administrator, create cluster roles or read `pg_authid` were rejected.

Twenty-four concurrent reads remained project-scoped and observed backend connection counts stayed within the test's bound. A shared Supavisor restart preserved the native registry, both tenant connections and direct REST operation. The original fixture database and ACL were preserved.

New pool/admin roles stayed NOLOGIN until the exact first-match HBA prefix was observed and reloaded. Missing-prefix activation and repeated activation were refused. Actual native Supavisor registry migrations ran in its fixture-only control database. Production generation instead retains the observed original `_supabase` registry and its original Vault key; it generates no replacement registry database and does not reseed the donor's default tenant.

The test discovered that authorized Supavisor management readback contains database passwords. Raw responses were never published. The adapter now binds the response to its project and emits a redacted receipt. Project service-role JWTs could not authenticate to the independent native management API. The original PUT route is explicitly documented as an UPSERT: absent-record observation and an original-owner exclusive lease remain required before any real mutation.

## Administration assertions

The private gateway verified short-lived Ed25519 operator tokens and server-side project memberships, not browser-chosen connection strings. The product contains only a public verifier. Its test issuer and identities were synthetic; no real DIAL identity issuer or current Owner credential was minted.

Both project SQL requests reached the actual expected database and project-specific `_admin` role through the real Postgres Meta encrypted-connection mechanism. Injected `pg`, `x-connection-encrypted`, tenant and forwarding headers did not change the selected database. The operator could create and query its own public table, but could not become `postgres`, create global roles or read other database password material. The same SQL credential could not connect to the other application database, default database, legacy fixture or pooler registry.

Restricted operators saw only their permitted project; another project's API and SQL routes were hidden before native Meta was called. Read-only operator scope could not execute SQL. App service-role tokens, expired or overlong operator tokens and wrong-audience/unknown identities were rejected. Cookie-authenticated writes required the exact same origin. Foreign Host/Origin and unsupported platform APIs were refused. Meta's unselected default connection intentionally had no working database authority.

The administration queue kept at most two executing SQL queries per operator, while allowing another operator to proceed. Pending work waited before execution rather than being replayed. Separate Node tests covered queue bounds, timeout, cancellation, fairness, retained active ownership and idempotent release. Process-health probes required the exact private registry digest and key and did not claim platform readiness.

## Actual browser behavior — limited but real

Eighteen browser checks passed against the unchanged compiled Studio UI using Firefox 142.0.1 and pinned Playwright Core 1.56.1. For each project, a fresh browser session opened the private selector, clicked the selected project, rendered the actual Studio table editor, displayed `admin_fixture`, clicked that table and read its distinct row: **17 in one project, 29 in the other**. Browser-authenticated metadata and SQL confirmed the corresponding database. This is real rendered interaction, not just a successful HTML fetch or a fabricated UI screenshot.

The sessions were deliberately separate fresh browser processes. Seamless same-tab switching, the complete Studio product, all advanced menus and all user workflows remain unqualified. Unsupported API-key/settings/integration panels can still return 501; they are not forwarded to an unrelated default project's backend. The original UI's `postgres` dropdown label did not change the actual restricted backend role.

The fixture was kept within its existing 768 MiB Commander cgroup: the earlier tested pooler/Auth/REST/project-gateway processes were stopped before the browser stage. PostgreSQL, Meta, Studio, the project gateway and fixture TLS remained running. Therefore this is sequential native and browser verification within one fixture, **not simultaneous full-stack load qualification**.

Chrome's explicitly sandboxed launch failed because its setuid helper was not qualified on this host. Its initial default-launch attempt was not accepted as a sandbox-qualified run. No root permission, host sandbox configuration or cgroup limit was changed. The later Firefox path used no explicit sandbox-disable flag, but the host reported namespace restrictions; complete browser-sandbox qualification is not asserted. Only the exact test HTTPS origin and trusted staged UI assets were permitted. The ephemeral self-signed TLS fixture is not production certificate acceptance.

## Complete deployment-model check

The 26-check configuration merge covers core project Auth/REST/gateways, shared Storage, shared Realtime, shared Edge, the existing Supavisor and one private administration gateway alongside the original Studio and Meta. It retains one PostgreSQL server, all original services, the original pooler registry URL and Vault key, original mounts and the existing loopback-only Studio port. The new administration service publishes no port, requires an admitted non-root UID/GID, has a read-only root filesystem and mounts its registry read-only.

This ran `docker compose config` only. It did not build, pull or start containers. The admin image and Realtime derivative image are deliberately invalid placeholder references in this parser test. Supavisor and Edge are pinned to tested amd64 digests; no target ARM64 claim is made. Original lifecycle/startup configuration still needs full owner-reviewed integration before `--remove-orphans` can see any added services.

## Defects found and retained

Earlier attempts exposed unqualified distributed Supavisor startup, native management password readback, Meta's Node ABI mismatch, browser sandbox/fixture-host problems, overly restrictive asset admission, and Studio's actual query-body contract. These failures led to exact loopback fixture adaptation, redacted management receipts, the correct native Node version, a separate bounded static asset queue, and accepting only the documented false-valued timeout flag while still rejecting timeout bypass.

UI bursts also needed bounded pre-execution request queuing without increasing simultaneous database queries. Native browser reuse exceeded the small fixture's reliable memory envelope; two fresh browser sessions provided a bounded and honestly narrower proof. Failed timeouts and earlier one-project-only render passes remain failures. No workload limit was silently increased and no SQL mutation was automatically replayed.

One daemonized `epmd` from the original failed distributed start was later discovered beyond the tracked child list. It was matched to the exact staged executable and ordinary-user identity, terminated, and independently checked absent; no unrelated process was signalled. `cleanup-observation.json` distinguishes this reconciliation from the native runner's tracked-child cleanup flag. Failed private fixture data was removed only after original completion/ownership/process checks.

A historical documentation transcription of the Edge binary hash was corrected to match its unchanged raw native receipt. The earlier binary and JSON evidence were not altered.

## Remaining production gates

Actual VAN resource and architecture inventory, original database/tenant/key/object/registry observation, target image build/admission, existing operator issuer integration and revocation, production TLS, complete Studio feature coverage, full simultaneous service qualification, native lifecycle fencing, coordinated encrypted off-host recovery and actual Nissan GTR migration/rollback remain open. Trusted project SQL roles still share cluster metadata and infrastructure failure domains; they are not a substitute for hostile-tenant VM isolation or a complete malicious-query resource policy.

**Disposition: shared Supavisor and scoped Studio/Meta basic administration demonstrated with real services and browser interaction. Keep PR #102 draft and production unchanged.**
