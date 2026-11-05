# Shared Storage native qualification — isolated candidate

## Verified checkpoint

**118 tests passed, zero failures/errors/skips. 245 real-service checks passed. Twelve effective Compose/legacy-route checks passed.**

This continues VAN PR #102 from `4ab8760d19fd74ed18c2d321258bd8bdd1d83626`. It extends the already-published independent database/Auth/API core and logical-recovery implementation with **one real upstream multi-tenant Storage service**, not a complete stack or Storage container per project.

The 245 native checks comprise the original 101 Auth/API/database checks plus 144 Storage, isolation, preservation, mutation and local object-restoration checks. The separate 118-test suite includes the existing 79 tests plus 39 Storage generation/security contracts. Four of those older unit-suite tests deliberately use HTTP stubs; the 245-check native run uses real services, not Storage stubs. The earlier 157-check database recovery drill remains retained evidence, not an additional 157 new checks in this run.

## Runtime and custody

Execution took place as UID 1000 on `dial-control` through the connected Remote Desktop Commander, in the existing isolated candidate workspace. The test created fresh temporary databases, synthetic users and temporary object files. No root elevation, Docker daemon, package installation, firewall change, production Supabase restart or live VAN/Nissan database connection was used.

Native versions: PostgreSQL 17.11, Auth 2.196.0, PostgREST 14.17, Nginx 1.24.0, Node 24.22.2. Storage was compiled from the unmodified official tag `v1.74.0`, commit `01c95148a981a88b5f7e9014571a2926567b51e3`, with its original dependency lock. The existing upstream esbuild script and path resolution produced the tested server; `fs-xattr` was compiled locally for the staged Node runtime. A complete upstream TypeScript/acceptance suite pass is not claimed. The exact lock, built tree, native binding, Node and test-source hashes are retained.

One PostgreSQL server held the two project databases, the upstream tenant-registry database and a synthetic legacy database. One shared Storage process handled both projects; service restarts were sequential. All processes created by the successful run were stopped and temporary data removed. Failed attempts recorded their actual failures and cleanup states.

This is not a donor-container, ARM64, actual VAN deployment, Root-signed admission or independent production acceptance receipt.

## Real service behavior verified

- Each project Storage login could connect only to its own database, not the other project, registry, legacy or administrative database. The registry login could not enter either project. New logins stayed disabled until the exact HBA prefix was installed/reloaded; old-prefix activation and repeated activation were refused.
- The native upstream API registered both tenants and completed real Storage migrations. Ordinary project keys could not administer the shared registry, and tenant readback did not return credentials.
- A synthetic existing single-tenant service wrote an original private bucket/object and issued a signed URL. After switching the same service configuration to multi-tenant mode with the original tenant/bucket/root/keys retained, the original bytes and signed URL still worked without relocation or rekeying. The other project could not redeem that signed URL.
- Both projects created private/public buckets and uploaded different bytes under the same bucket/key names. Upload, authenticated download, listing, public download and signed download worked against the real Storage API.
- Wrong-project user JWTs, service-role JWTs, API keys and signed URLs were denied. Unknown tenants, forged forwarding headers, missing credentials and anonymous writes did not cross project boundaries. The public gateway did not expose tenant/migration management routes.
- A second actual user in each project could neither read, replace, delete nor sign a private object owned by the first user. The first user's object listing remained scoped, and the first user could not read the second user's uploaded object. A project service role retained its intended access inside that project.
- Owner-authorized update/delete worked; new object bytes were verified after update and access failed after deletion. A download URL could not be replayed as an upload. Expired and meaningfully tampered signed URLs were rejected.
- Forty concurrent requests returned only each project's bytes. Metadata, object bytes and signed links survived a shared Storage restart.
- The local object recovery drill quiesced shared Storage, copied one tenant's bytes and every extended attribute, detected a corrupted copy, restored into an empty temporary namespace while retaining the original, then verified actual API bytes, content type, cache metadata, ETag and pre-existing signed links. The neighbour's object tree remained unchanged and its API worked afterward. Cross-project denial persisted.

## Effective deployment model checks

Actual `docker compose config` on the retained donor plus its current override and the proposed Storage overlay passed twelve checks. The same service names remain; PostgreSQL and every non-Storage service are unchanged; the original Storage volume mount and physical bucket mapping remain; no Storage/admin port is published; the selected multi-tenant configuration and literal tenant-regex end anchor are retained.

The exact-source legacy Envoy candidate changes only the original `/storage/v1/` mapping. Other route bytes remain unchanged; stale, duplicate and already-patched inputs are refused. Actual Envoy binary validation and live routing are still required before production activation. No Docker containers or Envoy processes were started by the model check.

## Source changes

`tools/shared_storage.py` contains the scoped role/schema/HBA generator, private native registrations, shared environment, project gateways, existing-service overlay, exact legacy-route candidate, credential-binding checks and private staged CLI. It rejects cross-project reused signing secrets/database passwords and mismatched or expired API-key credentials. It never executes SQL, starts a service, upserts an existing tenant or changes production state.

The compiler requires explicit original namespace/mount/bucket inputs. Existing API secrets are reused, not regenerated. Private output files have mode 0600 within a new mode-0700 directory. New-project HS256/project-ref credentials are the currently supported format; unrelated legacy formats require independent preservation work and must not be silently rewritten.

## Failures retained, not erased

Earlier uncommitted attempts failed at Storage startup/migration setup and Nginx map placement before reaching the original 174- and 183-check passes. Their original non-secret outcome records remain in the attempt register.

The expanded run exposed a flaky tamper assertion: changing the final base64url character can change only unused padding bits and still decode to the identical signature. The test now changes a meaningful signature byte and requires rejection; no upstream verifier or security check was weakened.

Candidate-generation tests found that the generic env writer rejects the regex end-anchor dollar sign. A dedicated literal, single-quoted Compose env writer now preserves that value while refusing newline/quote injection. The first effective-model assertion also mistook Compose's canonical `$$` escaping for a changed runtime pattern; it now compares the exact canonical literal form, not a loosely normalized pattern.

A minimal Envoy-route fixture exposed a final-newline boundary defect. The candidate builder now retains the final newline, while preserving the same strict source/hash/unique-route requirements. All final suites were rerun against the resulting exact source.

## Evidence and limits

See `evidence/2026-11-04-storage/`: final native result/log, 118-test output, twelve-check Compose report, package/runtime provenance, source/evidence manifest and earlier-attempt outcomes. No private bundles, JWTs, DB URLs, object archives or passwords are committed.

This does not qualify coordinated production DB-plus-object backup, off-host encryption, large uploads or restoration at actual Nissan GTR scale. The object drill is local, has a shared-service outage, and does not rewind database metadata. Shared Storage remains a common failure/trust domain. Native upstream JWT verification and per-tenant keys provide the tested boundary; this work does not add a new cryptographic issuer/audience verifier to upstream Storage.

Production gates still include current authorized VAN inventory, exact donor/container/architecture verification, original tenant/key/object mapping, full systemd Compose startup integration, Envoy binary validation, TLS/CORS/quotas, rotation/revocation, resumable/S3/browser SDK requirements, backup recovery, and Nissan GTR business-flow migration. Realtime, Edge Functions, project-aware Studio and Supavisor are not yet qualified. The current Root estate attempt returned `OWNER_METADATA_EXPIRED`; no privileged fallback was used to modify VAN.

**Disposition: shared Storage demonstrated in real isolated execution; keep PR #102 draft. No live VAN/VATI or Nissan GTR service/data changed. REA was not required.**
