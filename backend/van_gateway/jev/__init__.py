"""VAN's client of the one DIAL Jev service (`dial-jev`, DDS).

The VAN gateway never carries TypeSafe/provider credentials. It reads the private DIAL Jev
control-plane API, exposes an owner-device projection and asks registered judgments.

One Jev (Programme B, B0): nothing in this package starts a service, opens a browser,
keeps a judgment ledger or executes an action. Jev output is evidence; the owning VAN
subsystem decides, and the Browser Harness / Browser Control Agent executes.
"""
