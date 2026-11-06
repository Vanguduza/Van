# BE-014: calendar file identity, shape and exact declared time

Status: source-tested component; the news, calendar and source-health unit remains in progress.

The file adapter now accepts the documented JSON array as well as an events envelope. Missing or malformed arrays refuse loading instead of becoming empty coverage. Schedule and observation rows preserve an explicit original event key; distinct same-name releases can retain their separate currency scopes. Reuse of one key with conflicting name, time or currency scope is rejected. Rows without an explicit key retain their original legacy identity.

Both calendar parsers use exact integer UTC milliseconds and require an explicit timezone offset. They preserve legacy epoch units and historical dates before 1970. Precision finer than milliseconds is rejected, including original fractional digits that Python would truncate before parsing. Trailing zero precision remains valid. No timestamp is rounded down into an earlier availability cutoff.

The report preserves declared source counts and blackout behavior while distinguishing label agreement from native provider admission. Two file labels cannot establish a live-eligible report. It explicitly reports provider_qualified false, authority_effect NONE and the declared-only source state. This does not implement provider identity, independence, entitlements or a qualified news feed.

Actual evidence includes ten initial failed assertions with two healthy controls, followed by four additional failed assertions exposing Python's long-fraction truncation. The first integration had 516 passes, three declared PostgreSQL skips and one failed old assertion that treated source labels as live qualification. That oracle now checks the explicit qualification fields; its original blackout, timing and source-count assertions remain. Intermediate 525-pass and 528-pass runs are retained with their original scope and hashes.

The final selection passes 532 cases against actual pinned isolated PostgreSQL with no skips, no storage-audit violations and matching source hashes. All 25 final controls pass. Six final supplemental faults are assertion-caught without setup errors and the source is restored exactly; the earlier six-fault run remains separate. These are not an execution of the canonical 374-case corpus. Raw reports and supervisors are retained under ci/calendar_feed_20261025.

Schedule availability, native publisher clocks, source identity and health, licensing, corroboration, ingestion services and full dataset chronology still require implementation and qualification. No unit, independent/native, owner, F15, BG-001, provider, production, profitability or S24 acceptance is issued.
