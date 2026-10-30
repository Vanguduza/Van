# BE-025: Chromium page readiness in source qualification

The fresh hosted run at source `df249c52e30cd5f188a77a12ebff7efaa3244266` reproduced a setup race: Chromium had written `DevToolsActivePort`, but `Target.getTargets` did not yet contain the command-line page. The test kit immediately called `next(...)`, raised `StopIteration`, and never executed that security scenario. The browser job correctly failed; its later full-suite, listener-UID and namespace checks did not execute.

The kit now observes the original page within one ten-second deadline. Each CDP request uses the remaining time. A page received after the deadline is refused; no replacement page is created. CDP errors propagate. Failed construction closes its websocket because normal fixture teardown cannot own a session whose constructor failed.

Five deterministic CDP-response checks reproduce this without Chromium. Before the repair, four fail and the already-ready positive control passes. After the repair, all five pass. These are test-instrument checks, not live browser evidence. The original lease-guard scenario file is byte-identical to the published source, including every security assertion. No skip, expected count, network scope, lease protection or application implementation is weakened.

Fresh Chromium execution of the unchanged scenarios and the complete browser, listener-UID and privileged namespace suites is still required at the repaired source. Local Chromium is absent. The previous hosted run is retained as a failure in `receipts/HOSTED_SOURCE_df249c52.json`; passing source groups from that run do not erase the browser failure.

This packet does not issue BE-025 acceptance, F15, BG-001, a deployment, a production release or S24 acceptance. The frozen Rev1.18 package and programme are unchanged. Continue the backend programme, including BE-020 market monitors, after publishing this repair.
