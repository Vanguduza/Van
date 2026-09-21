"""Rev 1.5 §20.10 — the path epoch is granted, and the phone has to adopt the grant.

Two implementations of one rule, in two languages, with a failure mode that is invisible
in either half on its own: the Gateway grants `new_path_epoch` on every accepted resume,
`accept_upstream` fences any envelope that does not carry the authoritative one, and the
phone resumes the moment its socket opens. A client that kept the epoch `/open` gave it, or
that incremented one of its own, has every owner message refused — with the socket open,
the status screen green, and neither side logging anything that looks like a fault.

`backend/tests/test_session_transport_api.py` pins the Gateway's half against the running
app. This pins the phone's: that `VanHermesSessionManager` reads the granted number, and
that it does not mint one instead.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANAGER = ROOT / "android/app/src/main/java/com/dial/van/session/VanHermesSessionManager.kt"
SERVICE = ROOT / "backend/van_gateway/session/service.py"
API = ROOT / "backend/van_gateway/session/api.py"

GRANT_FIELD = "new_path_epoch"


def _manager() -> str:
    return MANAGER.read_text(encoding="utf-8")


def test_the_gateway_still_calls_the_granted_field_what_the_phone_reads():
    """The name is the contract. A rename on one side is a silent divergence."""
    service = SERVICE.read_text(encoding="utf-8")
    assert f"{GRANT_FIELD}=" in service, "the resume result no longer carries the grant"
    assert GRANT_FIELD in _manager(), "the phone no longer reads the grant"


def test_the_gateway_grants_a_new_epoch_rather_than_echoing_the_old_one():
    """`+ 1` on the session's authoritative epoch, in the service that issues it.

    Stated here as well as exercised at the route because it is the premise of everything
    below: if a resume echoed the current epoch, adopting the grant would be a no-op and
    the phone could keep its own counter without anyone noticing.
    """
    service = SERVICE.read_text(encoding="utf-8")
    assert "session.authoritative_path_epoch + 1" in service


def test_the_phone_does_not_mint_a_path_epoch_of_its_own():
    """The bug this replaced, kept out by name.

    `pathEpoch = _state.value.pathEpoch + 1` in the socket's failure callback agreed with
    the Gateway after exactly one failure and one resume, and diverged permanently after
    two failures in a row — which is what a carrier handover on a moving train looks like.
    """
    text = _manager()
    assert "pathEpoch = _state.value.pathEpoch + 1" not in text
    assert "pathEpoch + 1" not in text, "the phone is incrementing an epoch it was granted"


def test_the_grant_is_adopted_on_an_ordinary_resume_and_not_only_on_a_failover():
    """The part that made this a live bug rather than a failover bug.

    The first resume happens on `onOpen`, before anything has failed. An adopter that ran
    only inside the failover branch would leave a freshly-connected phone stamping the
    epoch `/open` gave it, and every message it sent would be fenced.
    """
    text = _manager()
    adopt = text[text.index("private fun adoptGrantedPathEpoch") :]
    adopt = adopt[: adopt.index("\n    private fun adoptCursor")]
    assert "failover != null" in adopt, "the adopter no longer distinguishes the two cases"
    # The non-failover branch has to actually write the epoch.
    assert "pathEpoch = granted" in adopt


def test_both_resume_outcomes_that_keep_the_session_adopt_the_grant():
    """RESUMED and RESUMED_WITH_NEW_EPOCH both continue the session on a new path epoch.

    Only one of them adopting it would make the bug depend on whether the Gateway had also
    bumped the *session* epoch, which is the kind of conditional failure that reproduces
    on one person's phone and nobody else's.
    """
    text = _manager()
    for outcome in ("ResumeOutcome.RESUMED ->", "ResumeOutcome.RESUMED_WITH_NEW_EPOCH ->"):
        branch = text[text.index(outcome) :]
        branch = branch[: branch.index("ResumeOutcome.", len(outcome))]
        assert "adoptGrantedPathEpoch(response)" in branch, outcome


def test_the_route_that_grants_it_is_the_one_the_phone_calls():
    """A grant on a route nobody calls is not a grant."""
    api = API.read_text(encoding="utf-8")
    assert '@api.post("/resume")' in api
    assert "sessionResume" in _manager()
