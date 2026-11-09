# Shared Storage in the existing Supabase installation

## Architecture

Use the pinned upstream `supabase/storage-api:v1.74.0` service in its native multi-tenant mode. **One Storage process/service and one PostgreSQL server** serve independent project databases. A small `dial_storage_control` database on that same server retains the upstream tenant registry; it is not another PostgreSQL server or Supabase stack.

Each project retains its own `storage` schema, RLS policies, storage database login and original Auth signing keys. The shared service selects a tenant from a fixed internal host rewritten by the trusted project gateway. It then uses that tenant's native registry entry, database credentials and keys. The service necessarily holds delegated access to multiple tenants: compromise of that shared service/registry is a common trust boundary, not VM-grade isolation.

The candidate derives new project tenant IDs from their immutable UUIDs, but **preserves an existing native tenant ID explicitly**. Do not rename VAN's original tenant, physical bucket directory, object root or signing keys during the switch. The rehearsal converted a synthetic existing single-tenant instance to multi-tenant mode and successfully read its original bytes and pre-conversion signed URL without relocation or rekeying. Actual VAN conversion remains unperformed.

## Implemented source

`tools/shared_storage.py` supplies staged role/schema/HBA statements, the shared environment, native tenant-registration payloads, project Nginx routing, a minimal overlay of the existing Compose `storage` service, and an exact-source-bound legacy Envoy route candidate.

The compiler has **no apply, upsert, restart, overwrite-database or deploy operation**. Its outputs contain credentials and API keys and must remain private. SQL creation deliberately refuses existing names; partial state requires original-outcome reconciliation, not blind replay.

New Storage logins and the registry login start NOLOGIN. The complete first-match HBA prefix retains the already configured Auth/REST/migration logins, adds each project's Storage login only for its own database, and restricts the registry login to its control database. Exact parsed rules and reload observation are checked before enabling the new logins. Existing Auth credentials are not regenerated or reactivated by this step.

Native upstream migrations create Storage tables and internal functions. The candidate creates only the empty scoped schema and permissions; it does not imitate upstream migrations. RLS policy selection remains the application's responsibility; the real test installs an owner-only policy for its synthetic objects.

## Routing and administrative boundaries

Project gateways require the selected project's API key for ordinary APIs and replace client-supplied tenant/forwarding headers. The native service verifies a JWT against the selected tenant's keys and applies its database RLS. An explicit GET/HEAD exception permits upstream-verified signed downloads and genuinely public objects without an API-key header. It does not permit anonymous uploads or expose the separate management listener.

The shared admin API requires an unrelated high-entropy control key. Project service-role JWTs are not admin credentials. Tenant readback suppresses database URLs and signing credentials. The registry uses upstream encrypted credential fields and a distinct encryption key; that key needs separate protected backup and rotation. This is not a claim that local object bytes or database backups are encrypted.

The original VAN Envoy Storage route must also be adapted before multi-tenant activation. `legacy_envoy_candidate` accepts only the exact reviewed template digest and a safe original native tenant ID, alters only `/storage/v1/`, overwrites the internal forwarded-host/prefix and removes conflicting identity headers. All other route bytes are preserved. It refuses ambiguous, stale or already-modified input. **An actual Envoy binary configuration validation is still required** before applying the candidate; source/Compose checks do not replace it.

## Preserving the existing Compose installation

The generated overlay changes only `services.storage`. It retains the donor volume mount, healthcheck and all unrelated services, adds no public port and no PostgreSQL container, and disables unqualified image transformations. The original single-project global credentials are cleared from this shared process; they must first be retained in the corresponding private native tenant registration. The original bucket and mount are explicit compiler inputs, never guessed from a generic example.

Docker Compose's effective-model check against the retained donor verified the service set, unchanged PostgreSQL and other services, unchanged Storage mount, no published Storage/admin ports, explicit multi-tenant state and preserved bucket mapping. This ran `docker compose config` only, not Docker containers. Compose emits literal dollar characters escaped as `$$` in reusable configuration output; the exact canonical form of the tenant-pattern end anchor is checked.

`vati-supabase.service` still needs an owner-reviewed complete overlay model in both start and stop operations. Its `--remove-orphans` option must never see an incomplete model. The generator does not edit systemd.

## Generate private candidate inputs

The private input is an owner-only JSON file in an owner-only directory. It has exactly:

- `credentials`: project UUID to original `project_uuid`, `jwt_secret`, `anon_key`, `service_role_key`.
- `shared`: newly reserved `control_password`, `encryption_key`, `admin_key`, and project Storage passwords keyed by native UUID-derived IDs. `new_secrets(projects)` can create this once in the protected provisioning context; it must not be rerun to replace active secrets.
- `object_bucket`, `object_path`: the explicitly verified original physical bucket and mounted path.
- `preserved_tenants`: project UUID to original native tenant ID where applicable.

The current new-project compiler verifies legacy HS256 API JWT signatures, issuer, audience, role, expiry and immutable project reference. It does not claim opaque publishable/secret-key support or automatically convert an unrelated legacy key format. Existing VAN key compatibility must be independently reviewed; never regenerate its keys to satisfy a compiler check.

```sh
python3 tools/shared_storage.py \
  --manifest projects.rehearsal.json \
  --private-input /absolute/private/reserved-storage-input.json \
  --client-cidr 127.0.0.1/32 \
  --out /absolute/private/new-storage-candidate
```

The loopback CIDR is a rehearsal example, not a production Docker-network guess. Outputs use mode 0600 in a new mode-0700 directory. `.env` values are literal single-quoted values, preserving the tenant-regex end anchor without environment interpolation. Never commit, print or publish the generated files.

## Reproduce actual runtime checks

The retained upstream source is tag `v1.74.0`, commit `01c95148a981a88b5f7e9014571a2926567b51e3`. The native rehearsal uses its generated server code under pinned Node 24.22.2 and a built `fs-xattr` binding. Source/package-lock and built-tree hashes are recorded. These native processes are not a test of the production container image or ARM64.

```sh
DIAL_REHEARSAL_STORAGE_NODE=/absolute/staged/node \
DIAL_REHEARSAL_STORAGE_SOURCE=/absolute/pinned/storage-source \
python3 tests/rehearse_storage.py \
  --pg-bin /absolute/staged/postgresql/17/bin \
  --pg-lib /absolute/staged/lib \
  --auth-bin /absolute/staged/auth \
  --rest-bin /absolute/staged/postgrest \
  --nginx /absolute/staged/nginx \
  --report /absolute/private/new-storage-result.json
```

The script creates only temporary databases/services and synthetic users; it never accepts an existing production endpoint. The ordinary-user test stops all children and removes successful fixtures. Failed attempts retain private diagnostics until checked and cleaned; public evidence excludes credentials and object archives.

## Recovery scope and outstanding gates

The local object-restoration drill stops the shared Storage process, copies a selected tenant's files with all extended attributes, verifies their hashes and metadata, detects corruption, retains the original tree, restores into an empty temporary namespace, and verifies actual API reads and pre-existing signed links afterward. The neighbouring tenant's object tree is unchanged.

This is **not** a consistent production database-plus-object backup. A real recovery point needs project metadata and object bytes captured under a single verified writer fence, native version/key/registry custody, protected manifest digests, encrypted off-host storage, and restoration at the actual data volume. A shared Storage restart is a shared outage, not independent high availability.

Other remaining gates include actual donor/container/architecture tests, original VAN tenant/keys/object inventory, DNS/TLS/CORS/rate limits, API-key rotation/revocation, browser SDK behavior, resumable/TUS and S3 compatibility if required, image proxy integration if enabled, original Envoy binary validation, native deployment admission and Nissan GTR application migration. Realtime, Edge, Studio and Supavisor remain separate workstreams. REA is not required.
