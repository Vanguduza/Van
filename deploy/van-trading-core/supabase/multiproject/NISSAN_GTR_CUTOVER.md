# Nissan GTR: Cloud to one existing DIAL Supabase installation

## Source-of-truth and non-negotiable preservation

Hosted control/commerce Supabase project: bicyjghgdnzlnjqxzoud, as documented at Vanguduza/Nissan-Gtr-Auto/docs/SUPABASE_REMOTE.md.
Retired project gylrgwqyuiwkyykardwc: recovery-only, DO NOT DELETE.
R2 carries heavy EPC catalog payloads and serves via catalog-live-r2; preserve it outside PostgreSQL.
Nissan GTR includes Web/Vercel, Android customer/management/delivery, iOS, POS, CRM, finance, HR, webhook payments, documents, SMS/WhatsApp/AI, live/offline workers.
Historical 3 October export: 115 of 125 hosted versions lacked matching then-active files. Current source commit `8131858c7c7479d178cbe9e246f83cb49ed80f5e` contains a reconciled FRESH-INSTALL baseline plus twelve forwards (thirteen active files), retaining the earlier history separately. That source consolidation is not live hosted-ledger reconciliation. Do not replay either historical folder or the fresh baseline onto populated production. The original Storage conflict-arbiter and other historical corrections remain source provenance, not fresh hosted acceptance.

## Dependency-ordered programme

G0. Freeze and inventory source revisions and canonical UI/feature lineage. Record database size, live migration versions, PG extensions, roles/grants, RLS policies, bucket metadata AND objects, Auth identities, refresh sessions, hooks, site URL, SMTP/OAuth/OTP, functions, cron, Vault, foreign data and publications.
G1. Generate and verify clean full source backups plus restore drill; do not use cloud snapshot existence alone as proof. Capture R2 manifests/checksums and full storage object list.
G2. Verify DIAL VM resource budget, backup capacity, network, TLS, credential store, WAN reliability. Whole VAN/VATI baseline and restore tests green.
G3. Provision GTR isolated project DB gtr_prod with production-worthy bootstrap and isolated Auth/REST project processes and registered shared Storage in the ONE current Compose installation. No source data yet. Project-specific issuer/API URL and secrets minted in vault, not committed.
G4. Reconcile hosted schema into an authoritative, reproducible baseline; preserve migration history and run upgrade/replay compatibility against PG17, extensions and scheduled jobs. Include permission/trigger/function definitions.
G4a. Qualify single-cluster scheduling. The locked baseline's pg_cron install and four cron.schedule calls need the source-bound central split in `shared_scheduler.py`, not a cron extension in every database. Verify actual cron database/timezone/engine, restricted runtime roles and native function ownership; stage every job inactive. The actual donor background-worker mode is off and its canonical `postgres` DB has no installed cron extension, so target scheduler setup remains a separately admitted operation. Compare Auth 2.197.0/Storage 1.79.36 used for the baseline reconstruction with the observed 2.196.0/1.74.0 donor before assuming schema compatibility. Full GTR SQL/financial/notification job execution remains unqualified.
G5. Restore a staging copy to isolated project database, verify schema digests, counts, financial total invariants, invoices/orders/staff/roles and negative RLS behavior. Auth users must remain separate from VAN users and retain canonical UUID linkage after restore.
G6. Configure GoTrue email/SMS providers and OAuth callback domains, site and redirect URL allowlists, password policy, signup hooks, MFA (if used), SMTP. JWT re-key strategy must be explicit; previously issued cloud tokens should reauthenticate unless safely preserved with verified issuer policies.
G7. Migrate Storage buckets/policies AND actual object bytes and checksum them. Keep Cloudflare R2 heavy catalog on original R2; adapt the catalog-live-r2 function/manifest registration against the new database and verify vehicle_search, vehicle_fitment, section_parts, diagram_parts and diagram_image.
G8. Package and deploy ALL required Edge functions and shared dependencies; function-specific JWT/unauthenticated provider webhooks must be explicit. Re-establish per-project function secrets, vault keys, cron/schedulers/worker auth and payment callbacks. Fix documented EcoCash substring status issue and recheck Paynow/webhook verification before live traffic.
G9. Validate web/Vercel and all mobile clients' new SUPABASE_URL + matching publishable/JWT credentials, OAuth deep links, realtime/storage URLs, invoice/receipt downloads, POS offline sync (PowerSync if applicable) and Temporal worker configuration. Do not silently enable fake RPC or preview-only modes.
G10. Parallel staging E2E (stock reserve -> checkout -> payment -> fulfillment -> receipt -> refund), negative BOLA/RLS, failure injection, duplicate callback idempotency, worker outbox durability, active customer/staff flows and isolated VAN regression.
G11. Cutover rehearsal: capture final incremental delta, rehearse write freeze and reconciliation, select DNS/API endpoint TTL, rollback evidence, finalize RPO/RTO budget. NO dual writable authority.
G12. With explicit signed owner release, pause writes briefly, replay validated delta, reconcile financial and Auth counts, update web/mobile secrets/config, switch hostname routing, monitor error, throughput, payment anomalies and WAL. Do not purge cloud; rollback at cutover boundary with state/accounting verification.

## Rollback

Before production write switch: revert only clients/routing to cloud, GTR staging is discarded/recreated without affecting VAN.
After switch with live new writes: cannot simply point back to cloud; choose canonical writer, reconcile all new orders/payments/identity changes, and perform controlled reverse sync or compensating transactions. Test rollback exactly in staging.
Cloud source and retired recovery project remain until expressly retired after independent acceptance and verified offsite backup.

## Explicit no-go gates

Any missing Auth/REST data independence, cross-project service-role reuse, unverifiable database history, partial object migration, missing provider webhook secret, uncleared payment settlement issue, untested RLS, unreliable backups, incorrect OAuth/OTP handling, unqualified project-specific Realtime/Edge, VAN trading regressions or untraceable deployment blocks production.

## Read-only history tooling available

`gtr_history_reconcile.py` now verifies the exact 173/125/13 source history sets and emits a nonce-bound READ ONLY/REPEATABLE READ metadata query for the active hosted project. It refuses a hidden, truncated, duplicate, RLS-filtered or view-backed ledger and keeps statement-array hashes distinct from source-file hashes. Ten repeated historical version/name pairs have different raw source bytes; do not infer behavioral equivalence or select a winner from filenames alone.

Use a current authenticated hosted connection and retain its original receipt separately: the query's declared project ref is not connection authentication. No such hosted query has been performed in this checkpoint. The code does not repair the ledger, mark the baseline applied, reset a database or grant cutover authority. See `HOSTED_HISTORY_RECONCILIATION.md`.
