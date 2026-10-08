# Native Artemis with the owner ChatGPT subscription

This VAN integration binds native Artemis to `gpt-5.6-sol` through the existing local Codex ChatGPT login for `tapiwaguduza@gmail.com`. It uses the supported app-server stdio interface. It never reads or copies auth.json, exports credentials, switches to API-key billing, or delegates phone actuation to Codex tools.

All 20 configured native agent/utility roles and their fallback entries select the exact requested model. Artemis retains its controllers, device lock, task lifecycle, verification and traces. The profile uses Artemis's custom-provider extension seam; no upstream runtime source is edited.

## Launch on dial-control

Use `/home/ubuntu/.local/bin/van-artemis-mcp` after the owner installation has been completed. This entrypoint launches the existing native Artemis interpreter with `mcp_launcher.py` and this profile. The equivalent source command is:

```bash
/opt/hermes-mobile-fabric/artemis/current/.venv/bin/python tools/artemis_subscription/mcp_launcher.py
```

Default upstream runtime: `/opt/hermes-mobile-fabric/artemis/current`.
VAN application state and traces: `/home/ubuntu/.local/share/van/artemis-subscription`.
Set `VAN_ARTEMIS_ROOT` to select a separately qualified runtime; `VAN_ARTEMIS_CODEX` selects the existing Codex executable. Neither setting supplies new authentication.

The native diagnostic credential probe now reports a supported account/read result. It distinguishes account authentication from inference qualification. It does not assert an API key exists. Each inference session refuses a different account or an API-key account and checks the model/provider returned by thread/start.

## Model and transport behavior

The adapter supports text/image messages, typed structured output, bound Artemis tool responses and LangChain's stream interface. It returns one complete message after a successful turn/completed event; it does not expose partial structured/tool output. Tool descriptions return to Artemis for execution. Shell, browser, MCP, plugins and delegation in the Codex child are disabled, and unexpected execution/auth requests are refused.

Codex keeps and refreshes its original login in place. The child environment removes API-key overrides and native Qt/loader settings, and preserves the account home. Native Artemis injects loader settings. A startup handoff problem was observed during development; successful native model/stream/tool readback followed child-environment separation. Native timeouts and cancellations reap the owned app-server process.

Only text and images are qualified by this adapter. Audio and video blocks are explicitly refused. Full physical VAN acceptance still needs its actual fixtures, applicable owner bindings and independently checked postconditions.

## Validation

Run the optional adapter contract tests inside the installed native Artemis environment:

```bash
/opt/hermes-mobile-fabric/artemis/current/.venv/bin/python tests/test_artemis_subscription.py
```

The retained operational receipts distinguish real provider vision/structured-output checks, native factory/tool/stream checks, failed or interrupted setup attempts, handset installation and physical acceptance. Synthetic contract fixtures never count as handset acceptance.
