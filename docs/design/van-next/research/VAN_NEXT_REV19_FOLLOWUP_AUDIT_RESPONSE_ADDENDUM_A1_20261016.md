# Addendum A1 to the Rev 1.9 follow-up audit response

**Addendum to:** `research/VAN_NEXT_REV19_FOLLOWUP_AUDIT_RESPONSE_20261016.md`, as sealed in the Rev 1.9a evidence pack (source commit `8ac8992`). SHA-256 of the base document: `2711905d657eaeeaed52a50127ea92f7f46a6740867a7a37c9c857d068b46fff`.

**Why it is separate:** the text below was first appended to the base document in commit `34bc80d`, after the pack had been sealed. The third audit (NXA-06) noted that the two copies then differed. Rev 1.9b (OD-36) restores the base document to its sealed bytes and keeps the later text here, so each file has one fingerprint.

---

**Also found while applying the fixes.**
- The evidence builder's refusal gate ("inputs must equal the committed HEAD") was tested by modifying an input on purpose, and it **failed**: the pack was built anyway. The cause was git pathspecs resolved against the wrong directory, so nothing ever looked modified. After the fix, the gate refuses both a modified input and a deleted one (exit 2), and the pack was rebuilt from clean inputs.

**Evidence pack (U8).**
- Pack: `evidence/VAN_NEXT_PREDEV_EVIDENCE_PACK_REV1_9A.zip`, bound to source commit `8ac8992`, zip SHA-256 `3dfb6518c4617a8bfef8a63ef143dfa413bb8e4bbb725bd170092df170b45648`.
- Build: deterministic, byte-identical on rebuild.
- Rerun: unzipped into an empty directory, every input matched its manifest hash, and all five commands reproduced their receipts exactly (four exit 0; the run on the pack's original machines exits 1 with its 69 findings, as expected).
