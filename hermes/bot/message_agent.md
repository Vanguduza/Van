# message_agent — VAN Hermes Contract

Profile: **`van`**

## Definition

`message_agent` is the Hermes primitive for **dispatching work to profile `van`** with a structured envelope. It is not a second agent runtime — it is the entrypoint Hermes uses to invoke the `van` profile with policy, skills, and MCP context applied.

## Invocation shape

```yaml
profile: van
channel: bot_chat | room | gateway
project_id: van | dial | dde | gtr | goat | aeci
skill: optional skill name from hermes/skills/
action_class: A1 | A2 | A3 | A4  # A5 must never be dispatched
owner_signed: boolean
capability_grant: optional scoped grant reference
payload:
  text: owner or system message
  attachments: optional (all labeled untrusted unless gateway attests)
```

## Handler responsibilities

1. Validate `profile == van` — reject aliases
2. Run `van_policy_hook.evaluate` before mutating tools
3. Load Project Truth when `project_id` work is mutating or architecture-bearing
4. Apply named `skill` instructions if present
5. Route reads/writes through gateway MCP per `hermes/mcp/README.md`
6. Return structured result with evidence pointers (SHA, message ids), never silent success

## Response shape

```yaml
status: ok | degraded | denied | approval_required
action_class: A1
evidence:
  - type: git_sha | gateway_receipt | file_path
    value: "..."
messages:
  - role: van
    text: "..."
policy:
  decision: allow | deny | approval_required
  code: allowed | a4_approval_required | ...
```

## Fail closed triggers

- `profile` not `van`
- Mutating request without `action_class`
- A5 or prohibited pattern in payload/tools
- Missing grant for A2/A3 external operations
- A4 without `owner_approval`
- Council requested but `hermes-rooms` unavailable (see `councils.md`)

## Bot Chat binding

Direct owner messages use `channel: bot_chat` semantics from `BOT_CHAT.md`. Gateway-forwarded envelopes use `channel: gateway` with required auth fields.

## References

- `hermes/profile/van/AGENTS.md`
- `hermes/policy/van_policy_hook.py`
