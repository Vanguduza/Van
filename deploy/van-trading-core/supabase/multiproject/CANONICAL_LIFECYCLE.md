# Existing Supabase canonical startup and shutdown

## Purpose

The original `vati-supabase.service` starts the two donor Compose files with `up -d --remove-orphans`. Launching additional project services outside that same startup model can cause a later service start to remove those legitimate services. Docker documents that `--remove-orphans` removes services not present in the selected Compose model. The new source compiler therefore binds start AND stop to one complete set of the existing installation's files, project name and local Docker socket.

This is an extension of the **same unit and same Compose installation**, not another systemd manager, worker ledger, deployment authority or Supabase stack. Existing DIAL Root remains the only production execution/admission owner. No service was installed, started, stopped or reloaded by this compiler's tests.

## Staged compiler contract

`tools/compose_lifecycle.py` accepts an exact original donor unit and a private JSON descriptor with:

- `schema_version: 1`, `kind: DIAL_SUPABASE_LIFECYCLE_INPUT_V1`, a stable `release_id`, exact immutable `source_sha`, and the original unit's SHA-256.
- `observed_project_name` from the original native Compose/container labels, and `observed_daemon_socket: /var/run/docker.sock`. These are required operator observations, not evidence fabricated by this tool. It rejects remote or alternative daemon selectors.
- `base_files`: the two exact original paths in order, each with SHA-256; `overlays`: exactly `core`, `storage`, `realtime`, `edge`, `pooler`, `admin`, all within the selected immutable release directory.
- `environment_files`: exactly the original `base` environment plus `realtime`, `edge`, `pooler` and `admin`; `protected_files`: additionally reviewed private runtime registry/env/gateway/main-worker file bindings.
- The exact new project slugs and effective service names from the independently reviewed complete Compose model. Missing donor services, missing project service triples, extra database services and duplicate/unsafe identities are rejected.

The compiler returns only three private artifacts: `90-dial-multiproject.conf`, `lifecycle-inputs.sha256`, and `lifecycle-candidate.json`. It has **no apply/deploy/restart/approve flag** and creates no original-owner qualification. It refuses pre-existing output directories and protects generated files with the existing private writer.

```sh
python3 tools/compose_lifecycle.py \
  --private-input /absolute/private/owner-observed-lifecycle.json \
  --original-unit /absolute/private/exact-observed-vati-supabase.service \
  --out /absolute/private/new-lifecycle-candidate
```

Do not substitute the fixture's `original-supabase` name, dummy hashes or synthetic paths for real observations. Do not guess the project name from a directory or start an independent Compose project to get around a collision. The old project label is part of the identity of its networks and volumes.

## Generated unit behavior

The drop-in uses systemd's empty `ExecStart=` / `ExecStop=` assignments to clear the old command lists. It keeps `Type=oneshot`, `RemainAfterExit`, the original working directory and timeout from the original unchanged unit. Both actions explicitly select the same local socket, original project name, project directory, five environment files and eight Compose files.

Before start, native `sha256sum --check --strict --status` verifies the immutable input bindings; `docker compose ... config --quiet` then validates the complete model. Only afterward would the unit perform the existing `up -d --remove-orphans` action. Stop also verifies the pinned inputs before executing `docker compose ... stop` against the **same complete model**. No `down --volumes`, implicit new project, `--force-recreate`, broad restart or automatic rollback is generated.

The unit clears inherited Docker/Compose selector variables to avoid silently targeting another daemon/project or omitting an overlay. Explicit arguments take precedence. It does not change the host's global Docker context, environment, networking, credentials or service configuration.

The manifest is **integrity, not authentication**. Root must protect the unit, checksum file, all pinned inputs, container images and runtime dependencies using the existing admission and filesystem custody model. Hashes in a user-editable file or a success printed by this compiler are not privileged execution evidence. An operator must inventory additional bind mounts, image identities and include/secret dependencies; the compiler cannot infer unseen production files.

## Required real deployment order

Observe the currently loaded unit/drop-ins, original Docker socket/project/container identities, full effective Compose model, legacy tenants, native secret/registry keys and capacity through the qualified Root route. Capture a tested recovery point before any conversion.

Reserve one exact source and target-compatible image set through the existing deployment owner. Stage all private files within the immutable release directory, retain original secret and tenant identities, verify hashes/permissions and native Compose/Envoy acceptance, and ensure every live service remains in the complete model.

Install the admitted drop-in atomically through the existing owner, reload the manager, perform the approved bounded transition, and read back actual service/database/route identities. A model parser's success does not prove this happened. Native private registrations and data migration must retain their own original-owner leases, absent-record observations and unknown-outcome reconciliation.

Any rollback must account for already-created project services and new application writes. Returning to the old two-file model while keeping `--remove-orphans` would remove the added services; therefore it is **not an automatically safe rollback**. Reconcile the complete previous release and project routing under the original owner, preserve data and credentials, and never replay an uncertain migration or registration.

If a pinned input changes or disappears, start and stop fail closed. Do not remove the guard or rehash unknown state merely to make the unit run. The original authorized owner must reconcile that exact release and action outcome. This can require an explicitly admitted scoped recovery operation; the generator does not mint one.

## Actual checks performed

`tests/test_compose_lifecycle.py` covers exact unit/source/project/socket bindings, complete file and service sets, missing/tampered/duplicate paths, unsafe characters, original donor drift, deterministic command construction, private output and no-authority claims.

`tests/check_lifecycle.py` ran the real installed systemd 255 parser against the exact original unit and the effective extended unit. It ran the actual native checksum tool against private synthetic input files, rejecting corruption of every bound input and a missing file, then accepting the restored fixture inputs. Twenty-eight checks passed. These checks did not read the real VAN `.env`, contact the Docker daemon, reload systemd or invoke start/stop.

The independent `check_management_compose.py` retained all 26 existing full-model checks; the complete integration rehearsal kept all shared services alive simultaneously. See `QUALIFICATION_INSTALLATION_2026-11-05.md` and `evidence/2026-11-05-installation/`.

## Primary behavior references

- Docker Compose project identity: https://docs.docker.com/compose/how-tos/project-name/
- Docker Compose multi-file merge: https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/
- Docker Compose `up` semantics: https://docs.docker.com/reference/cli/docker/compose/up/
- systemd service command/reset semantics: https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html

**Current state: source candidate and private parser/integrity qualification only. No live VAN unit was changed.**
