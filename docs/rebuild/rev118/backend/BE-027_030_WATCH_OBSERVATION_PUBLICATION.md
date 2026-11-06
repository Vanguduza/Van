# Owner watch observation and alert integrity

Existing owner-authored watches remain read-only monitors. Their observations cannot dispatch an agent, trade, browser mutation or broader automation. This packet changes the existing goal/watch service, attention engine and scheduled watch job; it adds no new interface design or host configuration.

A watch's active-state check, edge detection or failure count, observation history, current projection and immutable notification intent now commit in one SQLite write transaction. Invalid boolean, text, non-finite numeric or non-JSON observations are refused before a commit. A failed history/notification-intent insert rolls back the projection. Concurrent checks retain both failure counts and create only one alert for a single boolean edge. An owner pause that races an observation remains authoritative.

After observation acceptance, an alert delivery failure leaves an original pending publication. It does not turn that accepted observation into another failed check. The standing `owner.watches` scheduler retries persisted publications even when no browser watch is due. Stable dedupe identities recover both failures before persistence and lost replies after persistence. A server receipt confirms attention persistence, not handset delivery or owner acknowledgement. The observation endpoint now advertises a typed result with `NOT_REQUIRED`, `PENDING` or `PUBLISHED` notification state.

Failure notifications use a durable per-watch sequence. A delayed first failure cannot downgrade a newer paused/blocker report. The sequence survives retention of individual run history; it does not use a recyclable SQLite rowid. Replays preserve an owner's acknowledgement. Each intent retains its original project's scope. One unavailable publication does not starve another watch's publication.

An owner pausing a watch during its browser read discards the observation, terminates its browser task and lets other watches continue. The existing deterministic public-page path, lease fencing, network-effect guards and authority boundaries remain in force.

Evidence is recorded in `receipts/WATCH_OBSERVATION_PUBLICATION_SOURCE_20261023.json`: reproduced failures, real persisted-state checks, independent SQLite interleavings, lost-reply/restart recovery, the paired gateway/scheduler, actual Chromium network guards and eight deliberately broken source variants. Earlier failed instrumentation/test attempts are retained separately. The receipt also links the successful frozen `2e93ab52` broad run; that run does not qualify this later source.

This is candidate source evidence for BE-027/030, with BE-003 durability dependencies. It does not complete those units, implement provider feeds or a new Android consumer, establish device delivery, or issue native, release or physical S24 acceptance. Owner-goal CRUD and all other canonical programme obligations remain in scope.
