# Complete shared-service coexistence and canonical lifecycle qualification

## Final isolated result

**681 real native assertions passed with all shared services active together. 245 Python tests, eight Node admission tests, 26 full Compose-model checks and 28 lifecycle/parser/integrity checks passed.** The final Python and Node suites had no failed, errored or skipped tests. The native result reports zero production changes and complete cleanup; exact tested source bytes were checked before publication.

This continues VAN PR #102 from `348bb5ace86dce85410978cdd4c458a928843354`. It closes the previous *sequential-only native service coverage* limitation for the test's HTTP/data-plane workload. It does not deploy the system on `van-trading-core`, qualify production capacity or migrate Nissan GTR.

## One simultaneous installation, not isolated component substitutions

The native rehearsal used ONE fresh PostgreSQL 17.11 server, two application databases and the existing synthetic legacy fixture. Thirteen service processes ran concurrently: two Auth, two PostgREST and two per-project gateways, plus ONE shared Storage, ONE shared Realtime, ONE Edge Runtime, ONE Supavisor, ONE Postgres Meta, ONE original Studio server and ONE private administration gateway. No service was stopped to free memory for the coexistence workload.

The exact previously staged native versions remained Auth 2.196.0, PostgREST 14.17, Storage 1.74.0, patched Realtime 2.152.0, Edge Runtime 1.76.2, Supavisor 2.9.12, Postgres Meta 0.99.0 and original Studio `2026.09.07-sha-7996410`. Each component's source and runtime identities now appear in separate namespaces in the combined receipt to avoid accidentally assigning one component's version to another's source hash.

The source/runtime test ran through the authorized Commander as ordinary UID 1000 on `dial-control`, within the existing 768 MiB parent cgroup. The guard did not change any budget. Its highest sampled cgroup current usage was 537,440,256 bytes; highest sampled anonymous/kernel/shared-memory sum was 483,262,464 bytes. These are observations of the bounded test cgroup, not a sizing recommendation or a full application's production footprint. No OOM event was observed and the memory limit remained unchanged. A safety watcher would abort only this fixture if nonreclaimable memory approached the existing cap; it did not trigger.

## End-to-end application workflow

For EACH synthetic project:

1. A real authenticated user joined a private WebSocket and received the native database-change subscription readiness event.
2. A real permission-bounded Edge Function called that project's REST API to create a row and its Storage API to upload matching object bytes. No control-plane credential was supplied to the function.
3. Native Realtime delivered the exact newly written row. The selected project's Storage API returned the matching file, while another project's credentials could not retrieve it.
4. The native Supavisor connection and the project-scoped Meta API read that exact same row. The original Studio HTTP editor remained available at the same time.
5. Backend and operator SQL roles retained RLS restrictions. Fixture-only read policies granted those roles access to the selected user's rows, not to another user or to another project. No superuser/BYPASSRLS privilege was introduced.

Three rounds then concurrently exercised Edge, Storage, Supavisor, Meta, REST and Studio HTTP for both projects, plus private Realtime joins. Before/after snapshots recorded the same thirteen live service PIDs and same PostgreSQL directory throughout each round. This is 36 bounded concurrent HTTP/SQL requests across the six paths plus the explicit realtime checks, not a production soak/load benchmark.

## Failure boundaries while the other services remain live

The test deliberately stopped the original shared Edge process. Both projects' Storage, REST, Meta, Supavisor and private Realtime remained usable. Function calls failed rather than silently selecting another backend. Restarting the same Edge configuration restored correct project identity; every other service retained its original PID.

The test then deliberately stopped the original shared Supavisor process. Direct REST, Storage, Meta, Realtime and Edge requests remained usable. Pool connection attempts failed rather than being rerouted. Restarting Supavisor restored the two correct databases, and again only the intended service PID changed. This is fault containment between these specific services, not independent high availability of the shared PostgreSQL server.

The synthetic legacy database remained unchanged. No mutation was automatically replayed. Eleven coexistence observations bind the service identities, and the two complete flow receipts remain in `native-result.json`.

## Full lifecycle source contract

`tools/compose_lifecycle.py` now generates one guarded drop-in for the existing `vati-supabase.service`, not a second unit or Compose project. Start and stop use identical complete ordered inputs: BOTH original Compose files, all SIX shared/project overlays and all FIVE environment files. The existing project name and local Docker socket must be explicitly observed; no guessed project name is accepted. The original working directory and relative mount basis are retained.

The drop-in clears the original ExecStart/ExecStop lists, validates a pinned private checksum manifest before start AND stop, validates the full Compose configuration before start, then uses the same full model for `up -d --remove-orphans` and `stop`. It clears conflicting inherited Docker/Compose selector variables and explicitly binds the local socket. Source drift, missing overlays, missing environment files, unexpected service names, unsafe paths and mismatched original unit bytes are refused by the compiler.

Native `systemd-analyze verify` accepted both the exact original donor unit and the effective extended unit. The actual `sha256sum` binary rejected corruption of each of sixteen private test inputs and a missing input, then accepted the restored fixture inputs. The complete lifecycle validation passed 28 checks. The independent existing full Compose merge again passed 26 checks. No systemd manager action, Docker daemon call, container start/stop or production file read/write was performed by those model tests.

**The generated drop-in is still a candidate, not an admission receipt.** Root must independently observe the original host/project/socket/labels, verify all runtime secrets and mounted-file dependencies, preserve ownership/modes, admit target images and install a complete immutable release. A checksum is integrity evidence, not authority. A broken pin intentionally refuses start/stop until the original authorized owner reconciles the release; no automatic rollback, destructive `down`, force-recreate or bypass is supplied.

## Defects found and fixed without weakening production rules

The existing separate test harnesses used overlapping `node`, `admin_port` and `admin` member names. Those fixture attributes were namespaced before composition; native service business logic was not changed. The pool fixture no longer shrinks or restarts an already sufficient temporary PostgreSQL connection budget. Its own and later Storage/Realtime HBA prefixes are retained instead of dropping earlier pool/admin access rules.

The first full trial passed 585 checks but the pooled row comparison failed closed because a SELECT grant does not itself satisfy the table's authenticated-user RLS policy. The test now deliberately creates a fixture-only read policy for the exact enrolled user and separately verifies that the second user's rows are still hidden. No generator or live database policy was relaxed to make the test pass. The second run passed 628 checks; the final source added service failure containment and separate provenance namespaces, then passed 681. All earlier outcomes remain in the attempt register.

## Evidence and cleanup

`evidence/2026-11-05-installation/` retains native results and logs, Python/Node outputs, complete Compose report, lifecycle report, original attempts, source/evidence hashes and independent cleanup observation. Fifteen PIDs appeared across the successive coexistence snapshots; all were independently absent after completion. No executable from the staged native-runtime workspace remained running. The runner had already stopped PostgreSQL and removed the successful temporary databases and credentials. Failed private fixtures are removed only after exact ownership and completed-process checks; their nonsecret outcome records remain.

Historical component evidence is preserved. The 681 integrated assertions include many earlier component checks, so prior totals must NOT be added to it as independent acceptance coverage.

## Remaining production work

The original live Root route refused inventory/qualification with `OWNER_METADATA_EXPIRED`, `ROOT_INGRESS_RECORD_EXPIRED` and `ROOT_AUTHORITY_FENCE_BUSY`. No alternate privileged transport, self-issued qualification or fence bypass was used. Production still needs current target inventory, actual donor/CPU/OCI image qualification (including the Realtime derivative and admin image), original tenant/key/object identity reconciliation, real operator issuer/login/revocation, TLS/provider Auth and target network controls, coordinated encrypted off-host database/object/registry/secret recovery, sustained-load qualification and actual Nissan GTR migration/rollback.

All-services browser rendering was NOT exercised in this concurrent run: Studio was served and queried over real HTTP while the data plane was live. Earlier basic Firefox table-editor evidence remains a separate narrower browser proof. Full Studio features, production UI/session behavior and a large real workload are not qualified by this result.

**Disposition: complete native service coexistence, end-to-end synthetic data flow, selected failure isolation and guarded lifecycle source are demonstrated. Keep PR #102 draft; live VAN/VATI and Nissan GTR remain unchanged.**
