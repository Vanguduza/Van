# Candidate account edit and owner review contracts

The existing account onboarding path now resolves an edit against the current native record. It preserves every omitted setting and credential reference, accepts an explicit `enabled` boolean, and rejects unsupported fields or ambiguous control values before any effect. A label edit no longer resets mode, currency, login, demo/live configuration, policy reference or connection metadata. New accounts keep their existing defaults; an existing environment credential reference is never replaced with an empty file.

This is source work for the original BE-002/004/005 units. It does not complete native account migration, retirement, financial activation or whole-unit admission.

## Owner approval and actual writer

The gateway requests the native read-only `account_review` command for `account_upsert`. Under the alias operation lock, it resolves the public before/after records, changed fields, original argument digest and current native resource version. Credential references expose only their kind. The gateway validates the complete typed contract, public-only field set and canonical digests before allocating an approval.

The existing A4 challenge binds the complete resolved review in its signed parameters. Verification recomputes the current review. The native operation authority reference includes its review digest, and the actual locked writer recomputes that digest before its first effect marker. A changed interpretation after gateway verification is therefore a known pre-effect refusal; it cannot silently execute a different edit. Existing one-use proof, original operation identity, native version CAS and unknown-effect recovery remain in force.

The existing Android approval path displays the resolved target context and before/after changes before the biometric prompt. Missing, incomplete or private-locator-bearing reviews prevent dispatch. Cancelled or locally expired approvals send no action. The original challenge timestamp still crosses the biometric boundary unchanged. This repairs an existing approval screen; it is not a new frontend or redesign before BG-001.

## Supplied frontend contract

`GET /v1/trading/accounts/catalog` requires a current paired owner device. It describes exactly the existing account actions, their input schemas, approval requirements, resolved-review requirement, original-result readback capability and broker credential-key names. Credential inputs are marked `writeOnly`; the catalogue returns no credential values or native file locations. `VanGatewayClient.tradingAccountCatalog()` supplies the existing Android consumer seam.

The challenge response now has a typed `resolved_review` contract. The original owner feature `OF-TRADING-003`, screen `van.trading.accounts.add`, function identities, authority records and historical citations remain intact. Their derived contract extensions point to the catalogue, review and existing operation readback rather than inventing new feature identities or screen acceptance.

## Connection protection

Existing-account native identity changes require verified migration; a generic metadata edit is not migration evidence. cTrader linking cannot overwrite an existing alias. Gateway preflight also rejects account-creation/link collisions before allocating an approval.

Production Deriv registration, credential verification and adapter construction accept only the official secure WebSocket provider bases. An owner can disable a legacy record with an invalid endpoint without first repairing its identity. This does not admit that endpoint for verification, credential traffic or production adapter use. Low-level injected research transports remain separate test seams.

## Evidence and limits

`receipts/ACCOUNT_UPDATE_REVIEW_SOURCE_20261022.json` records the actual counterexamples, source hashes, full private-PostgreSQL trading suite, gateway checks, Android JVM/build/lint, owner-registry checks and source-fault observations. The original omissions produced twenty failing assertions before the repair; those assertions are not twenty independent defects.

Native physical-account uniqueness across aliases/hosts, verified connection migration, exposure/order/funds/lease-safe retirement, provider-effect finality, native adjudication and device-epoch migration remain required programme work. No native provider, handset, signing, release or profit acceptance is issued here.
