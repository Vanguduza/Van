# VAN REA evidence study — the 39 original records

**Date:** 15 October 2026 · **Owner decisions:** OD-16, OD-17 · **Feeds:** blueprint Rev 1.6 §7.8.11, §7.9

## 1. Access and provenance

- **Path:** Desktop Commander device `dial-control` (online) → SSH as `ubuntu` to `van-trading-core` (10.77.0.4) with the existing `dial-oracle-admin` key. The `oracle-admin` devices were offline (last seen 521 h or more ago). The read was read-only: nothing on `van-trading-core` was changed. A study script ran there and only its printed summary came back.
- **Index:** `/opt/van-rea-lab/evidence/OPUS55_REA_VM_EVIDENCE_INDEX_20261015.json` lists `records: 39, unparseable: 0` and has scope "read-only static APK code architecture, no runtime/broker inspection".
- **Subjects:**

  | App | Version | SHA-256 | Notes |
  |---|---|---|---|
  | MetaTrader 5 `net.metaquotes.metatrader5` | 500.6260 | `6f220fc7…7bdd6` | Signer verified as MetaQuotes; 9,030 classes |
  | TradingView | — | VM secondary `c762b6df…cf584` | The index records "7 DEX byte identical, 53 assets identical, 4009 res/ files identical; manifest differs, signing not promoted" against the owner's original `dfbc561d…71b1` |

- **Not from the official store:** the 10:28 receipt still says TradingView `apk_status: NOT_ACQUIRED`; the later index adds the VM-secondary shards. TradingView findings therefore come from a byte-equivalent copy whose signing was not promoted, not from a Play Store install.
- **Tooling:** REA 6.5.0 with the JADX headless bridge 0.7.1 (pinned artefact `6e5eacf5…ff75`).
- **What was used:** class names, method names, field names and reference counts only. No third-party source code was copied, ported or kept in VAN (DEC-039). The raw decompiled method bodies in the `mt5_method_*` records stay on the VM.
- **Limits:** all of this is static structure. It shows what exists and how it is divided, not how it behaves at runtime. No broker, chart or order behaviour was executed.

## 2. The records

| Kind | Count | Records |
|---|---|---|
| Full class inventories | 8 | `mt5_all_classes` (9,030 classes); `tv_rea_dex1…7_full_classes` (40,053 across 7 DEX shards) |
| Keyword class searches | 8 | MT5 Chart, Indicator, Order, Position, Quote, News, Market; TV shard-1 Chart |
| Class inspections | 13 | MT5 `ChartRenderer`, `ChartSurface`, `TradeOrder`, `OrderSendFragment`, `IndicatorCollection`, `TradePosition`, `TerminalNews`, `NewsListFragment`; TV `ChartApi`, `ChartBridge` (266 methods), `ChartService`, `MarketDataProviderImpl`, `WebMessageChannel` |
| Method inspections | 3 | `mt5_method_1..3` (two ChartSurface callbacks, one order-result handler) |
| Reference traces | 5 | MT5 `ChartSurface`, `IndicatorCollection`, `NewsMessage`, `TradeOrder` (40 refs), `TradePosition` (46 refs) |
| Package inspections | 2 | MT5, TradingView |
| **Total** | **39** | |

None of the 39 records inspects an account class directly. The account findings in §4 come from the full inventories (class names in their packages), and are marked as such.

## 3. Chart engine findings and what was built

Each row was implemented in `android/app/src/main/java/com/dial/van/next/chart/` and has a test in `android/verification/.../ChartEngineReaEvidenceTest.kt`.

| Evidence (record → names) | VAN engine change | Test class |
|---|---|---|
| `mt5_class_detail_1` → `ChartRenderer.CHART_NOT_READY/REQUESTING/PROCESSING/READY/SYMBOL_CHANGED` | **Load state.** A symbol or interval change emits `SnapshotRequested`. While it loads, the old instrument's candles are not shown under the new name, no trade draft is accepted (an open one is cleared), streamed bars are ignored, and a late snapshot for the previous symbol is refused. Drawings are per instrument, and undo cannot cross an instrument change. | `LoadStateTest` (7) |
| `mt5_class_detail_1` → `CA_RULER_START/MOVE/STOP` | **Ruler.** Measures in instrument units: price change, percent, ticks and bars. | `RulerTest` (3) |
| `tv_rea_class_chartbridge` → `magnetMode`, `magnetEnabled` | **Magnet.** A drawing or ruler point within 14 dp of the bar's open, high, low or close snaps to that exact price; otherwise the price is rounded to the tick. | `MagnetTest` (2) |
| `mt5_extra_3` → `IndicatorCollection.getPreviousSettings`, `resetSettingsToDefault`, `resetLevelsToDefault`; MT5 `IndicatorLevelsFragment` | **Indicator memory and levels.** A re-added indicator uses the settings last used on this chart. Levels are editable per instance (RSI 30/70 and MACD 0 by default, at most 8), validated and versioned. Reset restores both settings and levels. | `IndicatorSettingsTest` (3) |
| `tv_rea_class_chartbridge` → `hideDrawingsShowOthers`, `hideIndicatorsShowOthers`, `hidePositionsAndOrdersShowOthers`, `lockAllDrawingTools` | **Layers and lock.** Drawings, indicators and trades can each be hidden, and a notice in words says so. Hiding trades **never hides a stop the broker has not confirmed**, nor the owner's draft. Locked drawings cannot be moved, removed or undone, but new ones can be added. | `LayersTest` (3) |
| `tv_rea_class_chartbridge` → `goToTime` | **Go to time.** Centres the bar at or before a timestamp. | `GoToTimeTest` (1) |
| `mt5_class_detail_3` → `TradeOrder.ORDER_STATE_REQUEST_MODIFY/REQUEST_CANCEL` | **Order states.** Adds `MODIFY_REQUESTED` and `CANCEL_REQUESTED`; such orders stay drawn until the broker confirms. | `OrderLifecycleTest` (1) |
| `tv_rea_class_chartbridge` → `hasChartChanges`, `getAutosave` | **Unsaved changes.** Indicator, drawing and style changes count as workspace changes; panning and zooming do not. | `UnsavedChangesTest` (1) |
| `tv_rea_class_chartapi` → feature groups | **Contract growth.** New capabilities `chart.measure`, `chart.magnet`, `chart.layers`, `chart.drawing.lock`, `chart.goto` and `chart.indicator.levels`; the forbidden list is unchanged. | `ContractGrowthTest` (1) |

**Confirmed by the records (already in the engine):**
- `ChartSurface` runs on a `TextureView` surface with `onWindowVisibilityChanged` and terminal load/unload hooks, which matches `ChartTextureHost` plus `FrameScheduler`.
- `ChartRenderer` uses `setDensity` / `setDarkMode`, which matches `ChartLayout(density)` and theme roles.
- `ChartRenderer`'s cursor modes (`CM_CROSS`, `CM_OBJECT_DRAG`, `CM_WINDOW_RESIZE`) match the crosshair, drawing-drag and pane-sizing interactions.

**Seen but not built (each needs a decision or later work):**
- **Replay practice trading.** TradingView's `barReplayBuy/Sell/ClosePosition` with autoplay delays and random dates. VAN's engine refuses drafts in replay by design. A simulated-only practice mode would be a new product decision (proposed as OQ-17).
- **Multi-chart sync and layouts** (`ChartApi.getMultiChartSync`, `getMultiLayout`).
- **Glyph atlas text rendering** (`ChartRenderer.createAlphabet`, `_mMaxTextureSize`). This is a host-side performance technique, to measure on the S24 before adopting.
- **Separate volume modes** (`CHART_VOLUME_HIDE/REAL/TICK`). VAN has volume on/off only, and should label tick volume as such where the broker supplies no real volume.

**Verification (`android/verification`, 15 October):**
- All 64 chart engine tests pass: 42 existing and 22 new.
- Full harness clean run (`gradle cleanTest test`): 125 suites, 1,050 tests, 0 failures.
- **Gates broken on purpose:** making `LoadRequest.matches` always true and removing the hidden-trades unconfirmed-stop line made exactly three tests fail:
  - `a late snapshot for the previous symbol is refused`
  - `a resync must be for the same instrument and interval`
  - `hiding trades never hides a stop the broker has not confirmed`

  The code was then restored.

## 4. Account management findings

All rows below come from class names in the full inventories; no account class body was inspected.

### MetaTrader 5 (`net.metaquotes.metatrader5`, `net.metaquotes.payments`, `net.metaquotes.brokers`)

| Area | Classes | What it shows |
|---|---|---|
| Accounts list and detail | `AccountsFragment`, `TabletAccountsFragment`, `AccountDetailsFragment`, `AccountParamsFragment`, `AccountsBase`, `AccountRecord`, `AccountLink` | Several saved accounts per install, with a detail and parameters view |
| Broker and server search | `BrokerSearchFragment`, `BrokerInfoFragment`, `BrokerInfo`, `BrokerInfoAPI`, `BrokerRecord`, `ServersListFragment`, `ServersBase`, `ServerRecord`, `ServerLabelInfo`, `BrokerServerView`, `BrokerSignature` | A broker directory, then a server list per broker, with signed broker information |
| Login and credentials | `LoginFragment`, `ChangePasswordFragment`, `PasswordWidget`, `QRCredentials`, `CertificatesFragment`, `CertificateImportActivity`, `KeysFragment` | Password login, password change, **QR-code login**, and **certificate- and key-based authentication** |
| One-time passwords | `OTPFragment`, `OTPBindFragment`, `OTPPassword`, `OTPCounter` | A built-in OTP generator bound to the account |
| Opening accounts | `OpenAccountFragment`, `AccountTypeFragment`, `AccountTypeButton`, `PersonalDataFragment`, `FinanceDataFragment`, `RealExperienceFragment`, `PreliminaryDataFragment`, `EULAFragment`, `AgreementsList`, `DemoResultRecord`, `AllocationResultFragment`, `VerifyInfo` | Demo opening, plus a **real-account application questionnaire** (personal, financial, experience) with agreements and verification |
| Server migration | `MigrationFragment` | The broker can move an account to another server |
| Leverage and margin | `ConLeverage`, `ConLeverageRule`, `ConLeverageTier`, `SymbolMarginCalculator`, `MarginValue` | **Tiered leverage** per account and per-symbol margin calculation |
| Funding | `Payment`, `PaymentAccount`, `PaymentAction`, `PaymentCommission`, `PaymentCurrency`, `PaymentField`, `PaymentInstitution`, `PaymentRedirect`, `PaymentState`, `PaymentVerify`, `Wallet`, `WalletPayment`; screens `PaymentMethodFragment`, `PaymentListFragment`, `PaymentInvoiceFragment`, `PaymentWebViewFragment` | **In-app deposits through payment institutions**, with commission, currency, verification, state, invoice and a web-view redirect |

### TradingView (`com.tradingview.tradingviewapp`)

| Area | Classes | What it shows |
|---|---|---|
| Broker directory | `feature.brokers.api.backend.{Broker, Brokers, CountryInfo, RatingDetails, Regulation, Site}`, `BrokersSortBy`, `BrokerType`, `BrokersRating*`, `brokers.list.{list, haveaccount, integrations}` | Ratings, regulation, per-country info, sorting, and separate "I have an account" and "integrations" paths |
| Broker sign-in | `brokers.login.*` with `ConnectionType`, `AuthorizationType`, `BrokerLoginConfirmationCheck`, `BrokerLoginTermsOfUse`, `CustomTermsOfService`, `BrokerPlans`, `BrokerLogin2fa*` | Login or OAuth per broker, terms acceptance, broker plans, and a two-factor step |
| Broker maintenance | `BrokerMaintenanceStatus`, `BrokerMaintenanceWarningPayload`, `BrokerMaintenanceLink`, `BrokerLoginMaintenance` | Maintenance is shown before and during sign-in |
| OAuth that survives the app being killed | `broker.oauth.impl.session.{BrokerOAuthSessionStore, CallbackSettlingStore, HeldOutcomeStore, BrokerOAuthSessionLostException, BrokerOAuthOutcomeLostException}`, `BrokerOAuthSessionEvictedException`, `BrokerOAuthCancelledException`, `BrokerOAuthPathRefusedException`, `crypto.{BrokerOAuthWireCodec, BrokerCryptoService, BrokerSessionKeys}` | The OAuth attempt and its outcome are persisted, callbacks are settled, a lost session or outcome is a named state rather than silence, and callback payloads are encrypted |
| Deleting the TradingView account | `deleteaccount.*` with `ConfirmDeleteAccount*`, `PasswordState`, `InvalidPasswordException`, `TooManyAttemptsException`, `PaidServicesExistException`, `AnonymizeResponse`, `CancelAccountDeletion*`, `CancelAccountDeletionBanner` | Password re-confirmation, attempt limiting, **blocked while paid services exist**, deletion carried out as **anonymisation**, and a cancellable grace period with a banner |

### What this changes in VAN (blueprint §7.9.11)

| # | Change | Evidence |
|---|---|---|
| A1 | OAuth and link attempts are persisted and survive the app being killed. A lost session or outcome is a visible, named state that the owner can retry or discard, never a silent failure. | TV `HeldOutcomeStore`, `CallbackSettlingStore`, `*LostException` |
| A2 | Broker maintenance is shown in the broker directory and before linking, not only on connection health. | TV `BrokerMaintenance*` |
| A3 | Delete and disconnect need fresh owner re-authentication on top of device-signed approval. Failed attempts are rate-limited. Deletion of personal data is anonymisation, with trade records kept under retention. | TV `PasswordState`, `TooManyAttemptsException`, `AnonymizeResponse` |
| A4 | The block on deleting with open positions or working orders matches TradingView's block on deleting with paid services. Keep it. | TV `PaidServicesExistException` |
| A5 | The broker capability matrix records **tiered leverage and margin rules** per account. Risk sizing reads the broker's actual tier for the position size, not one flat leverage figure. | MT5 `ConLeverageTier`, `SymbolMarginCalculator` |
| A6 | When the broker moves an account to another server, VAN detects it and runs re-verification instead of reporting the account as disconnected. | MT5 `MigrationFragment`, `ServerRecord` |
| A7 | Credential types can include an OTP binding and a client certificate or key, alongside passwords and OAuth tokens. All are stored only as credential references. | MT5 `OTP*`, `Certificates*`, `KeysFragment` |
| A8 | Pair the MT5 Expert Advisor bridge by **QR code** from the phone instead of typing a key. | MT5 `QRCredentials` |
| A9 | Opening a real account stays at the broker. MT5 collects personal, financial and experience data in-app; VAN does not hold KYC data. VAN links to the broker's own application. | MT5 `PersonalData/FinanceData/RealExperienceFragment` |
| A10 | The funding stance is unchanged: VAN never moves money (§0.3). MT5's in-app payment flow (institution, commission, currency, invoice, web view) supports VAN showing each broker's stated methods and commissions next to its cashier link. | MT5 `net.metaquotes.payments.*` |

**Still unverified:** MT5's investor (read-only) password. No class name shows it directly; it may be a field of `AccountRecord`, which was not inspected. It stays marked as general knowledge in §7.9.

## 5. Operations note

On `dial-control`, `/etc/ssh/ssh_config.d/60-dial-migration-source.conf` has the wrong owner or permissions, so plain `ssh van-trading-core` fails with "Bad owner or permissions". This study bypassed it with `ssh -F ~/.ssh/config`. The file was not changed. Someone with authority over that host should fix its ownership.
