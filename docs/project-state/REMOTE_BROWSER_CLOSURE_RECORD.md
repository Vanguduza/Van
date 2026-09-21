# Remote Browser Rev 1.5 — closure record

**Date:** 2026-09-20
**Historical implementation branch:** `claude/van-system-audit-ysgtcd`  
**Current canonical branch:** `main` (PR #55 merged at `ae96854b85c1ff1c8bcd483cd90cef270c7cf23b`)
**Authority:** `docs/VAN_REMOTE_BROWSER_PRODUCTION_BLUEPRINT_REV_1_5.md`
**Verdict:** `REPOSITORY_COMPLETE_PENDING_EXTERNAL`

This is the record of what the Remote Browser programme finished, what it did not, and how
to tell those apart without taking anyone's word for it. Every number below is produced by
a checker in CI rather than written here, and each one names the checker.

## The verdict, stated once and not softened

The Remote Browser is **not production accepted** and cannot be from a repository. §43
names one hundred and four requirements; fifty-nine are proven here and forty-five are
not. The forty-five are not all a backlog. Thirty-eight need a Browser Stream Host, a
carrier handover or the owner's S24 Ultra, and seven need the owner to provision or
accept something — a keystore, a voice asset pack, a second ingress, a look at a screen.

One of the thirty-eight arrived by subtraction and is the most useful line in this
document. Row 63, STORE_AND_FORWARD, read `REPOSITORY_PROVEN` from the day it was
written until C16, on evidence that was real and that all passes. Every one of those
tests calls the outbox directly, and in the running app nothing does.

Nothing in §43's **Runtime**, **Performance** or **Stream/control topology** groups is
proven, because none of it exists here to be proven against. Not one frame has been drawn
anywhere. No TLS handshake has happened in either direction. No latency has been measured.

`REPOSITORY_PROVEN` is the strongest thing this repository can say and it is weaker than
certification: it means the code demonstrates the behaviour and names what does. It does
not mean anyone has watched it work on a phone.

## The registers, and what each refuses

| Register | Contents | Checker |
|---|---|---|
| `evidence/van-system-audit/findings.json` | 154 findings, all closed: 76 `INTEGRATED_AND_EVIDENCED`, 72 `EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE`, 6 `DELIBERATELY_REMOVED_CANON_CORRECTED` | `tools/ci/maturity_gate.py` — refuses a closure state that claims more than its residual class allows |
| `evidence/van-system-audit/component_ledger.json` | 209 components, all at a terminal state: 133 integrated, 69 externally blocked, 7 deliberately removed | `tools/ci/maturity_gate.py`, `tools/ci/ledger_reconcile.py` — the first refuses a ledger that overstates, the second one that understates |
| `docs/project-state/REMOTE_BROWSER_IMPLEMENTATION_MATRIX.json` | 122 rows: 87 `WIRED_UNPROVEN`, 21 `NOT_STARTED`, 9 `BUILT_UNWIRED`, 3 `BLOCKED`, 2 `VERIFIED_UNCERTIFIED` | `tools/ci/ledger_reconcile.py` — refuses a row whose booleans contradict its status, and an empty `external_gates` |
| `evidence/van-system-audit/red_team_register.json` | §38's 72 scenarios: 63 `PASS`, 9 `BLOCKED_EXTERNAL`, **0 assumed** | `tools/ci/red_team_register.py` — every `PASS` must cite a runnable pytest node id |
| `evidence/van-system-audit/production_acceptance.json` | §43's 104 requirements: 59 proven, 38 blocked external, 7 owner deployment | `tools/ci/production_acceptance.py` — recomputes the verdict from the rows |
| `docs/project-state/AUTHORITY_MAP.yaml` | every invariant, owned once | `tools/ci/authority_map.py` |

Six registers, six checkers, all six in `.github/workflows/van-ci.yml`, and each with a
self-test — because a gate that only ever passes proves nothing.

## What the twenty-one `NOT_STARTED` rows are

Every one needs something no commit can supply, and each row says which:

- **the Browser Stream Host itself** (RB-011 display, RB-012 capture, RB-013 H.264 encode,
  RB-014 Opus, RB-015 ICE/STUN, RB-016 TURN, RB-033 Chromium crash recovery) — §13 makes
  the host a separately deployed component and RB-002 is an owner decision that has not
  been taken;
- **canaries against real hardware** (RB-053 latency, RB-054 S24 device, RB-055 production
  stream-host, RB-056 soak, RB-085 offline voice S24, RB-086 voice-through-failover,
  RB-092 split-screen, RB-093 Samsung pop-up, RB-112 second-device refusal, RB-114
  zero-configuration acceptance, RB-120 S24 attestation preflight) — a canary is a
  measurement, and there is nothing to measure;
- **a local ASR/TTS runtime the owner declined** (RB-073 Sherpa-ONNX, RB-075 ASR fallback,
  RB-078 bundled TTS) — owner decision 2, with minSdk raised to 31 so the platform
  recogniser is always present, which is the other half of that decision.

## The 9 `BUILT_UNWIRED` rows, and why that is the honest status

RB-010 (stream-host provisioning), RB-116 (Trading Core → Stream Host mTLS), RB-118
(profile storage) are built and have nothing to be wired to. RB-072, RB-074, RB-076,
RB-079 are the offline voice decisions: implemented, executed in the JVM harness, and
waiting on a voice asset pack that does not exist.

RB-065 (warm standby) is the eighth and it was moved here by review. It had read
`WIRED_UNPROVEN`, which overstated it: §20.9's policy is built and executed, and the
second authenticated socket it governs is not. `VanHermesSessionManager` holds one
`WebSocket`, so a `StandbyDecision` of `WARM_STANDBY` says what the phone can afford and
not that a spare path is open. Three tests now fail if the source implies otherwise.

Seven were moved here at C16a and six went back at C16b, once the cause was repaired
rather than only recorded. It was: **the §20 device session is
constructed and never started.** `VanApplication` builds `VanHermesSessionManager`, calls
`setInteractionActive` and `setStandbyConditions`, and stops. `start()` has no caller
anywhere in the app — four references to the field in the whole source tree. So no socket
opens, nothing resumes, nothing is restored, and `submit` is never reached. RB-035,
RB-061, RB-062, RB-064, RB-068, RB-069 and RB-071 all described things downstream of that
call, and all seven read `WIRED_UNPROVEN`.

RB-062 is the one that stayed. §20.1 lists a `session/transport/` directory that was never
created, so `DEFAULT_PATHS` declares a `fallback-http2` path that nothing can open and the
supervisor can name a failover target the manager cannot reach.

Two checkpoints made the session outbox durable and then atomic without either noticing
that nothing puts anything in it. `tools/audit/kotlin_reachability.py` did not catch it
and could not: it asks whether anything *references* a file, and a constructor is a
reference. `tests/contracts/test_session_is_driven.py` asks the other question, and holds
the matrix to the answer in both directions — so it does not have to be deleted when the
session is finally wired.

`BUILT_UNWIRED` is the status §42.5 exists to make sayable. None of these is hidden:
the reconciler refuses a row whose booleans contradict its status, and §43's "implementation
matrix contains no hidden `BUILT_UNWIRED` item" is satisfied by every one declaring it.

## The three `BLOCKED` rows

RB-002 (owner streaming-host decision), RB-040 and RB-041 (Stagehand live gate and
same-session attach). The first is a decision; the other two wait on it.

## What this pass found that reading would not have

Four defects in this final stretch had one property in common: every component involved was
correct, and the system was broken anyway.

**P0-SESS-001.** `POST /v1/session/resume` grants a new path epoch on every accepted
resume. `accept_upstream` fences any envelope that does not carry it. The phone kept the
epoch `/open` gave it. Since the device resumes on `onOpen`, **every owner message over
the durable session was refused from the first healthy connect** — socket open, status
screen green, nothing logged that looks like a fault. Found by probing the running service,
not by reading either half, and the session's only tests drove the service directly, where
the client's arithmetic does not exist.

**P0-SEC-013.** Two screens asked the owner to type a Gateway address and a pairing code —
the first and fifth entries on §0D.2's list of fields a production build must never expose.
A complete compromise of the assistant was one convincing message away, on either of two
screens.

**P2-AND-018.** A second parser for the build-time trust anchor nearly shipped in the fix
for the above. It read a `kid=PEM` string as JSON, would have reported every correctly
configured release APK as having no anchor, and the only symptom would have been a phone
sitting on "waiting for the installer" forever — with every test green.

**P1-OBS-005.** §27's quality controller was correct, unit-tested and had no caller. The
rule that VAN must not silently consume hours of the owner's mobile data was enforced by a
class with no instances.

## What external review found that this pass did not

Three material corrections came from a checkpoint review rather than from the registers,
and the shape they share is worth more than any of them individually: **each was a claim
whose supporting tests all passed, because every one of those tests ran in the same
process the claim was about.**

**The durable outbox was durable in name.** §20.14's policy — reconfirmation, expiry,
attempt count, the path last attempted — lived in an in-memory `ArrayDeque` in
`VanHermesSessionManager`, which never touched `EncryptedCommandQueue` at all. Android
kills backgrounded processes routinely, so after a kill a command could survive in the
encrypted queue while the policy deciding whether it may be *silently replayed* did not.
Every outbox test passed because every one of them was in-process. Fixed: the metadata now
rides on the canonical queue's own record, one write, persisted before it is queued and
forgotten only after the send returns.

Writing the restart tests found two further defects nobody had raised. The mapping
silently dropped `commandId`, which is the identity §20.12 matches a restored command by —
a restart would have sent it twice. And a session envelope sitting in the shared queue was
*dispatchable by the replayer*, which is P0-SEC-002's exact shape; it is now a named
refusal rather than a reliance on `commandTextOrNull` happening to return null.

**The warm standby is policy, not a transport.** `StandbyDecision.WARM_STANDBY` says what
the phone can afford. There is one socket. §20.9's make-before-break is unbuilt, RB-065 is
`BUILT_UNWIRED` rather than `WIRED_UNPROVEN`, and three tests now fail if the source
implies otherwise — one counts the sockets, one reads the claim boundary out of the
policy's own docstring, one counts the routes.

**An unreadable battery authorised optional spending.** `UNKNOWN` was converted to 100
before the standby decision, which is the one value that buys a second socket. The right
instinct applied to the wrong question: `VanResourceEnvelope` treats unknown as no pressure
because there the question is whether to take capability *away*. A spare socket is cost,
and the repository already stated that asymmetry three files away in `networkCost`.

### The second review, and the seam behind the seam

A later review accepted the outbox fix and named the one thing still wrong with it: a
persist was `remove()` then `enqueue()`, two persistent operations with a process death
possible between them. It asked for an atomic upsert and a kill test in that gap.

It was right, and attacking it found the seam was worse than the report. `enqueue` mints
its own row id, so the record was never keyed by the message id — which means that
`remove` matched nothing and neither did `forget`. Every delivered command stayed on disk
and was restored and re-sent after each restart. `enqueue` also de-duplicates on the
idempotency key and returns the existing row unchanged, so a reconfirmation — the owner's
"yes", already stamped on the entry — was silently discarded and the owner was asked the
same question again after the next kill. And `EncryptedCommandQueue`'s own `persist` and
`remove` were each two SharedPreferences editors with asynchronous `apply()`: three
non-atomic writes, not one.

All four are the same mistake. An *insert* API was used where the outbox needed an
*upsert keyed on the message id*, and nothing forced the difference into view because the
adapter could not be executed — it took `EncryptedCommandQueue`, so every test in the
repository exercised a nine-line fake instead. `OutboxRecordStore` is that operation, the
adapter depends on the interface, and the adapter itself now runs in the harness against a
store that can be killed between operations.

**A resume dropped every command it asked about.** Writing the restart-to-delivery test
required §20.12's reconciliation to work, and it did not. The phone sent `inFlight.keys` —
*message* ids — as `pending_command_ids`; the Gateway resolved each as a *command* id
against the mission table; every answer came back `UNKNOWN`; and the phone then removed
every key it had asked about, unknowns included. `UNKNOWN` is the Gateway saying it has
never heard of this, which is the one answer that means resend. So every reconnect
silently discarded every unacknowledged owner command — and nothing looked wrong, because
the two defects cancelled: nothing was resent because nothing was recognised, and nothing
was left behind to notice.

**Three of the four session kinds had no delegate, and the refusal burned the key.**
`SessionRouter` knows four upstream kinds and `app.py` wired one. Worse than a missing
feature: the router admitted the envelope into §20.12's table *before* discovering it had
nobody to hand it to, so the idempotency key was taken with a null result and the phone's
retry came back `ALREADY_KNOWN` — which reads as success. "Cancel it" over the durable
session was acknowledged, never performed, and unrepeatable.

## The lesson this pass added to the programme's list

A mutation survived its first run: a rate limiter that recorded refused packets. The test
that should have caught it sent ten thousand refusals at a single timestamp — which
recovers under either implementation, because one timestamp ages out in one step. The test
exercised exactly the right line and asserted something true either way.

What separates them is a flood spread over time that then stops: the correct code admits
the owner's very next packet and the broken one never admits another, because each refusal
extends the window that caused it. **A test can be about the right thing, run the right
code, and still assert the wrong consequence.**

The second review added a sharper one. **A component that cannot be executed is tested by
proxy, and the proxy is always correct.** The outbox adapter had four defects and a full
suite of passing tests, because every one of those tests ran against a fake that
implemented the interface as intended rather than against the file that would ship. The
repair is not more tests; it is moving the dependency so the shipped file is the tested
file — here, an interface narrow enough to fake in a dozen lines, with the Keystore and
the disk left behind it.

And a corollary about fault injection: **a kill switch named for the operation rather than
the boundary injects the fault in the wrong gap.** The first version of the sweep said
`killAfter` and meant "before", which put the fault outside the window under test — and it
passed. The counterexample is kept executable: the previous two-step adapter is still in
the test file, and a test asserts it still loses the command. If that ever stops
reproducing, the sweep guarding the new one has gone quiet.

### The lesson C17 added

**Strengthening a shared primitive for one caller changes it for all of them.** The queue
was moved from `apply()` to `commit()` so the outbox's "saved" is true when it is said.
That is right, and it turned every write into a synchronous encrypted one — including
three Android main-thread entry points that had always been fine: a share, each arriving
notification, and the owner's "discard everything" tap, which looped one committed write
per queued command.

Review found it by asking where the synchronous write actually *runs*, rather than
accepting that the durability had improved. The general form is the one this programme
keeps meeting from a new direction: a change is judged against the caller it was made
for, and the callers it was not made for are where it lands.

### The third time, and what it says about the method

C18 found the same shape a third time: two halves of a wire format, each internally
consistent, with nothing that runs both. The client read `seq` from the top of a frame
where it is nested, and matched an acknowledgement on `"session.ack"` — a string the
Gateway does not send, because its answer carries the *envelope's* kind.

Three silent consequences: the cursor never advanced, nothing left `inFlight`, and every
downstream event was parsed into nothing. §20.1's "SHALL feed durable downstream pages
into `EventStream.applyPage`" was not merely unmet — there was also nowhere to feed,
because the history lived in a composable's `remember` and an application-scoped socket
cannot write into one.

**The method that finds these is the same every time.** Not reading the code for
correctness, but asking whether the thing one side produces is a thing the other side
consumes — and then pinning the answer in a test that reads *both* sources. Three of those
tests exist now, for the stored command body, the session socket's frames and the
offline-intent windows. Each was written after a defect the reviews and the suites had
both missed.

## What to do next, in order

1. **RB-002** — decide whether to provision a Browser Stream Host. Twenty of the
   twenty-one `NOT_STARTED` rows and most of §43's blocked requirements are downstream of
   this one decision.
2. **A production keystore and a connectivity signing key.** Without both, `assembleRelease`
   refuses to produce an APK at all — deliberately, since a release with no trust anchor
   installs and waits forever.
3. **Run `tools/provisioning/provision_owner_device.py` against the owner's S24.** It has
   never been run against a device, and RB-114's acceptance canary is exactly that.
4. **The device canaries**, once there is something to run them against.

Nothing on that list is a repository change, and that is the closure claim: the
repository's half is finished, and the registers name every place it stops.
