# Nissan GTR archived SQL — exact-body reconciliation

## Result

**Ten of ten** shared migration version/name pairs in the pinned *legacy* and *hosted-export archive* contain the **same SQL body** after removing only the two exact provenance-comment lines and blank separator added by the hosted export. Six hosted bodies also have exactly one additional final linefeed. Four bodies are byte-identical immediately after removal of the known export prefix.

This is a material refinement of the earlier report that the raw archived files had different SHA-256 hashes. **The raw hashes remain different and must not be overwritten, collapsed or described as identical files.** Their executable SQL body bytes, including all internal whitespace, comments, string literals, statements and ordering, are unchanged in these ten pinned archived pairs. The only accepted difference besides the known export header is one final LF byte.

The pinned source is `Vanguduza/Nissan-Gtr-Auto@8131858c7c7479d178cbe9e246f83cb49ed80f5e`. The baseline manifest SHA-256 is `e63bbf3ef3f57d6cf4750879e2aceb5b0fdf794d20fcaf562616b8065cd9f3cc`. All **313** prior source inputs remain individually hashed and retained; this proof covers **only** the ten known cross-family overlaps.

## Method

`tools/gtr_archive_equivalence.py` uses the existing `gtr_history_reconcile.source_catalog` immutable public-source loader. It refuses altered source bytes, unexpected versions, filenames, variant-set hashes, missing inputs, a different overlap count, and any internal SQL-body difference. The only removable wrapper must be precisely:

```
-- Exported from the hosted project's supabase_migrations.schema_migrations (<exact version> <exact name>).
-- Source of record for what production ran; see supabase/live-history/README.md.

```

The values of `<exact version>` and `<exact name>` are derived from the pinned source filenames. Nothing else can be removed or normalized. A version with an extra SQL comment, changed SQL keyword, missing semicolon, altered internal whitespace, extra newline beyond one allowed terminal LF, CRLF substitution, wrong wrapper or wrong SHA-256 is refused.

The report lists the original hashes and normalized body hash for each of the ten pairs, but it **does not include SQL source, passwords, connection strings, customer rows, payment material or any hosted credential**. Its `production_deploy_authorized`, `may_apply_migrations`, `may_repair_hosted_history`, `may_activate_canary`, and `may_cutover` fields are all false.

## Reproduction

From the pinned, private, independently acquired GTR source tree:

```sh
python3 tools/gtr_archive_equivalence.py \
  --source-root /absolute/private/pinned-gtr-source \
  --out /absolute/private/new-archived-equivalence
```

Only a new owner-private output directory (0700) and a single 0600 JSON result are permitted. The tool has no SQL connection, network, Docker, SSH, database mutation, hosted capture or deployment operation. Re-running against an existing output is rejected.

The real ten-pair pinned source run returned:

- `overlap_count=10`
- `exact_wrapper_only=4`
- `wrapper_plus_one_final_lf=6`
- `remaining_archived_body_differences=0`
- report SHA-256: `02daca1f670b27fd4de6f8483e3f38a8f7e6cfd3e1c4d547e1cac85b13e90348`

The full existing Python test suite plus 20 new refusal/equality tests passed **387 tests** without failure, error or skip. All source comparisons ran as UID 1000 in the isolated `dial-control` workspace. No live production state, client credential, hosted service, Supabase project or database was accessed. Full immutable source and test hashes are retained under `evidence/2026-11-09-gtr-archive-equivalence/`.

## Unchanged release boundaries

This is **archived source-body equivalence**, not proof of which migration statements the **current** hosted `supabase_migrations.schema_migrations` ledger contains, nor proof of current schema, row data, Auth, Storage/R2, financial records, payment webhooks, or reversible cutover readiness.

The current active hosted ledger still requires an independently verified, authenticated **read-only** capture using the separate history-reconciliation tool. Do not mark migrations applied, replay the 173 legacy migrations, replace the 125 hosted-export records, or choose a baseline merely because ten archive pairs now reconcile. Keep the original archives and their raw hashes.

The prior live-canary execution safety refusal remains unresolved and **must not** be bypassed by this code or by another execution route. The same original single-installation Supabase/ARM64 admission, role/HBA, signed release, coordinated recovery and business-flow qualification are still mandatory.

**No Nissan GTR Cloud data was copied or modified; no second database or project endpoint was activated. PR #102 remains draft until independently qualified.**
