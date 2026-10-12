# Original-Site integration package

This is not a deployed Site. Read `../../docs/project-state/MUSE_DUAL_SURFACE_CANDIDATE_20261012.md` for current verification and blocked gates.

`bff.mjs` belongs in the ORIGINAL Site backend; `requireOwner`, `signOwnerEnvelope`, `transport` and `invokeExistingTask` must be connected to its real existing code. `gatewayPublicJwk` is public-only. No browser credential or signing key belongs in the client. `client.mjs` and `muse-live-controls.mjs` add a same-origin `<muse-live-controls>` element for Conversation, Approvals and Activity without deleting existing Tasks, History, Projects or Inbox.

```html
<script type="module" src="/assets/muse/muse-live-controls.mjs"></script>
<muse-live-controls></muse-live-controls>
```

Test local server authentication/intent handling only:

```sh
node --test web/muse-interaction/bff.test.mjs
```

The test uses Node Web Crypto fixtures, no live browser and no provider action. Real Site publishing, transport integration, notification delivery and cross-client owner approval acceptance remain separate.
