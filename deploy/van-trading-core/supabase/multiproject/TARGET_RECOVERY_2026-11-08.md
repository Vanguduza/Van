# Actual ARM64 target recovery checkpoint — 8 November 2026

## Completed against the real installed donor

The existing PostgreSQL 17.6 installation on `van-trading-core` now has a verified pre-migration recovery snapshot. It was captured from the running donor, encrypted using AES-256-GCM CMS, copied to `dial-control`, successfully decrypted there, verified against every retained payload hash, and returned to the target for a native ARM64 boot-restoration drill.

**17 physical-restore checks passed. SHA-256 comparisons matched all 57 application tables across `postgres` and `_supabase`. Cluster-role attributes and password verifiers also matched.** No raw passwords, rows, secrets, private keys or database archives are committed. A damaged ciphertext was rejected during an actual authenticated-decryption test.

The archive contains a native `pg_basebackup` with streamed recovery WAL, logical dumps of both databases, global roles, PostgreSQL configuration, the `db-config` key volume, original systemd unit, Compose/environment configuration and the Storage directory. Native `pg_verifybackup` passed. Original Auth users, Storage buckets and Storage object counts were zero at capture; this is not a general coordinated active-writer object/database backup or a continuous PITR guarantee.

## What actually ran

The physical restore used the **already installed ARM64 image** `supabase/postgres:17.6.1.136`, exact local image ID `sha256:f371b5f3f2ac0a05703f33d6e6134515fb2498cab708fb948a0aeb7481467c00`. It booted the returned physical cluster in a temporary verification container with no network, no published port, ordinary PostgreSQL UID, bounded memory/CPU, dropped capabilities and disabled cron execution. The physical cluster system identifier was preserved, recovery completed, and both original databases and their 57 table catalogues were present. A second network-isolated verification compared canonical row digests and private role-password-verifier digests.

All temporary restore containers were stopped and removed. No persistent extra PostgreSQL server or Supabase stack was deployed. Every original Supabase container kept its original ID and start time, and all eleven remained healthy. The original `vati-supabase.service` stayed unchanged.

A precise, temporary local-only replication HBA record for `supabase_admin` was required for the native backup stream. It was added under an exclusive operation lock, checked, reloaded, and **restored byte-for-byte** immediately after capture. This was a reversible live configuration interaction, not a zero-interaction claim. No original application rows were changed and no existing service/container was restarted.

## Backup custody

Encrypted snapshot size: **4,796,688 bytes**. Ciphertext SHA-256: `e6f4147d9c994d220e12664cacf311935f54f9de0a8b2f87ea1c23c0eb42f0ff`. Decrypted archive SHA-256: `aa198399b59d4f7593849afbbde465f254d5a2f3833109e640e5cdb91ab5d222`.

The encrypted target copy is under `/var/backups/dial-supabase/pre-canary-20261108-r1/`; the verified off-host encrypted copy and separate-host private decryption key are under `/var/lib/dial-supabase/recovery-custody/arm64-20261108-r1/` on `dial-control`. These are root-private locations, not application API resources. No key material is in this repository. This is off-VM protection, not independent-provider geographic disaster recovery or hardware-backed key custody.

After successful restore and row verification, only this operation's known plaintext payload, returned plaintext archives, copied restore tree and temporary in-container basebackup directory were removed. The encrypted copies, separate-host key and non-secret receipts remain. No original mounted database, Storage object or unrelated backup was removed. Filesystem deletion is not a certified secure erase of underlying media.

## Canary activation was NOT executed

The next planned step was two synthetic project databases with real ARM64 Auth/REST gateways on the existing PostgreSQL server. An initial shell submission failed before writing a script because the POSIX shell rejected `pipefail`. The corrected canary command was subsequently refused by the execution tool's safety layer before execution. It was not rerouted or disguised. Readback confirmed no canary script/work directory, no canary containers and only the original `postgres` and `_supabase` databases.

The current ARM64 Auth/REST image identities were observed, and a small ARM64 Nginx image was staged, but this does **not** qualify an active target multi-project Auth/API service. The original shared-service runtime is still the original two-file Compose installation, not the proposed overlays.

## Evidence and authority

`evidence/2026-11-08-target-recovery/` retains public receipts for backup, off-host custody/decryption, physical restore, row-fingerprint matching, cleanup, staged image and final target state. Exact managed-job references and command digests correlate to original TetherBound receipts. These are actual owner-authorized target observations, not self-issued Global DIAL/Zuul qualification or a production release acceptance.

This checkpoint continues source `e62c0f0948b1d0c8778deee3a4460bc378a003eb` and changes only documentation/evidence. The existing 681-assertion all-services rehearsal and component source remain unchanged. The live canary boundary is still closed; no new project database, active public endpoint, Nissan GTR migration or production cutover is claimed.

Remaining gates: a permitted exact-owner canary activation route, target-native Auth/REST and shared-service isolation, ARM64 Realtime derivative/admin images, original tenant/key/object mapping, admitted canonical Compose startup/rollback, operator identity/TLS/providers, sustained load/quotas, complete recovery retention/PITR and Nissan GTR application/payment/R2 migration rehearsal. Keep PR #102 draft.
