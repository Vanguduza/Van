# BE-008: native event selection without delivery loss

Status: source-tested component; no full unit acceptance.

Three framed-socket regressions fail on the preceding source: matching a later execution event reorders earlier unmatched events; a predicate exception consumes the current financial delivery; and a slow selector hides an unmatched delivery from a competing consumer. The fixture uses an ordered native application-authentication response after the original frames. No live provider is involved.

Selection now examines queued originals without removing them. Predicates run outside queue/state locks against copied payloads. A successful selector claims one original by identity, so concurrent selectors cannot receive the same delivery. Unmatched entries retain their original order and complete payloads; exceptions, invalid timeouts and callback expiry leave their originals available for reconciliation. A quote whose connection retires during selection cannot seed a replacement. Financial evidence remains available after disconnect. No native request, financial receipt, authority or retry policy is added.

The final wider selection passes 958 cases without skips or storage-audit violations against actual isolated pinned PostgreSQL. All 108 rebuild checks pass. Fifteen final selector controls pass, and six supplemental faults are assertion-detected with no setup errors before exact source restoration. These six faults are separate from the original 374-case mutation corpus; registry consistency is checked without claiming its execution on this local-only source.

The PostgreSQL supervisor captured the new test file hash before an unused import was removed during startup. Production source hashes match exactly and test assertions did not change. The unchanged raw receipt and final 15-case control are retained; the receipt is not presented as a byte pin for the final test file. An intermediate glob run collected the initial three tests twice and had six PostgreSQL opt-in skips; it is not the final unique zero-skip selection.

This remains volatile SDK delivery selection. Durable tick/live-bar capture, stream capacity/error journals, governed host/service isolation, source entitlements, depth/calendars and qualified consumers remain. Arbitrary callback code is not an interruptible host sandbox; elapsed time is checked on return. No acceptance or production/device outcome is inferred.
