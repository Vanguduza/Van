# Reproduce this review

The delivered ZIP and MANIFEST bind the current files; the exact original parent ZIP and its manifest are in lineage. The original probe script, inputs/results, seven baseline command receipts and pinned source extracts are under evidence/rev115.

Run `python3 -B verification/reproduce_parent_probes.py` to safely extract the pinned parent into a temporary directory and rerun the exact original document-only script; it compares all eleven results byte-independent JSON-for-JSON with the saved receipt. It does not import VAN application modules or call a venue. Run the current checks listed in README_START_HERE.md to validate the revised contract. Python 3 plus jsonschema is required.

Fresh repository materialization used HTTPS Git, depth-one branch and PR-head fetches into a bare snapshot, without touching the user's existing checkouts. `SOURCE_RECONCILIATION_EVIDENCE.json` records every fetched ref/commit and selected file SHA-256/symbols; `fetched_refs.raw.txt` is the captured source ref inventory. `collect_review_source.py` is the exact extraction script used with the original bare `source.git`; recreating that snapshot requires the pinned objects, and a later fetch can advertise different heads. Reject source drift rather than silently rerunning against new code. PR state and native runtime identity were not obtained from Git.

The review reports hand-derived source arithmetic separately from executed documentary checks. No historical price dataset was silently downloaded, no financial experiment was executed and no per-order/account economic table is claimed. The registered future output contract is EVALUATION_PROTOCOL.md.
