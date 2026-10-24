# Private-core shared storage import boundary

The full815405e9 backend run completed with7202 passes,9 skips and2 failures. Chart-table retention was already corrected by a8374cc4. The other failure showed that shared storage imported `van_gateway.trading.chart_schema`; the trading package initializer then loaded its service into the private-core process. This violated the existing owner-defined import boundary.

The data-only chart migration now belongs to `van_gateway.storage.chart_migration`. Its SQL is byte-identical. Shared storage imports that module directly, and the old chart schema path reexports the constant for existing chart callers. No forbidden-prefix check is relaxed and no trading implementation is deleted. A fresh private-core import excludes the trading modules; restoring the old import is detected by the unchanged contract test.

The focused pass also exposed historical migration fixtures calling the modern mission producer on intentionally old45/46 databases. A test-only pre57 producer retains native mission/event creation while omitting the learning queue that did not exist in that era. Only the historical fixture helpers use it; current-runtime origin-rule tests and all original cognitive-model assertions remain. Production still requires its migrated schema and has no missing-table fallback.

Evidence: `../receipts/PRIVATE_STORAGE_IMPORT_BOUNDARY_SOURCE_20261024.json`. This source check does not qualify actual private-core host placement, networking, custody, migration of production data, whole-unit completion or F15/BG/device acceptance. The earlier failed full run is retained, and a fresh exact-source broad regression is required.
