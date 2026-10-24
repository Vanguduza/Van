# Authenticated command-result speech delivery

This candidate connects the existing gateway result reader, speech segmentation, Android gateway client, application queue and actual playback callbacks. It repairs inherited Android wiring; it creates no new frontend design or admitted unit acceptance.

| Contract | Consumer and effect |
|---|---|
| `GET /v1/commands/{command_id}` | The device-owned durable mission/audit reader adds a stable `result_ref` and qualified `spoken_text`. |
| `POST /v1/voice/responses` | `VanGatewayClient.openSpokenResult` requests an existing command/result using a playback request ID. The gateway supplies the words; this never dispatches the command again. |
| `GET /v1/voice/streams/{stream_id}` | `speechStream` rechecks the device and current result before serving the unheard tail. |
| `POST /v1/voice/streams/{stream_id}/cursors` | `reportSpeechCursors` reports received and actually completed contiguous playback separately. Strict integer/range checks reject impossible progress. |
| `POST /v1/voice/streams/{stream_id}/interrupt` | `interruptSpeech` records interruption after local audio stops. Exact reopening cannot revive that playback request. |

All routes inherit ingress and paired-device authentication. Mutations also inherit the existing current device-key proof requirement when bound, with no internal-token or client-supplied text authority. The Android methods use the provisioned gateway, trust and proof code already present; no new in-app connection setting is introduced.

A playback request binds the device, available native turn (or command identity when no turn exists), command result and exact words. Retries retain stream identity and progress, including a lost opening reply. A deliberate new playback request gets its own delivery identity. A changed result invalidates old cached text; a definitive source refusal during cursor reporting also stops remaining local audio. Bound complete results cannot be appended to or silently revised. Generic streaming helpers are not exposed as authority to rewrite a completed command's speech.

The same result reader protects HTTP and speech. A partial, failed or unverified result retains its status warning even if a provider's summary claims success. This qualification now also reaches the durable conversation and result artifact; a raw provider claim remains recorded as source material rather than being promoted to checked success. Session command-state recovery also checks durable mission ownership.

`VanCommandController` retains the original question time/context across intermediate polls. A later capture or typed input revokes the old context; clock rollback and the existing two-minute boundary do not authorize unsolicited speech. `GatewaySpeechDelivery` checks that lease again after network waits. The application confines its delivery/playback state to the main dispatcher. Callback identity, contiguous heard prefixes and terminal interruption remain enforced. Reconnect uploads the real local heard cursor before reading a tail; process startup without a current local voice context does not autoplay cached answers. A remote interruption stops local output. Speech yielded to a call is retried only while the current voice context permits it.

Cached speech text remains in memory and expires after the existing 24-hour period. A lifecycle cleanup runs every minute and clears the cache at shutdown. Input length, total UTF-8 bytes, global stream count and per-device count are bounded; capacity refusal preserves existing progress and the displayed result. No audio is persisted by this service.

Validation: see `receipts/AUTHENTICATED_SPEECH_DELIVERY_SOURCE_20261022.json`. The expanded real HTTP/backend selection passes 155 cases without skips. New JVM controls cover wire corruption, changed owner context, heard-prefix reconciliation, local-first interruption, server interruption, backward clock and visible delivery failure. Legacy mutation identities are unchanged; the delayed-answer mutation is detected after a passing control and restored.

Hosted source `9573b320` ran all 374 legacy mutations successfully. Its public database, trading and 102 voice checks passed. Actual emulator instrumentation collected 22 cases: 16 passed, four core-artwork cases skipped, and both new voice cases failed while waiting 60 seconds for startup readiness. Neither native synthesis nor AudioTrack completion was demonstrated. The current candidate starts TTS preparation independently of ASR/wake initialization and records readiness diagnostics; its new native run must supply the result. No readiness wait or assertion is weakened.

BE-029 remains partial. Current work does not qualify acoustic recognition, financial numeral/OOV verbalization, spoken-summary quality, full Android audio-focus/browser ducking, every process/retention/replay acceptance scenario, production provisioning or S24 execution. Public CI requires all 117 voice/result source cases without skips. Native, independent, owner, financial and release authorities remain separate and unissued.
