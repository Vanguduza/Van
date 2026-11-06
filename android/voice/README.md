# Pinned generic offline voice pack

The APK includes generic KWS, ASR, VITS and WeSpeaker weights, exact runtime configurations,
reviewed notices and a real synthesized `hie van` acknowledgement. It includes no owner
embedding, speech profile, enrollment audio, owner signer or gateway credential.

Prepare the reviewed local staging directory:

```
python3 android/tools/package_voice_assets.py --staged /workspace/van-acoustic-assets/selected
```

For a clean development machine, acquire the exact official public artifacts named in
`acquisition-lock.json` before an APK build:

```
python3 android/tools/package_voice_assets.py --acquire
python3 android/tools/package_voice_assets.py --verify
```

Acquisition preserves TLS verification and refuses changed size/digests. It downloads at most
1 GiB and extracts only exact selected weights. No download occurs in Gradle or first launch.
Small derivative/configuration/license files live in `source/`; large weights remain in ignored
`app/build/generated/voice-assets/`. The build verifies this generated directory before packaging.
`VoiceBundlePin.kt` binds exact source manifest bytes; the APK signature authenticates that pin.
Changing an acquisition result never changes the expected source digest automatically.

First launch prepares the pack on IO into private application storage, verifying exact size and
SHA256 of every file before publishing the completed directory. Main-thread readers only observe
published readiness. Actual native inference/self-tests separately gate runtime readiness. VAD
is the actual built-in RMS/energy endpointing mechanism; no unused neural VAD is claimed.
The selected VITS lexicon is bounded: an utterance containing a missing word falls back as a whole
to a verified on-device Android voice or visible text, rather than silently dropping words.

`SpeakerEnrollmentManager` uses the generic model only after a dedicated fresh one-use biometric
signature by the existing paired approval key. Three bounded genuine clips stay in memory;
quality checks are energy usability, not evidence of identity. Only their normalized native
aggregate and exact device/model/consent metadata are stored in authenticated encrypted preferences.
Profile use requires fresh owner-binding verification; local privacy removal can work offline
when the stored binding matches the existing local hardware and approval keys. Similarity is
revocable provenance and never command authorization. Actual capture, owner accuracy, enrollment,
biometric behavior and handset performance remain handset acceptance work.

The generic native probes distinguish graph/inference compatibility from accuracy. The selected
non-mobile KWS graph passed native decode and silence checks; the staged synthetic positive
produced zero hits. ASR/TTS/speaker probes are not owner accuracy qualification. Owner wake
accuracy, false accepts/rejects, capture quality and phone performance remain unverified.

Retain all `source/licenses/` notices. Generic model licenses and speaker CC BY4 attribution are
recorded separately. The admitted Sherpa1.13.8 AAR includes statically linked eSpeak GPL3 code;
a lexicon-only VITS runtime does not remove that binary component. `NATIVE-SOURCE-INPUTS.json`
inventories inspected corresponding-source selectors but is not a complete source bundle or
source-to-binary reproduction proof. This prepares inputs for a private owner acceptance
artifact; public redistribution and a signed production release are not qualified. Existing owner production
signing remains a separate external prerequisite; this tooling creates no signing identity.
