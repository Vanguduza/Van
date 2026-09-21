"""Rev 1.5 §13.2 — the only cross-host bridge to Chromium.

Raw CDP stays bound to loopback on the Browser Stream Host. Nothing on the private VCN,
and nothing on the public side, ever speaks CDP; Trading Core's Stagehand and Browser
Harness reach this agent over mTLS and it speaks CDP locally on their behalf.

The reason is one sentence long. CDP is a remote code execution interface: `Runtime.evaluate`
runs arbitrary JavaScript in a page that holds the owner's logged-in sessions, and
`Page.navigate` will happily fetch `file:///`. Exposing it across a host boundary — even a
private one — is exposing that, and the blueprint's §13.2 list of what this agent must *not*
offer is a list of the ways that goes wrong.

So the agent is narrow by construction: a fixed set of operations, each with a declared
scope, each validated against a control lease before it touches the browser.
"""
