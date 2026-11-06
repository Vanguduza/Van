# VAN Next — Accounts, Brokers, Funding and Withdrawal Technical Contract

**Status:** Design candidate; no provider money-movement adapter is qualified or enabled by this document.

## 1. Ownership and language

A *VAN link* is the local integration record and credential reference. A *broker trading account* is a remotely owned account, possibly subject to KYC/regional rules. A *funding account* is a provider wallet, bank, card or other payment rail. A *funds ledger* records the provider's cash movement, not unrealised P&L. These are distinct identifiers. `account_remove` means unlink local record; it is not broker closure. A hosted broker onboarding/funding page is still part of the guided in-app experience only when origin, identity and callback provenance are verified; VAN does not replace hosted payment security.

## 2. Canonical identities

- `owner_id`: verified owner principal; `device_id`: enrolled signature identity.
- `account_id`: stable internal UUID, not mutable alias. `broker_account_ref`: provider-scoped immutable account identifier.
- `provider_id` and `provider_profile_epoch`: configuration/entitlements; no hardcoded generic MT5 provider funding.
- `funding_intent_id`: durable exactly-once business intent; `idempotency_key`: unique to owner+provider+account+action+arguments digest+epoch.
- `payment_rail_id`: gateway to provider-supported deposits/withdrawals, *not* an instruction to store card credentials in Android.
- `beneficiary_ref`: vault-owned masked destination, never arbitrary clipboard injection.
- `currency_minor_units` and `decimal_amount`: exact decimal model, venue-specific unit rules; no binary float for money.

## 3. Dynamic operation capability matrix

At runtime the account projection MUST supply operation capability status, scope, relevant fees/limits, actual provider mode, required A4 action class, source age, current connectivity, dependency and reason. Supported states: `AVAILABLE`, `BROKER_HOSTED`, `REQUIRES_KYC`, `REQUIRES_LINK`, `REQUIRES_APPROVAL`, `TEMPORARILY_UNAVAILABLE`, `NOT_SUPPORTED`, `UNKNOWN_UNVERIFIED`.

Unknown is not available; disabled controls explain why and provide a broker-hosted verified route where applicable. A `GET /v1/trading/accounts` response containing equity is not permission to withdraw. Provider API availability, account entitlement, payment method admission, jurisdiction and KYC must be separately proven.

## 4. Operations

| Operation | Owner-facing contract | Owning executor and qualified postcondition |
|---|---|---|
| Link existing | Select broker, authenticate safely, select specific account, review permissions | Broker OAuth/client or supported bridge; fetch immutable broker account identity + account mode |
| Create demo | Broker-specific form or local paper account; distinguish both | Broker demo API or paper simulator; newly created ID and fresh account verification |
| Open live | KYC/terms/country/account type, provider-native or broker-hosted step | Provider-created record with owner mapping and account eligibility, no fake immediate activation |
| Edit local | Alias/label/notifications/selection where allowed | Validated atomic registry replacement and independent readback; no delete gap |
| Edit broker | Only fields officially supported by broker capability | Provider callback/readback; local change alone cannot assert broker update |
| Remove local | Explain effects on connector, not funds; fence exposures and pending payments | Owner A4, eligible zero/secured exposure state, local removal receipt; remote account remains |
| Close remote | Separate irrevocable closure request, checks funds/orders/positions/obligations | Broker accepted + independently verified closed status; pending closure distinct |
| Deposit | Choose account/provider/method, exact quote/fees, A4 if required | Provider intent and payment outcome; `SETTLED` only on broker-side credited reconciliation |
| Withdrawal | Masked beneficiary, exact amount/fee/net, expiry, KYC, A4, provider status | Provider payout/transfer record and independent settlement readback |
| Transfer | Select exact owner source/dest, eligibility and FX/fees | Provider transaction identity; both debit and credit readback and exception handling |
| Transactions | List cash/fees/settlement/reversals/filter/reference | Provider ledger, not simulated app cash and not position ledger |

## 5. Funds state machine and request skeleton

The provided `development-pack/STATE_MACHINES.json` is authoritative for design state names and allowed transitions. Example **proposed**, not existing, command:

```json
{
  "schema_version": 1,
  "type": "FundsIntentDraft",
  "intent_id": "uuid",
  "owner_id": "owner-ref",
  "account_id": "immutable-account-uuid",
  "broker_account_ref": "provider-scoped-ref",
  "operation": "WITHDRAW",
  "money": {"amount_decimal":"125.00","currency":"USD"},
  "beneficiary_ref": "vault-masked-ref",
  "quote_id": "provider-quote-ref",
  "provider_capability_revision": "capability-epoch",
  "expires_at": "ISO8601",
  "request_nonce": "unique-opaque"
}
```

Mutation must be separate from quote/discovery. A4 challenge binds the *exact* canonical bytes plus account/beneficiary/fees/expiry/action and cannot be recycled. Server must independently verify recipient ownership, broker account, current source, KYC state and authority. Provider credential grants are scoped, revocable and must never be exposed to chart, LLM or general browser contexts.

## 6. Unknown outcomes and reconciliation

`HTTP 200` means only accepted by a gateway, not settled. Redirect or submitted state means only that a hosted provider flow was opened/submitted, not that a deposit was credited. On timeouts, preserve idempotency and query provider by intent/transaction ID. Do not automatically repeat withdrawals or funds transfers without reconciliation. Accepted pending, settled, failed, reversed, unknown, chargeback and disputed must be separate. Publish immutable state-change receipts.

## 7. Security controls

- Authenticate the device and owner, inspect exact action prior to A4, verify signed challenge and scope at gateway and provider boundary.
- Enforce amount, currency, fee, beneficiary, provider account, environment (demo/live), KYC/region, account status, quote freshness and policy limits at the deterministic server controller.
- Prevent chargeback/pending cash from being counted twice as realised trading P&L or deposited available collateral.
- Preserve audit under encrypted storage; redact credentials, full beneficiary identifiers, payment links and private metadata from normal UI/analytics.
- Host callbacks must be verified by source signature, audience, state, nonce and provider readback; browser URL alone cannot authorize a financial mutation.
- Account status and transactions must work with read-only degradation without silently enabling monetary actions.

## 8. Gated delivery sequence

Capability inventory → provider discovery → local broker account record lifecycle → demo links and verified account readback → native Accounts & Funds UI → financial quote/review/readback contract → single admitted provider payment rail → failure/reversal reconciliation → more providers only with evidence → S24, broker sandbox, independent security and owner acceptance. No provider production credentials or live transfers in preparation.
