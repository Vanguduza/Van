# AP-002 candidate verification

Status: proposed, dry-run verified, not admitted. The original Rev1.18 package is unchanged.

AP-002 adds eight NOT_RUN acceptance identities, six test-to-unit co-listings over four existing identities, and four citation errata. Full proposed stimuli, observations, refusal/recovery cases and evidence requirements are retained in the candidate's `amendments/AP-002.json`, as well as in the proposal. No existing acceptance oracle is replaced.

Two independent candidate constructions are reproducible:

| Candidate | Identities | Changed files | Package file-tree SHA-256 |
|---|---:|---:|---|
| AP-002 alone | 1,618 | 18 | `eb88ef3a005e21a34ad49e1248beaf50c5d65d1b99897fd47f39eb2ef54becc9` |
| AP-001 then AP-002 | 1,632 | 19 | `f9e2bf7b7fb72c70ab4526c4bbdf28cb4efe6323c28bfe158c1ebb46a1a67b49` |

Each candidate passes all ten package documentary commands. The separate preservation audit compares against the original delivery, preserving original test records and order, requirement/lineage files, unit contracts, and all files. Only declared co-listings may extend existing test ownership. It also checks complete rich oracles for additions, manifest hashes/counts, and absence of a claimed signature. Thirteen regression cases include induced changes to old tests, proposed oracles, unit exits, historical source and signatures. These checks do not execute the new acceptance identities or independently admit the amendment.

Reproduce with the isolated documentary dependencies:

```sh
python -m pip install -r tools/rebuild/requirements.lock
python tools/rebuild/amendment_candidates.py /tmp/van-ap002-review AP-002
python tools/rebuild/amendment_candidates.py /tmp/van-combined-review AP-001 AP-002
python -m pytest -q tests/rebuild/test_amendment_candidates.py
```

Output directories must not exist and must not overlap the original package. The two committed `*_CANDIDATE_VERIFICATION.json` files contain exact changed-file sets, command results and digests, and regression tests rederive those receipts. Admission of either or both proposals must follow the package's owner/independent procedure. The candidate tools issue no admission, owner signature, F15, backend-complete gate, or product qualification.
