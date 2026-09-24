"""VAN-DEV-001/002/010 — the VAN side of DIAL's Development Projection API v1.

VAN displays DIAL development state and forwards typed owner commands to DIAL. It never
plans, schedules or executes DIAL work: Hermes profile `van` remains VAN's sole agent
runtime (docs/SECURITY_POLICY.md), and DIAL's own Hermes/Oracle chain remains the only
thing that acts on DIAL. The contract this package implements is DIAL's
`VAN-DEVCC-R1` (VAN Development Control Centre Design Rev 1, §§2.2, 3, 5, 7, 8).

Boundaries held here:

* Android calls `/v1/dial-dev/*` on the VAN gateway only. The gateway alone calls DIAL's
  `/v1/dev/*`, with a DIAL-scoped bearer read from a gateway-side token file that never
  appears in any response.
* Every projection envelope is passed through byte for byte. VAN never fills a gap with a
  local guess and never marks anything done: the projection decides.
* Owner actions are a closed set, require a hardware device proof, and are de-duplicated
  through the gateway's existing idempotency service.
"""
