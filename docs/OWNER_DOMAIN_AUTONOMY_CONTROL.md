# Owner domain autonomy ceilings

`GET /v1/autonomy` returns the current trust/evidence rows and policies. Its
additive `known_domains` list derives from actual registered action namespaces
(the autonomy gate's first two dotted segments) plus existing trust records.
`supported_levels` is exactly `S0` through `S4`; `typed_command_prefix` is
`set domain autonomy ceiling `.

Submit the existing signed owner command endpoint `POST /v1/commands` with text:

```text
set domain autonomy ceiling {"domain":"google.gmail","level":"S3"}
```

Only those two string properties are supported. The canonical action is
`owner.autonomy.ceiling.set`, class A4, with a 30-second freshness window and
no stale execution replay. The existing biometric challenge binds the exact
normalized domain and level. Android's Work approval preview displays those
parameters before biometric consent. A new occurrence needs a new biometric;
there is no direct grant endpoint or model/external-runtime grant writer.

The atomic local writer rechecks owner command provenance, exact approved
parameters, current device revocation, original expiry, the running mission,
and the actual known-domain list under the write lock. It commits the grant,
materialized effective ceiling, and command-specific witness together.
Independent action and mission readback query the committed domain row and
the exact current owner operation. An abandoned delivery can reconcile that
committed result even after the original effect authority expires; it never
reexecutes the grant or raises a ceiling that a newer owner choice lowered.

Lower owner ceilings cap even well-earned suggestion/preparation. False-success
or negative evidence still suspends execution at S0. Setting S3/S4 does not
create standing policies, capability permissions, action effects, financial
authority, or permission to bypass native A4 biometric approval. S5, wildcard
domains, invented domains, and additional parameters are refused. A target
readback failure reports an explicit uncertain/degraded result rather than
verified success; the owner can inspect the current domain state.

The static capability declaration is `NATIVE_CONTROL`, A4 and owner-present.
Its declaration/readiness metadata is not executable authority: the actual
local action remains bound to the approved owner command and current device.
