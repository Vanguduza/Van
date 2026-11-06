# Atomic original mission capture

The original mission row, its required `mission.created` event and pending local learning delivery now commit together. A native event-write failure rolls all three back before optional learning can observe the work. The event retains the original owner/system actor and capture time. Publication occurs only after the canonical event is visible in the database.

A lost commit acknowledgement or abrupt process exit after commit retains the complete original mission/event. The existing command-to-mission identity join recovers that same capture without creating another mission, another event or running an action. A publication error after commit leaves the canonical record intact; this does not certify automatic bus redelivery or rewrite historical incomplete captures.

Four original source tests reproduced the partial-commit and premature-learning defects. Validation includes real SQLite constraints, a real subprocess exit immediately after commit, lost commit acknowledgements, failed publication and an independent connection observing committed state at publication. The prior post-insert integrity regression now injects failure through the transaction's native event writer and requires zero orphan missions rather than preserving the old orphan row.

Evidence: `../receipts/MISSION_CAPTURE_ATOMICITY_SOURCE_20261024.json`. This is a source component and supplies no complete lifecycle/unit, migration of historical orphan events, deployment, provider, Hermes/DIAL, F15/BG or handset acceptance. No endpoint, UI, financial authority or original package byte changes.
