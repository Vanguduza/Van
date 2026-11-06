# Rev 2 pack → blueprint Rev 1.9 crosswalk (OD-27)

| File | Scope | Status |
|---|---|---|
| `REV2_18_PRODUCT_TRUTH_CROSSWALK_REV1_9.csv` | All 18 Rev 2 product truths (VAN-PT-01…18) → VAN-NX requirements | Reviewed; pending owner signature with the decision record |
| `REV2_93_FEATURE_CROSSWALK_REV1_9.csv` | All 93 Rev 2 features (VNX-F-*) → VAN-NX requirements and Rev 1.9 sections | Reviewed: 83 confirmed, 9 previously partial now on new rows VAN-NX-061…069, 1 relabelled per OD-22 |
| `REV2_171_ATOM_SEED_UNREVIEWED.csv` | The independent audit's mechanically propagated mapping of the 171 Rev 2 requirement atoms | **Seed only, not reviewed.** Its semantic review, with the 115 surface contexts, is a DU-01 obligation (blueprint §16.1) |

**Method.** The independent audit's seed CSVs (archive SHA-256 `3a7300e7c1b3256da659d488e157f9997e4b5523581b7adc0665b1ba1e349e64`, see `research/VAN_NEXT_REV18_INDEPENDENT_AUDIT_RESPONSE_20261015.md`) were checked row by row:
- every referenced VAN-NX ID exists in Rev 1.9 (0 dangling);
- every cited section exists;
- each feature title was read against the requirement's wording.

Fourteen rows were corrected or completed; they carry a note in the CSV. In the other direction, every VAN-NX requirement is referenced by a Rev 2 item except VAN-NX-026 (REA research input), which has no Rev 2 counterpart.

**What this is not.** It is a document-level mapping. The execution evidence for each feature (action, state, producer, caller and tests) is `NOT_ASSESSED` until DU-01 and the feature's own packet.
