"""Rev 1.5 §§7, 8, 13 — the parts of the Browser Stream Host this repository can hold.

The host itself does not exist: no Chromium, no compositor, no encoder, no WebRTC peer
(RB-002, RB-010). What lives here is the logic that would run on it and that can be
executed without any of that — specifically, the translation from the owner's input packets
into CDP calls, which is RB-017 and is the place a wrong mapping puts the owner's tap
somewhere they did not touch.
"""
