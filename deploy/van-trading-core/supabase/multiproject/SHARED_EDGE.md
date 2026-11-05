# Shared Edge Functions — one Supabase installation

## Implementation and tested boundary

The existing donor `functions` service is extended to host **one shared upstream Supabase Edge Runtime v1.76.2**, with project-specific, ephemeral user workers inside that single process. Each project retains independently signed API credentials, its own Auth/REST database and private functions. This adds **no PostgreSQL server, no extra Supabase stack and no Edge service per project**.

Source: `tools/shared_edge.py` (private staged registry, per-project permission/secret compilation, exact gateway and donor Compose overlay); `edge/main/index.ts` (trusted single runtime main service); pinned `edge/main/package.json` and `package-lock.json`. The compiled `dist/` and `node_modules/` are not committed. The native main worker uses the pinned `jose` JWT verifier.

A project gateway replaces the client Host, tenant and project forwarding headers and supplies its private gateway key. The runtime accepts only a matching native project identifier and project gateway key, verifies HS256 JWT signatures with the selected project's issuer/audience, and enforces the function's declared `user`, `service_role` or API-key mode. CORS preflight is allowed only for exact reviewed origins; the gateway cannot expose the runtime's internal health endpoint or its private registry.

Each function has its own immutable source and permission revision. Source, secrets, project, function authority, environment and egress permissions contribute to its identity. Workers get only explicitly declared variables and permitted network destinations. Remote dynamic imports, direct disk access, process execution, other projects' function source and the trusted manager registry are denied in the tested runtime. Service-role credentials are passed to a user worker **only when its descriptor explicitly enables them**.

Concurrency, request bytes, response bytes, wall time and CPU time are bounded. An uncertain failure cannot be replayed automatically because the function may have performed a data mutation before failing. Native worker capacity remains occupied until a timed-out task actually settles; the test confirms bounded read-only capacity recovery rather than disguising a transient 429.

## Container image and original service preservation

The tested upstream is `supabase/edge-runtime:v1.76.2` at source commit `db47af5264be7a6e649d9488cc4f3f0da16ff875`. The staged amd64 runtime executable was extracted without a Docker daemon from the OCI image manifest digest `sha256:b331c6422f4f4bebd6052357da5f3c87610128c8cb530390ca024eb68cf4bf2e`, with layer and native-binary SHA-256 receipts retained.

The candidate overlay pins the **amd64 manifest digest** to prevent tag drift, but it is **not a production-compatible ARM64 qualification** and must not be applied to a different architecture without exact native validation. It modifies only `services.functions`, preserving the original donor services, the existing `/home/deno/functions` and Deno cache mounts, healthcheck and private service network. It adds only read-only private main/registry mounts, bounded limits, and an explicit main-service command. There is no published function port.

Only a private, non-interpolated, owner-protected registry is acceptable at runtime. The service checks file identity, mode and exact SHA-256 before parsing. If a registry, function, tenant or native identity already exists, the owner must reconcile original evidence; the generator does not overwrite or deploy. The `compile_bundle` API writes **new 0700 directories and 0600 files only**, with no command to apply SQL, recreate credentials, start a VM process, restart donor services or rotate production keys.

The existing donor functions must be audited before enabling the shared replacement. Reuse the actual VAN native function identities and keys; do not infer that the synthetic test registry matches production.

## Verified rehearsal

The isolated `tests/rehearse_edge.py` starts **one new PostgreSQL 17 cluster**, two Auth/REST project environments, project-specific gateways and one staged native Edge Runtime process. It exercises source-bound user functions, same-project REST calls, explicit service-role cases, per-project secrets, rejected cross-project JWTs/API keys, disk/network/process isolation, CORS, request/response limits, bounded CPU/wall time, worker slot reconciliation and restart.

Latest exact-source report: **209 real-service checks passed**, including the original **101 core checks**. The separate Python unit suite passed **185 tests** (zero failures, errors or skips). **16 Docker Compose effective-model checks passed** without running the Docker daemon. See `QUALIFICATION_EDGE_2026-11-04.md` and `evidence/2026-11-04-edge/`.

Reproduce from an authorized isolated non-root workspace with exact staged binaries:

```sh
BASE=deploy/van-trading-core/supabase/multiproject
python3 -m unittest discover -s "$BASE/tests" -v
python3 "$BASE/tests/check_edge_compose.py" --repo /private/source \
  --donor-ref cd4aab5377f2f1a6734a6cde7d6b8a7635a9a19d --report /private/new-compose-result.json
DIAL_REHEARSAL_EDGE_BIN=/private/staged/edge-runtime \
DIAL_REHEARSAL_EDGE_MAIN=/private/bundled/edge/main/dist \
python3 "$BASE/tests/rehearse_edge.py" \
  --pg-bin /private/postgresql17/bin --pg-lib /private/pg-libs \
  --auth-bin /private/auth --rest-bin /private/postgrest \
  --nginx /private/nginx --report /private/new-native-result.json
```

The bundled main worker was independently rebuilt using the pinned Node/npm lock and the same esbuild inputs, reproducing the exact native main bundle SHA-256 `774b3d2d83d0df06541f9c52680368bc0fd24aa8ef8863785f613e710b96e40a`.

## Gaps / no deployment claim

This is not a shared-host production security certification or a full Supabase Edge compatibility clone. A trusted shared main process holds all participating projects' selected credentials and becomes a common trust/failure domain. Privileged function descriptions, external egress/DNS rebinding, webhook signatures, scheduled/cron triggers, large uploads, streaming, user key rotation, package imports, browser SDKs and operational observability still need qualified production design. The native test uses synthetic functions; no actual Nissan GTR Cloud function, payment callback or customer record is migrated.

The **full one-host combined runtime** with Storage, Realtime and Edge all active together has not yet been qualified in a single native test. They were separately exercised against the same designed one-server topology, and existing Auth/REST/Storage/Realtime was tested together. Do not combine their overlapping check totals as a system-wide acceptance score.

Production requires current Root-signed VAN inventory, actual target CPU image admission, preserved legacy functions/keys, the original Envoy route, one complete `vati-supabase.service` Compose start/stop model, independent negative tenant tests, TLS/CORS/quotas, off-host recovery and a reversible Nissan GTR rehearsal. Studio and Supavisor remain separate work. REA is optional research, not a blocker.

## Complete simultaneous installation checkpoint

The newer `QUALIFICATION_INSTALLATION_2026-11-05.md` records 681 passing real assertions with every shared service and both projects' Auth/REST/gateways simultaneously alive on one private PostgreSQL server. It includes exact cross-service data flow, bounded concurrency and selected failure isolation. The canonical lifecycle candidate passed native systemd/integrity checks without being installed. This supersedes earlier *separate-only service coverage* limitations in this guide, but NOT the limitations on production deployment, original operator issuer, target images, advanced/full-browser Studio usage, actual-volume/off-host recovery or Nissan GTR migration. No production or cgroup-policy changes occurred.
