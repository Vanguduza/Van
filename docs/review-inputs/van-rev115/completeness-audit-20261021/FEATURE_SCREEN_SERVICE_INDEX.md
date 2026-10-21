# Complete feature and screen review index

Audited blueprint commit: `172d2143d3e6d2ec4b401376f5ef5a4cf94c7429`. Every row is specification coverage, not a runtime pass. Full requirement/action/service/test/atom/truth inventories and original fields are in `INVENTORY.json`.

## All 93 named features

| Feature | Purpose | Primary FE | Test owners | Binding review |
|---|---|---|---|---|
| VNX-F-HOME-01 | Spatial Home | FE-004 | FE-001 | REVIEW: primary absent |
| VNX-F-HOME-02 | State-aware metallic orb | FE-004 | FE-004 | Primary included |
| VNX-F-HOME-03 | Home quick hub | FE-004 | FE-004 | Primary included |
| VNX-F-HOME-04 | Attention preview | FE-004 | FE-004 | Primary included |
| VNX-F-HOME-05 | Smart briefing | FE-004 | FE-004 | Primary included |
| VNX-F-HOME-06 | Semantic deep links | FE-003 | FE-001 | REVIEW: primary absent |
| VNX-F-HOME-07 | Home state fallbacks | FE-004 | FE-003 | REVIEW: primary absent |
| VNX-F-TRADE-01 | Trading Home | FE-006 | FE-006 | Primary included |
| VNX-F-TRADE-02 | Portfolio summary | FE-006 | FE-009 | REVIEW: primary absent |
| VNX-F-TRADE-03 | Markets overview | FE-006 | FE-006 | Primary included |
| VNX-F-TRADE-04 | Watchlists | FE-006 | FE-006 | Primary included |
| VNX-F-TRADE-05 | Opportunity discovery | FE-006 | FE-014 | REVIEW: primary absent |
| VNX-F-TRADE-06 | Charts entry | FE-006 | FE-007 | REVIEW: primary absent |
| VNX-F-TRADE-07 | Intelligence entry | FE-006 | FE-013 | REVIEW: primary absent |
| VNX-F-TRADE-08 | Account context entry | FE-006 | FE-010 | REVIEW: primary absent |
| VNX-F-CHART-01 | Native chart previews | FE-007 | FE-007 | Primary included |
| VNX-F-CHART-02 | Rich chart terminal | FE-007 | FE-007 | Primary included |
| VNX-F-CHART-03 | Instrument search and alias mapping | FE-007 | FE-001 | REVIEW: primary absent |
| VNX-F-CHART-04 | Price and timeframe precision | FE-007 | FE-001 | REVIEW: primary absent |
| VNX-F-CHART-05 | Indicators and parameters | FE-008 | FE-008 | Primary included |
| VNX-F-CHART-06 | Drawing tools and persistence | FE-008 | FE-008 | Primary included |
| VNX-F-CHART-07 | Chart overlays and crosshair | FE-007 | FE-007 | Primary included |
| VNX-F-CHART-08 | Bar replay sandbox | FE-008 | FE-008 | Primary included |
| VNX-F-CHART-09 | Multi-chart layouts | FE-008 | FE-008 | Primary included |
| VNX-F-CHART-10 | Orderbook market depth | FE-007 | FE-007 | Primary included |
| VNX-F-CHART-11 | Chart alert creation | FE-007 | FE-006 | REVIEW: primary absent |
| VNX-F-CHART-12 | Order and position overlays | FE-007 | FE-009 | REVIEW: primary absent |
| VNX-F-CHART-13 | Chart source integrity | FE-007 | FE-001 | REVIEW: primary absent |
| VNX-F-CHART-14 | Chart observation export | FE-014 | FE-014 | Primary included |
| VNX-F-CHART-15 | Chart renderer failover | FE-007 | FE-007 | Primary included |
| VNX-F-ORDERS-01 | Open positions | FE-009 | FE-009 | Primary included |
| VNX-F-ORDERS-02 | Position details | FE-009 | FE-009 | Primary included |
| VNX-F-ORDERS-03 | Pending orders | FE-009 | FE-009 | Primary included |
| VNX-F-ORDERS-04 | Order creation proposals | FE-009 | FE-009 | Primary included |
| VNX-F-ORDERS-05 | Owner order approval | FE-009 | FE-004 | REVIEW: primary absent |
| VNX-F-ORDERS-06 | Broker order receipt | FE-009 | FE-009 | Primary included |
| VNX-F-ORDERS-07 | Stop loss take profit management | FE-009 | FE-009 | Primary included |
| VNX-F-ORDERS-08 | Partial reduction intents | FE-009 | FE-009 | Primary included |
| VNX-F-ORDERS-09 | Trade history and TCA | FE-011 | FE-009 | REVIEW: primary absent |
| VNX-F-ORDERS-10 | Risk command centre | FE-011 | FE-009 | REVIEW: primary absent |
| VNX-F-ACCOUNTS-01 | Accounts overview | FE-010 | FE-010 | Primary included |
| VNX-F-ACCOUNTS-02 | Link existing broker account | FE-010 | FE-010 | Primary included |
| VNX-F-ACCOUNTS-03 | Create demo account | FE-010 | FE-010 | Primary included |
| VNX-F-ACCOUNTS-04 | Apply for live broker account | FE-010 | FE-010 | Primary included |
| VNX-F-ACCOUNTS-05 | Edit local account configuration | FE-010 | FE-010 | Primary included |
| VNX-F-ACCOUNTS-06 | Edit broker account details | FE-010 | FE-010 | Primary included |
| VNX-F-ACCOUNTS-07 | Credential rotation | FE-010 | FE-010 | Primary included |
| VNX-F-ACCOUNTS-08 | Account connection validation | FE-010 | FE-010 | Primary included |
| VNX-F-ACCOUNTS-09 | Unlink local account | FE-010 | FE-010 | Primary included |
| VNX-F-ACCOUNTS-10 | Close remote broker account | FE-010 | FE-010 | Primary included |
| VNX-F-ACCOUNTS-11 | Deposit funds | FE-010 | FE-010 | Primary included |
| VNX-F-ACCOUNTS-12 | Withdraw funds | FE-010 | FE-010 | Primary included |
| VNX-F-ACCOUNTS-13 | Transfer between accounts | FE-010 | FE-010 | Primary included |
| VNX-F-ACCOUNTS-14 | Payment methods | FE-010 | FE-010 | Primary included |
| VNX-F-ACCOUNTS-15 | Transaction and settlement history | FE-010 | FE-010 | Primary included |
| VNX-F-ACCOUNTS-16 | KYC account restrictions | FE-010 | FE-010 | Primary included |
| VNX-F-ACCOUNTS-17 | Leverage and account permissions | FE-010 | FE-010 | Primary included |
| VNX-F-INTEL-01 | Intelligence overview | FE-013 | FE-013 | Primary included |
| VNX-F-INTEL-02 | News feed | FE-013 | FE-013 | Primary included |
| VNX-F-INTEL-03 | Full article analysis | FE-013 | FE-013 | Primary included |
| VNX-F-INTEL-04 | Economic calendar | FE-013 | FE-013 | Primary included |
| VNX-F-INTEL-05 | Instrument and portfolio impact | FE-013 | FE-013 | Primary included |
| VNX-F-INTEL-06 | Source verification and contradictions | FE-013 | FE-013 | Primary included |
| VNX-F-INTEL-07 | Live VAN trading analyst | FE-014 | FE-014 | Primary included |
| VNX-F-INTEL-08 | Strategy evidence analysis | FE-014 | FE-012 | REVIEW: primary absent |
| VNX-F-INTEL-09 | Trading opportunity reasoning | FE-014 | FE-013 | REVIEW: primary absent |
| VNX-F-INTEL-10 | Cross-signal intelligence packet | FE-014 | FE-014 | Primary included |
| VNX-F-INTEL-11 | Learning and outcome review | FE-014 | FE-014 | Primary included |
| VNX-F-WORK-01 | Work command centre | FE-015 | FE-015 | Primary included |
| VNX-F-WORK-02 | Projects overview | FE-015 | FE-015 | Primary included |
| VNX-F-WORK-03 | Task lists | FE-015 | FE-015 | Primary included |
| VNX-F-WORK-04 | Live dependency graph | FE-015 | FE-015 | Primary included |
| VNX-F-WORK-05 | Agent relationship graph | FE-016 | FE-016 | Primary included |
| VNX-F-WORK-06 | Evidence-based progress | FE-015 | FE-015 | Primary included |
| VNX-F-WORK-07 | Muse native control | FE-016 | FE-016 | Primary included |
| VNX-F-WORK-08 | ARTEMIS testing surface | FE-018 | FE-017 | REVIEW: primary absent |
| VNX-F-WORK-09 | Review and approval queue | FE-015 | FE-004 | REVIEW: primary absent |
| VNX-F-WORK-10 | Blocker and handoff tracking | FE-016 | FE-016 | Primary included |
| VNX-F-WORK-11 | Activity and execution receipts | FE-015 | FE-015 | Primary included |
| VNX-F-WORK-12 | Workflow accessibility parity | FE-015 | FE-015 | Primary included |
| VNX-F-PRESENCE-01 | Floating VAN service | FE-005 | FE-005 | Primary included |
| VNX-F-PRESENCE-02 | Floating workboard | FE-005 | FE-005 | Primary included |
| VNX-F-PRESENCE-03 | Voice and conversation | FE-021 | FE-017 | REVIEW: primary absent |
| VNX-F-PRESENCE-04 | Floating gestures and recovery | FE-005 | FE-005 | Primary included |
| VNX-F-PRESENCE-05 | Shared orb presence projection | FE-004 | FE-004 | Primary included |
| VNX-F-MEMORY-01 | Memory and record search | FE-019 | FE-019 | Primary included |
| VNX-F-MEMORY-02 | Research and sources | FE-019 | FE-019 | Primary included |
| VNX-F-MEMORY-03 | Memory privacy and erasure | FE-019 | FE-019 | Primary included |
| VNX-F-MEMORY-04 | Learning goals and adaptations | FE-019 | FE-019 | Primary included |
| VNX-F-MORE-01 | Connected services | FE-022 | FE-022 | Primary included |
| VNX-F-MORE-02 | Permissions and device authority | FE-022 | FE-022 | Primary included |
| VNX-F-MORE-03 | Automation and schedules | FE-020 | FE-019 | REVIEW: primary absent |
| VNX-F-MORE-04 | Settings diagnostics appearance | FE-022 | FE-022 | Primary included |

## All 234 contexts

| Context | Purpose / domain | Backend units | Test | Legacy endpoint references |
|---|---|---|---|---|
| VNX-S-HOME-01 | Spatial Home / HOME | BE-030 | T-SURFACE-001 | 0 |
| VNX-S-HOME-02 | Orb Quick Hub / HOME | BE-030 | T-SURFACE-002 | 0 |
| VNX-S-HOME-03 | Attention / HOME | BE-030 | T-SURFACE-003 | 0 |
| VNX-S-HOME-04 | Morning Brief / HOME | BE-030 | T-SURFACE-004 | 0 |
| VNX-S-HOME-05 | Critical Priority Details / HOME | BE-030 | T-SURFACE-005 | 0 |
| VNX-S-HOME-06 | Notification Timeline / HOME | BE-030 | T-SURFACE-006 | 0 |
| VNX-S-HOME-07 | System Presence Details / HOME | BE-030 | T-SURFACE-007 | 0 |
| VNX-S-TRADE-01 | Trading Home / TRADE | BE-032 | T-SURFACE-008 | 0 |
| VNX-S-TRADE-02 | Portfolio Overview / TRADE | BE-032 | T-SURFACE-009 | 0 |
| VNX-S-TRADE-03 | Markets Overview / TRADE | BE-032 | T-SURFACE-010 | 0 |
| VNX-S-TRADE-04 | Markets Category / TRADE | BE-032 | T-SURFACE-011 | 0 |
| VNX-S-TRADE-05 | Market Symbol Search / TRADE | BE-032 | T-SURFACE-012 | 0 |
| VNX-S-TRADE-06 | Watchlists Overview / TRADE | BE-032 | T-SURFACE-013 | 0 |
| VNX-S-TRADE-07 | Watchlist Editor / TRADE | BE-032 | T-SURFACE-014 | 0 |
| VNX-S-TRADE-08 | Opportunities Overview / TRADE | BE-032 | T-SURFACE-015 | 0 |
| VNX-S-TRADE-09 | Charts Library / TRADE | BE-032 | T-SURFACE-016 | 0 |
| VNX-S-TRADE-10 | Intelligence Entry / TRADE | BE-032 | T-SURFACE-017 | 0 |
| VNX-S-TRADE-11 | Accounts Shortcut / TRADE | BE-032 | T-SURFACE-018 | 0 |
| VNX-S-TRADE-12 | Trading Settings / TRADE | BE-032 | T-SURFACE-019 | 0 |
| VNX-S-CHART-01 | Instrument Overview / CHART | BE-008, BE-018 | T-SURFACE-020 | 0 |
| VNX-S-CHART-02 | Professional Terminal / CHART | BE-008, BE-018 | T-SURFACE-021 | 0 |
| VNX-S-CHART-03 | Indicator Picker / CHART | BE-008, BE-018 | T-SURFACE-022 | 0 |
| VNX-S-CHART-04 | Indicator Properties / CHART | BE-008, BE-018 | T-SURFACE-023 | 0 |
| VNX-S-CHART-05 | Drawing Tools / CHART | BE-008, BE-018 | T-SURFACE-024 | 0 |
| VNX-S-CHART-06 | Drawing Object Editor / CHART | BE-008, BE-018 | T-SURFACE-025 | 0 |
| VNX-S-CHART-07 | Chart Settings / CHART | BE-008, BE-018 | T-SURFACE-026 | 0 |
| VNX-S-CHART-08 | Timeframe Picker / CHART | BE-008, BE-018 | T-SURFACE-027 | 0 |
| VNX-S-CHART-09 | Chart Type Picker / CHART | BE-008, BE-018 | T-SURFACE-028 | 0 |
| VNX-S-CHART-10 | Multichart Workspace / CHART | BE-008, BE-018 | T-SURFACE-029 | 0 |
| VNX-S-CHART-11 | Chart Layout Picker / CHART | BE-008, BE-018 | T-SURFACE-030 | 0 |
| VNX-S-CHART-12 | Bar Replay / CHART | BE-008, BE-018, BE-019 | T-SURFACE-031 | 0 |
| VNX-S-CHART-13 | Replay Date Picker / CHART | BE-008, BE-018, BE-019 | T-SURFACE-032 | 0 |
| VNX-S-CHART-14 | Replay Results / CHART | BE-008, BE-018, BE-019 | T-SURFACE-033 | 0 |
| VNX-S-CHART-15 | Market Depth / CHART | BE-008, BE-018 | T-SURFACE-034 | 0 |
| VNX-S-CHART-16 | Chart Alerts / CHART | BE-008, BE-018, BE-020 | T-SURFACE-035 | 0 |
| VNX-S-CHART-17 | Price Crosshair Inspector / CHART | BE-008, BE-018 | T-SURFACE-036 | 0 |
| VNX-S-CHART-18 | Chart Data Provenance / CHART | BE-008, BE-018 | T-SURFACE-037 | 0 |
| VNX-S-CHART-19 | Chart Observation Notes / CHART | BE-008, BE-018, BE-021 | T-SURFACE-038 | 0 |
| VNX-S-CHART-20 | Native Chart Fallback / CHART | BE-008, BE-018 | T-SURFACE-039 | 0 |
| VNX-S-ORDERS-01 | Positions Overview / ORDERS | BE-009, BE-010, BE-011, BE-012 | T-SURFACE-040 | 0 |
| VNX-S-ORDERS-02 | Position Detail / ORDERS | BE-009, BE-010, BE-011, BE-012 | T-SURFACE-041 | 0 |
| VNX-S-ORDERS-03 | Position Bottom Sheet / ORDERS | BE-009, BE-010, BE-011, BE-012 | T-SURFACE-042 | 0 |
| VNX-S-ORDERS-04 | Pending Orders / ORDERS | BE-009, BE-010, BE-011, BE-012 | T-SURFACE-043 | 0 |
| VNX-S-ORDERS-05 | Order Draft / ORDERS | BE-009, BE-010, BE-011, BE-012 | T-SURFACE-044 | 0 |
| VNX-S-ORDERS-06 | Order Risk Review / ORDERS | BE-009, BE-010, BE-011, BE-012 | T-SURFACE-045 | 0 |
| VNX-S-ORDERS-07 | Order A4 Approval / ORDERS | BE-009, BE-010, BE-011, BE-012 | T-SURFACE-046 | 0 |
| VNX-S-ORDERS-08 | Order Receipt / ORDERS | BE-009, BE-010, BE-011, BE-012 | T-SURFACE-047 | 0 |
| VNX-S-ORDERS-09 | Stop Loss Take Profit Edit / ORDERS | BE-009, BE-010, BE-011, BE-012 | T-SURFACE-048 | 0 |
| VNX-S-ORDERS-10 | Partial Close Review / ORDERS | BE-009, BE-010, BE-011, BE-012 | T-SURFACE-049 | 0 |
| VNX-S-ORDERS-11 | Trade History / ORDERS | BE-009, BE-010, BE-011, BE-012 | T-SURFACE-050 | 0 |
| VNX-S-ORDERS-12 | Execution Quality / ORDERS | BE-009, BE-010, BE-011, BE-012 | T-SURFACE-051 | 0 |
| VNX-S-ORDERS-13 | Portfolio Risk / ORDERS | BE-009, BE-010, BE-011, BE-012 | T-SURFACE-052 | 0 |
| VNX-S-ORDERS-14 | Emergency Halt / ORDERS | BE-009, BE-010, BE-011, BE-012 | T-SURFACE-053 | 0 |
| VNX-S-ACCOUNTS-01 | Accounts and Funds Home / ACCOUNTS | BE-004, BE-005 | T-SURFACE-054 | 0 |
| VNX-S-ACCOUNTS-02 | Broker Connection Picker / ACCOUNTS | BE-004, BE-005 | T-SURFACE-055 | 0 |
| VNX-S-ACCOUNTS-03 | Create Demo / ACCOUNTS | BE-004, BE-005 | T-SURFACE-056 | 0 |
| VNX-S-ACCOUNTS-04 | Apply for Live / ACCOUNTS | BE-004, BE-005 | T-SURFACE-057 | 0 |
| VNX-S-ACCOUNTS-05 | Link Existing / ACCOUNTS | BE-004, BE-005 | T-SURFACE-058 | 0 |
| VNX-S-ACCOUNTS-06 | Account Detail / ACCOUNTS | BE-004, BE-005, BE-012 | T-SURFACE-059 | 0 |
| VNX-S-ACCOUNTS-07 | Edit Local Account / ACCOUNTS | BE-004, BE-005 | T-SURFACE-060 | 0 |
| VNX-S-ACCOUNTS-08 | Broker Profile Edit / ACCOUNTS | BE-004, BE-005 | T-SURFACE-061 | 0 |
| VNX-S-ACCOUNTS-09 | Credentials and Security / ACCOUNTS | BE-004, BE-005 | T-SURFACE-062 | 0 |
| VNX-S-ACCOUNTS-10 | Account Verification / ACCOUNTS | BE-004, BE-005 | T-SURFACE-063 | 0 |
| VNX-S-ACCOUNTS-11 | Unlink Review / ACCOUNTS | BE-004, BE-005 | T-SURFACE-064 | 0 |
| VNX-S-ACCOUNTS-12 | Broker Closure Review / ACCOUNTS | BE-004, BE-005 | T-SURFACE-065 | 0 |
| VNX-S-ACCOUNTS-13 | Deposit Form / ACCOUNTS | BE-004, BE-005, BE-006, BE-007 | T-SURFACE-066 | 0 |
| VNX-S-ACCOUNTS-14 | Deposit Provider Handoff / ACCOUNTS | BE-004, BE-005, BE-006, BE-007 | T-SURFACE-067 | 0 |
| VNX-S-ACCOUNTS-15 | Withdrawal Form / ACCOUNTS | BE-004, BE-005, BE-006, BE-007 | T-SURFACE-068 | 0 |
| VNX-S-ACCOUNTS-16 | Beneficiary Verify / ACCOUNTS | BE-004, BE-005, BE-006, BE-007 | T-SURFACE-069 | 0 |
| VNX-S-ACCOUNTS-17 | Transfer Review / ACCOUNTS | BE-004, BE-005, BE-006, BE-007 | T-SURFACE-070 | 0 |
| VNX-S-ACCOUNTS-18 | Transactions and Receipts / ACCOUNTS | BE-004, BE-005, BE-006, BE-007 | T-SURFACE-071 | 0 |
| VNX-S-INTEL-01 | Intelligence Home / INTEL | BE-014, BE-015, BE-016, BE-021 | T-SURFACE-072 | 0 |
| VNX-S-INTEL-02 | News Feed / INTEL | BE-014, BE-015, BE-016, BE-021 | T-SURFACE-073 | 0 |
| VNX-S-INTEL-03 | Article Full Analysis / INTEL | BE-014, BE-015, BE-016, BE-021 | T-SURFACE-074 | 0 |
| VNX-S-INTEL-04 | Economic Calendar / INTEL | BE-014, BE-015, BE-016, BE-021 | T-SURFACE-075 | 0 |
| VNX-S-INTEL-05 | Economic Event Detail / INTEL | BE-014, BE-015, BE-016, BE-021 | T-SURFACE-076 | 0 |
| VNX-S-INTEL-06 | Instrument Impact / INTEL | BE-014, BE-015, BE-016, BE-021 | T-SURFACE-077 | 0 |
| VNX-S-INTEL-07 | Position News Exposure / INTEL | BE-014, BE-015, BE-016, BE-021 | T-SURFACE-078 | 0 |
| VNX-S-INTEL-08 | Analysis Source Evidence / INTEL | BE-014, BE-015, BE-016, BE-021 | T-SURFACE-079 | 0 |
| VNX-S-INTEL-09 | Contradictions and Retractions / INTEL | BE-014, BE-015, BE-016, BE-021 | T-SURFACE-080 | 0 |
| VNX-S-INTEL-10 | Strategy Intelligence / INTEL | BE-014, BE-015, BE-016, BE-021 | T-SURFACE-081 | 0 |
| VNX-S-INTEL-11 | VAN Analyst Conversation / INTEL | BE-014, BE-015, BE-016, BE-021 | T-SURFACE-082 | 0 |
| VNX-S-INTEL-12 | Opportunity Reasons / INTEL | BE-014, BE-015, BE-016, BE-021 | T-SURFACE-083 | 0 |
| VNX-S-INTEL-13 | Model Disagreement / INTEL | BE-014, BE-015, BE-016, BE-021 | T-SURFACE-084 | 0 |
| VNX-S-INTEL-14 | Research History / INTEL | BE-014, BE-015, BE-016, BE-021 | T-SURFACE-085 | 0 |
| VNX-S-WORK-01 | Work Home / WORK | BE-023 | T-SURFACE-086 | 0 |
| VNX-S-WORK-02 | Projects Overview / WORK | BE-023 | T-SURFACE-087 | 0 |
| VNX-S-WORK-03 | Project Detail / WORK | BE-023 | T-SURFACE-088 | 0 |
| VNX-S-WORK-04 | Task Lists / WORK | BE-023 | T-SURFACE-089 | 0 |
| VNX-S-WORK-05 | Task Detail / WORK | BE-023 | T-SURFACE-090 | 0 |
| VNX-S-WORK-06 | Dependency Flow Graph / WORK | BE-023 | T-SURFACE-091 | 0 |
| VNX-S-WORK-07 | Agent Collaboration Graph / WORK | BE-023, BE-024 | T-SURFACE-092 | 0 |
| VNX-S-WORK-08 | Handoff Inspector / WORK | BE-023, BE-024 | T-SURFACE-093 | 0 |
| VNX-S-WORK-09 | Progress Evidence / WORK | BE-023 | T-SURFACE-094 | 0 |
| VNX-S-WORK-10 | Active Missions / WORK | BE-023 | T-SURFACE-095 | 0 |
| VNX-S-WORK-11 | Muse Workspace / WORK | BE-023, BE-024 | T-SURFACE-096 | 0 |
| VNX-S-WORK-12 | Muse Intervention / WORK | BE-023, BE-024 | T-SURFACE-097 | 0 |
| VNX-S-WORK-13 | ARTEMIS Lab / WORK | BE-023, BE-026 | T-SURFACE-098 | 0 |
| VNX-S-WORK-14 | Review Queue / WORK | BE-002, BE-023, BE-030 | T-SURFACE-099 | 0 |
| VNX-S-WORK-15 | Approval Detail / WORK | BE-002, BE-023, BE-030 | T-SURFACE-100 | 0 |
| VNX-S-WORK-16 | Activity Timeline / WORK | BE-023 | T-SURFACE-101 | 0 |
| VNX-S-PRESENCE-01 | Floating VAN / PRESENCE | BE-029, BE-030, BE-031 | T-SURFACE-102 | 0 |
| VNX-S-PRESENCE-02 | Floating Compact Workboard / PRESENCE | BE-029, BE-030, BE-031 | T-SURFACE-103 | 0 |
| VNX-S-PRESENCE-03 | Floating Expanded Workboard / PRESENCE | BE-029, BE-030, BE-031 | T-SURFACE-104 | 0 |
| VNX-S-PRESENCE-04 | Floating Quick Controls / PRESENCE | BE-029, BE-030, BE-031 | T-SURFACE-105 | 0 |
| VNX-S-PRESENCE-05 | Voice Conversation / PRESENCE | BE-029, BE-030, BE-031 | T-SURFACE-106 | 0 |
| VNX-S-PRESENCE-06 | Floating Recovery / PRESENCE | BE-029, BE-030, BE-031 | T-SURFACE-107 | 0 |
| VNX-S-MEMORY-01 | Memory Overview / MEMORY | BE-027 | T-SURFACE-108 | 0 |
| VNX-S-MEMORY-02 | Memory Record Detail / MEMORY | BE-027 | T-SURFACE-109 | 0 |
| VNX-S-MEMORY-03 | Research Library / MEMORY | BE-027 | T-SURFACE-110 | 0 |
| VNX-S-MEMORY-04 | Memory Privacy / MEMORY | BE-027 | T-SURFACE-111 | 0 |
| VNX-S-MORE-01 | More Home / MORE | BE-031 | T-SURFACE-112 | 0 |
| VNX-S-MORE-02 | Connected Services / MORE | BE-031 | T-SURFACE-113 | 0 |
| VNX-S-MORE-03 | Permissions and Devices / MORE | BE-031 | T-SURFACE-114 | 0 |
| VNX-S-MORE-04 | Settings Diagnostics Appearance / MORE | BE-031 | T-SURFACE-115 | 0 |
| van.home | Home / HOME | BE-030, BE-032 | T-SURFACE-116 | 7 |
| van.attention | Attention / HOME | BE-002, BE-030 | T-SURFACE-117 | 7 |
| van.work | Work / WORK | BE-023, BE-024 | T-SURFACE-118 | 9 |
| van.work.mission | Mission deep link / WORK | BE-023, BE-024 | T-SURFACE-119 | 8 |
| van.work.activity | Activity / WORK | BE-023, BE-024 | T-SURFACE-120 | 1 |
| van.work.artemis | ARTEMIS Android Lab / WORK | BE-026 | T-SURFACE-121 | 1 |
| van.work.dev.home | Development Hub / WORK | BE-023, BE-024 | T-SURFACE-122 | 3 |
| van.work.dev.plan | Stage Plan / WORK | BE-023, BE-024 | T-SURFACE-123 | 2 |
| van.work.dev.tasks | Development Tasks / WORK | BE-023, BE-024 | T-SURFACE-124 | 2 |
| van.work.dev.graph | Task Graph / WORK | BE-023, BE-024 | T-SURFACE-125 | 2 |
| van.work.dev.task | Task Detail / WORK | BE-023, BE-024 | T-SURFACE-126 | 3 |
| van.work.dev.agents | Agents / WORK | BE-024 | T-SURFACE-127 | 2 |
| van.work.dev.workspaces | Workspaces / WORK | BE-023, BE-024, BE-034 | T-SURFACE-128 | 2 |
| van.work.dev.workspace | Workspace Detail / WORK | BE-023, BE-024, BE-034 | T-SURFACE-129 | 5 |
| van.work.dev.evidence | Evidence / WORK | BE-023, BE-024 | T-SURFACE-130 | 2 |
| van.work.dev.reviews | Development Reviews / WORK | BE-023, BE-024 | T-SURFACE-131 | 2 |
| van.work.dev.memory | Development Memory / MEMORY | BE-027 | T-SURFACE-132 | 2 |
| van.work.dev.research | Development Research / WORK | BE-023, BE-024, BE-034 | T-SURFACE-133 | 2 |
| van.work.dev.design | Development Design / WORK | BE-023, BE-024, BE-034 | T-SURFACE-134 | 2 |
| van.work.dev.ci | Development Ci / WORK | BE-023, BE-024, BE-034 | T-SURFACE-135 | 2 |
| van.work.dev.security | Development Security / WORK | BE-023, BE-024, BE-034 | T-SURFACE-136 | 2 |
| van.work.browser | Browser & Automation / WORK | BE-025 | T-SURFACE-137 | 4 |
| van.work.browser.tasks | Browser Tasks / WORK | BE-025 | T-SURFACE-138 | 2 |
| van.work.browser.escalations | Browser Escalations / WORK | BE-025 | T-SURFACE-139 | 3 |
| van.work.browser.sessions | Browser Sessions / WORK | BE-025 | T-SURFACE-140 | 1 |
| van.work.browser.policy | Browser Policy / WORK | BE-025 | T-SURFACE-141 | 1 |
| van.browser.interactive | Remote Browser / WORK | BE-025 | T-SURFACE-142 | 30 |
| van.browser.downloads | Downloads, uploads and content policy / WORK | BE-025 | T-SURFACE-143 | 13 |
| van.browser.outcome | Browser task outcome evidence / WORK | BE-025 | T-SURFACE-144 | 1 |
| van.browser.action-plan | Immutable browser effect review and observation / WORK | BE-025 | T-SURFACE-145 | 5 |
| van.browser.file-provider | Exact owner file destination, admission and result / WORK | BE-025 | T-SURFACE-146 | 9 |
| van.trading | Trading / ORDERS | BE-009, BE-010, BE-011, BE-012 | T-SURFACE-147 | 0 |
| van.trading.overview | Overview / ORDERS | BE-009, BE-010, BE-011, BE-012 | T-SURFACE-148 | 5 |
| van.trading.positions | Positions / ORDERS | BE-009, BE-010, BE-011, BE-012 | T-SURFACE-149 | 1 |
| van.trading.positions.detail | Position Detail / ORDERS | BE-009, BE-010, BE-011, BE-012 | T-SURFACE-150 | 4 |
| van.trading.potential | Potential / INTEL | BE-013, BE-015, BE-021 | T-SURFACE-151 | 1 |
| van.trading.history | History & Intelligence / ORDERS | BE-006, BE-012, BE-022 | T-SURFACE-152 | 1 |
| van.trading.accounts | Accounts / ACCOUNTS | BE-004, BE-005, BE-006, BE-007 | T-SURFACE-153 | 1 |
| van.trading.cognition | Cognition / INTEL | BE-013, BE-015, BE-021 | T-SURFACE-154 | 1 |
| van.trading.accounts.add | Add Trading Account / ACCOUNTS | BE-004, BE-005, BE-006, BE-007 | T-SURFACE-155 | 2 |
| van.trading.strategies | Strategies / INTEL | BE-013 | T-SURFACE-156 | 3 |
| van.trading.halt | Halt Trading / ORDERS | BE-009, BE-010, BE-011, BE-012 | T-SURFACE-157 | 3 |
| van.trading.tickets | Trading tickets and broker receipts / ORDERS | BE-009, BE-010, BE-011, BE-012 | T-SURFACE-158 | 2 |
| van.approval.trading-ticket | Exact broker-fill receipt confirmation / ORDERS | BE-009, BE-010, BE-011, BE-012 | T-SURFACE-159 | 2 |
| van.memory | Memory / MEMORY | BE-027 | T-SURFACE-160 | 6 |
| van.memory.history | Fact History / MEMORY | BE-027 | T-SURFACE-161 | 1 |
| van.learning.adaptations | Adaptation review and rollback / MEMORY | BE-027 | T-SURFACE-162 | 3 |
| van.learning.goals | Goals, unresolved threads and learned strategies / MEMORY | BE-027 | T-SURFACE-163 | 7 |
| van.memory.privacy | Memory privacy and retention / MEMORY | BE-027 | T-SURFACE-164 | 8 |
| van.attention.decision | Exact owner choice and evidence / HOME | BE-002, BE-030 | T-SURFACE-165 | 2 |
| van.work.mission-control | Mission dispatch fence and direction receipt / WORK | BE-023, BE-024 | T-SURFACE-166 | 5 |
| van.memory.record | Exact retained record and erasure scope / MEMORY | BE-027 | T-SURFACE-167 | 5 |
| van.permissions.grant | Exact bounded owner consent / MORE | BE-002, BE-031 | T-SURFACE-168 | 4 |
| van.automation.plan | Automation candidate, admission and exact run evidence / MORE | BE-028 | T-SURFACE-169 | 7 |
| van.settings.speaker-profile | Local owner speaker consent, capture and erasure / PRESENCE | BE-029 | T-SURFACE-170 | 0 |
| van.projects | Projects / WORK | BE-023, BE-024 | T-SURFACE-171 | 5 |
| van.projects.detail | Project Detail / WORK | BE-023, BE-024 | T-SURFACE-172 | 7 |
| van.projects.rationale | Project rationale and decision provenance / WORK | BE-023, BE-024 | T-SURFACE-173 | 2 |
| van.connected | Connected / MORE | BE-002, BE-031 | T-SURFACE-174 | 5 |
| van.settings | Settings & Devices / MORE | BE-002, BE-031 | T-SURFACE-175 | 2 |
| van.diagnostics | Connection health and command correlation / MORE | BE-002, BE-031 | T-SURFACE-176 | 6 |
| van.onboarding | Device Onboarding / MORE | BE-002, BE-031 | T-SURFACE-177 | 0 |
| van.provisioning | Signed Provisioning Intake / MORE | BE-002, BE-031 | T-SURFACE-178 | 6 |
| van.settings.voice | Voice Settings / PRESENCE | BE-029 | T-SURFACE-179 | 0 |
| van.voice.turn | Voice Turn / PRESENCE | BE-029 | T-SURFACE-180 | 3 |
| van.settings.notifications | Notification Policy / MORE | BE-002, BE-031 | T-SURFACE-181 | 0 |
| van.floating | Floating VAN / PRESENCE | BE-029, BE-030, BE-031 | T-SURFACE-182 | 2 |
| van.permissions | Standing Permissions / MORE | BE-002, BE-031 | T-SURFACE-183 | 8 |
| van.autonomy | Autonomy / MORE | BE-002, BE-031 | T-SURFACE-184 | 4 |
| van.understanding | Understanding & Adaptation / MEMORY | BE-027 | T-SURFACE-185 | 10 |
| van.reminders.manage | Reminder Management / MORE | BE-028 | T-SURFACE-186 | 4 |
| van.approval.detail | Exact-action approval and refusal / HOME | BE-002, BE-030 | T-SURFACE-187 | 3 |
| van.knowledge.research | Research, private knowledge and evidence / MEMORY | BE-027 | T-SURFACE-188 | 12 |
| van.knowledge.sources | Private knowledge providers and citations / MEMORY | BE-027 | T-SURFACE-189 | 2 |
| van.automation.library | Automation inventory and admission / MORE | BE-028 | T-SURFACE-190 | 14 |
| van.automation.intent | Standing authority and workflow detail / MORE | BE-028 | T-SURFACE-191 | 8 |
| van.devices.provision | Signed provisioning and recovery / MORE | BE-002, BE-031 | T-SURFACE-192 | 9 |
| van.share.intake | Shared Context Intake / MORE | BE-025, BE-027 | T-SURFACE-193 | 1 |
| van.next.orb-hub | Home orb quick hub / HOME | BE-030, BE-032 | T-SURFACE-194 | 0 |
| van.next.trading.chart | Instrument chart terminal / CHART | BE-008, BE-018 | T-SURFACE-195 | 0 |
| van.next.trading.manual-review | Manual trade review & approval sheet / ORDERS | BE-009, BE-010, BE-011 | T-SURFACE-196 | 0 |
| van.next.trading.exit-sheet | Position exit / protection sheet / ORDERS | BE-009, BE-010, BE-011 | T-SURFACE-197 | 0 |
| van.next.trading.add-sheet | Add to position sheet (manual or automatic trade) / ORDERS | BE-009, BE-010, BE-011 | T-SURFACE-198 | 0 |
| van.next.trading.handover-sheet | Hand to VAN / take back sheet / ORDERS | BE-011 | T-SURFACE-199 | 0 |
| van.next.trading.markets | Markets & watchlists / TRADE | BE-008, BE-020 | T-SURFACE-200 | 0 |
| van.next.intel.news | News briefs / INTEL | BE-014, BE-015, BE-016, BE-021 | T-SURFACE-201 | 0 |
| van.next.intel.news-story | News story brief & trading effect / INTEL | BE-014, BE-015, BE-016, BE-021 | T-SURFACE-202 | 0 |
| van.next.intel.calendar | Economic calendar with event history / INTEL | BE-016 | T-SURFACE-203 | 0 |
| van.next.intel.event-history | Similar past events for a story / INTEL | BE-016 | T-SURFACE-204 | 0 |
| van.next.intel.news-coverage | News source coverage and health / INTEL | BE-014, BE-015, BE-016, BE-021 | T-SURFACE-205 | 0 |
| van.next.intel.news-live | News Live (live headlines, armed releases, latency) / INTEL | BE-017 | T-SURFACE-206 | 0 |
| van.next.trading.armed-ticket | Armed news ticket (pre-signed, one tap at release) / INTEL | BE-017 | T-SURFACE-207 | 0 |
| van.next.trading.behaviour | Manual trading habits and behaviour flags / INTEL | BE-022 | T-SURFACE-208 | 0 |
| van.next.trading.pattern-candidates | Patterns from your trades (candidate strategies) / INTEL | BE-022 | T-SURFACE-209 | 0 |
| van.next.intel.keyword-watchlists | News keyword watchlists / INTEL | BE-015 | T-SURFACE-210 | 0 |
| van.next.trading.replay | Chart replay sandbox / CHART | BE-019 | T-SURFACE-211 | 0 |
| van.next.trading.alerts | Alerts (price, indicator, drawing, keyword) / TRADE | BE-020 | T-SURFACE-212 | 0 |
| van.next.trading.screener | Screener / TRADE | BE-020 | T-SURFACE-213 | 0 |
| van.next.trading.chart-tools | Indicators, drawings and workspaces sheets / CHART | BE-018 | T-SURFACE-214 | 0 |
| van.next.work.flow | Project task flow graph / WORK | BE-023 | T-SURFACE-215 | 0 |
| van.next.work.agent-map | Agent handoff map / WORK | BE-024 | T-SURFACE-216 | 0 |
| VAN-S-CX-STRATEGY-DEVELOPMENT | Strategy development overview / TRADING_INTELLIGENCE | BE-036 | T-SURFACE-CX-001 | 0 |
| VAN-S-CX-CANDIDATE-COMPARISON | Candidate versus champion / TRADING_INTELLIGENCE | BE-013, BE-035, BE-036 | T-SURFACE-CX-002 | 0 |
| VAN-S-CX-EXPERIMENT-LEDGER | Complete trial and failed-candidate ledger / TRADING_INTELLIGENCE | BE-035, BE-036 | T-SURFACE-CX-003 | 0 |
| VAN-S-CX-LOCKOUT-SCOPES | Strategy/manual/autonomous lockout detail / TRADING_INTELLIGENCE | BE-009, BE-013 | T-SURFACE-CX-004 | 0 |
| VAN-S-CX-ORDER-RECONCILIATION | Pending-order policy and reconciliation detail / TRADING_INTELLIGENCE | BE-010, BE-012 | T-SURFACE-CX-005 | 0 |
| VAN-S-CX-MODEL-REGISTRY | Qualified model and forecast registry / TRADING_INTELLIGENCE | VAN-ML-PKT-022, VAN-ML-PKT-024 | T-SURFACE-CX-006 | 0 |
| VAN-S-CX-CALIBRATION | Forecast calibration and uncertainty / TRADING_INTELLIGENCE | VAN-ML-PKT-020, VAN-ML-PKT-041 | T-SURFACE-CX-007 | 0 |
| VAN-S-CX-EVENT-EXPECTATIONS | Prediction-market expectations / TRADING_INTELLIGENCE | VAN-ML-PKT-040, VAN-ML-PKT-041 | T-SURFACE-CX-008 | 0 |
| VAN-S-CX-EVENT-RESEARCH-LABS | Prediction-contract replay and research labs / TRADING_INTELLIGENCE | VAN-ML-PKT-044, VAN-ML-PKT-045, VAN-ML-PKT-046 | T-SURFACE-CX-009 | 0 |
| VAN-S-CX-SOURCE-ADMISSION | Data/feed quality and admission detail / TRADING_INTELLIGENCE | BE-014, VAN-ML-PKT-006, VAN-ML-PKT-037 | T-SURFACE-CX-010 | 0 |
| VAN-S-CX-EVALUATOR-STATUS | Evaluator qualification and result invalidation / TRADING_INTELLIGENCE | BE-035 | T-SURFACE-CX-011 | 0 |
| VAN-S-CX-RISK-POLICY-ACTIVATION | Signed risk-policy activation review / TRADING_INTELLIGENCE | BE-002, BE-009, BE-013 | T-SURFACE-CX-012 | 0 |
| CTX-HVA-DISCOVERY | Candidate discovery and rejection funnel / Trading / Intelligence / Research — existing contextual navigation | BE-038, BE-044 | T-CTX-HVA-DISCOVERY | 0 |
| CTX-HVA-SECURITY | Chain security and capability findings / Trading / Intelligence / Research — existing contextual navigation | BE-039, BE-040, BE-043 | T-CTX-HVA-SECURITY | 0 |
| CTX-HVA-WALLET | Temporal wallet and concentration evidence / Trading / Intelligence / Research — existing contextual navigation | BE-042, BE-043 | T-CTX-HVA-WALLET | 0 |
| CTX-HVA-SELLABILITY | State-bound route and executable economics / Trading / Intelligence / Research — existing contextual navigation | BE-041, BE-043 | T-CTX-HVA-SELLABILITY | 0 |
| CTX-HVA-COHORT | Whole-policy experiment and missing-outcome review / Trading / Intelligence / Research — existing contextual navigation | BE-044, VAN-ML-PKT-010, VAN-ML-PKT-027 | T-CTX-HVA-COHORT | 0 |
| CTX-HVA-JUDGMENT | Typed judgment provenance and contribution / Trading / Intelligence / Research — existing contextual navigation | BE-021, BE-044 | T-CTX-HVA-JUDGMENT | 0 |

## All 82 backend capability boundaries

| Unit | Purpose | Package status |
|---|---|---|
| BE-001 | Source consolidation and preservation oracle | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| BE-002 | Device identity, bounded authority and intent fencing | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| BE-003 | Durable event, readback and projection infrastructure | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| BE-004 | Accounts, broker/exchange directory and operation capabilities | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| BE-005 | Broker authentication, credential rotation and health | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| BE-006 | Exact funding ledger and flow-adjusted accounting | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| BE-007 | Deposits, withdrawals, transfers and provider rails | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| BE-008 | Instrument identity, conventional/crypto market feeds, bars and depth | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| BE-009 | Mandates, risk, sizing and portfolio reservations | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| BE-010 | Venue execution, parent/child orders, crypto spot adapters and reconciliation | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| BE-011 | Manual trading, adds and management handover | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| BE-012 | Positions, protection, portfolio, history and TCA | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| BE-013 | Strategy registry, signed trading modes and qualified edge-consumer contracts | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| BE-014 | News, calendar and source-health ingestion | PRESERVED_OR_EXTENSION_CANDIDATE_NOT_NEWLY_QUALIFIED |
| BE-015 | Event analysis, history, analogues and expectations | PRESERVED_OR_EXTENSION_CANDIDATE_NOT_NEWLY_QUALIFIED |
| BE-016 | Governed news effects D1–D7 and news strategy lifecycle | PRESERVED_OR_EXTENSION_CANDIDATE_NOT_NEWLY_QUALIFIED |
| BE-017 | Armed news tickets, readiness and single-use execution | PRESERVED_OR_EXTENSION_CANDIDATE_NOT_NEWLY_QUALIFIED |
| BE-018 | Chart data contracts, indicators, drawings and workspaces | PRESERVED_OR_EXTENSION_CANDIDATE_NOT_NEWLY_QUALIFIED |
| BE-019 | Historical replay, simulation and isolated practice data | PRESERVED_OR_EXTENSION_CANDIDATE_NOT_NEWLY_QUALIFIED |
| BE-020 | Watchlists, persistent alerts and typed screening | PRESERVED_OR_EXTENSION_CANDIDATE_NOT_NEWLY_QUALIFIED |
| BE-021 | Analyst, chart observations and cross-signal intelligence | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| BE-022 | Owner diagnostics, pattern discovery and learning review | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| BE-023 | Projects, tasks, missions and truthful workflow graphs | PRESERVED_OR_EXTENSION_CANDIDATE_NOT_NEWLY_QUALIFIED |
| BE-024 | Agents, Hermes, Muse and provider-bound interventions | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| BE-025 | Browser, remote interaction, artifact and share intake | PRESERVED_OR_EXTENSION_CANDIDATE_NOT_NEWLY_QUALIFIED |
| BE-026 | ARTEMIS device tests and independent evidence services | PRESERVED_OR_EXTENSION_CANDIDATE_NOT_NEWLY_QUALIFIED |
| BE-027 | Memory, knowledge, goals, privacy and erasure | PRESERVED_OR_EXTENSION_CANDIDATE_NOT_NEWLY_QUALIFIED |
| BE-028 | Automation, reminders and schedules | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| BE-029 | Conversation, voice and speaker-profile services | PRESERVED_OR_EXTENSION_CANDIDATE_NOT_NEWLY_QUALIFIED |
| BE-030 | Attention, notifications, presence and compact summaries | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| BE-031 | Connected providers, settings, devices and diagnostics | PRESERVED_OR_EXTENSION_CANDIDATE_NOT_NEWLY_QUALIFIED |
| BE-032 | Whole-product capability, action and UI-consumption catalog | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| BE-033 | Backend deployment, recovery, capacity and observability | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| BE-034 | Development studio, CI/security and evidence-workspace adapters | PRESERVED_OR_EXTENSION_CANDIDATE_NOT_NEWLY_QUALIFIED |
| BE-035 | Qualified chronological strategy evaluator and simulator oracle | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| BE-036 | Continuous governed strategy and execution-policy development; operational learning integration | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| VAN-ML-PKT-004 | Pinned dependencies and isolated research runtime | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-005 | Point-in-time market dataset and universe snapshots | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-006 | Shared feature definitions and Feast parity | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-007 | Targets, executable labels and outcome provenance | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-008 | Chronological folds, lookahead and warmup diagnostics | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| VAN-ML-PKT-009 | Simulation accounting, intrabar and timing corrections | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-010 | Account-wide replay and execution-policy parity | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| VAN-ML-PKT-011 | Qlib data, processor and recorder integration | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-012 | LightGBM expected-return and net-edge regressors | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-013 | LightGBM setup-event classification | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-014 | LightGBM quantile and grouped ranking adapters | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-015 | Challenger and simple baseline suite | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-016 | NeuralForecast bridge and N-HiTS | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-017 | N-BEATSx contextual forecasts and decomposition | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-018 | DeepAR distributional forecasts and retained scenarios | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-019 | Contextual and multivariate neural challengers | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-020 | One calibration and uncertainty-validation boundary | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-021 | Unified Optuna and rolling research studies | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-022 | Safe model artifacts and candidate registry | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-023 | Adaptive retraining scheduler and lifecycle | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-024 | Forecast serving, cache, freshness and novelty gates | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-025 | Forecast fusion, arbiter and mode evidence integration | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| VAN-ML-PKT-026 | Instrument and strategy protection policies | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-027 | Outcome ledger, drift and proprietary learning data | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-028 | Complete backend APIs and future-screen consumption | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-029 | VM deployment, isolation, recovery and service operations | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-037 | Prediction-market scope, VM profiles and source capability contracts | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-038 | Kalshi and comparison-provider ingestion, depth and history | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-039 | Event semantics, settlement and cross-venue equivalence | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-040 | Coherent event distributions, quality and probability features | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-041 | Event calibration, grouped chronology and frozen surprise | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-042 | Conditional asset-response models and forecast-stack integration | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-043 | Calibrated event value and bounded position evidence | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-044 | Execution-realistic prediction-contract replay | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-045 | Contract-consistency and non-atomic arbitrage research laboratory | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-046 | Inventory-aware event market-making research laboratory | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-047 | Prediction-market incremental-value and prospective study programme | SPECIFIED_NOT_IMPLEMENTED |
| VAN-ML-PKT-048 | Prediction-market consumers, operations and complete backend integration | SPECIFIED_NOT_IMPLEMENTED |
| BE-037 | Chain-aware identity and permitted read-only discovery adapters | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| BE-038 | Complete discovery cohorts and staged deterministic screening | SPECIFIED_NOT_IMPLEMENTED |
| BE-039 | Solana token capability and uncertainty analyzer | SPECIFIED_NOT_IMPLEMENTED |
| BE-040 | EVM contract/proxy capability and uncertainty analyzer | SPECIFIED_NOT_IMPLEMENTED |
| BE-041 | State-bound buy/sell simulations and executable quote facts | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| BE-042 | Temporal wallet attribution and holder-flow intelligence | SPECIFIED_NOT_IMPLEMENTED |
| BE-043 | Finality, reorganization and descendant revalidation | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
| BE-044 | Read-only crypto end-to-end research, operations and native consumption contract | REQUIRED_EXTENSION_NOT_IMPLEMENTED_BY_THIS_PACK |
