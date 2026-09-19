"""P2-CTX-003 — the owner's control over the graph that describes them.

The finding: "Retention exists. Export, correction, erasure, revision history and conflict
semantics do not." Erasure did exist (P2-MEM-002), which makes the rest worse rather than
better — VAN could destroy thirteen stores of owner-derived material on request while
permitting the owner to read two of them, through an internal-control route, by scope.

Four tests carry the weight, and each is written against a counterexample in which the
implementation looks green and the owner's real position is unchanged:

- an export that covers fewer stores than the erasure clears, so the owner can delete what
  they were never shown;
- an export that drops rows past a cap without saying so, so the owner believes VAN knows
  less than it does;
- a correction that closes the prior record and records no link, so "what changed VAN's
  mind" is unanswerable and a correction is indistinguishable from an expiry;
- a contradiction that exists only where something happened to ask, so two conflicting
  owner statements sit in the graph and nothing ever says so.
"""

from __future__ import annotations

import time

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.config import get_settings
from van_gateway.context.forget import FORGETTABLE
from van_gateway.context.lifecycle import MAX_ROWS_PER_STORE, ContextLifecycle
from van_gateway.context.models import (
    ContextEdgeCandidate,
    EpistemicState,
    OwnerFactCandidate,
    SensitivityClass,
    SourceTrust,
)
from van_gateway.context.service import ContextAdmissionError, OwnerContextService
from van_gateway.storage.db import Store

INGRESS = "ctx-lifecycle-ingress-0123456789"
INTERNAL = "ctx-lifecycle-internal"


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "ctx-lifecycle.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.invalid")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_EXA_EGRESS_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def store(tmp_path):
    s = Store(str(tmp_path / "lifecycle.sqlite3"))
    await s.migrate()
    return s


@pytest_asyncio.fixture
async def lifecycle(store):
    return ContextLifecycle(store, OwnerContextService(store))


@pytest_asyncio.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"X-Van-Ingress-Token": INGRESS}
    ) as ac:
        async with app.router.lifespan_context(app):
            yield ac, app


async def _enrol(ac, app, device_id="ctx-dev"):
    ticket = await app.state.auth.create_pairing_ticket(device_id)
    enrolled = await app.state.auth.pair_device(
        ticket.token, device_id, "s" * 32, "PEM", device_id
    )
    ac.headers.update({"X-Van-Device-Token": enrolled.access_token})
    return device_id


def _fact(fact_id, value, *, subject="OWNER", predicate="commute", at, **kw):
    return OwnerFactCandidate(
        fact_id=fact_id,
        subject=subject,
        predicate=predicate,
        value=value,
        authority=kw.pop("authority", EpistemicState.CANONICAL_OWNER),
        source_trust=kw.pop("source_trust", SourceTrust.OWNER_EXPLICIT),
        source_ref=kw.pop("source_ref", "owner:said-so"),
        valid_from_ms=at,
        observed_at_ms=at,
        **kw,
    )


# --------------------------------------------------------------------- export


@pytest.mark.asyncio
async def test_the_export_carries_records_not_counts(lifecycle, store):
    """/v1/context/memory already gave counts. A count is not an answer."""
    now = int(time.time() * 1000)
    await lifecycle.context.admit_fact(
        _fact("f-commute", "cycles to work", at=now)
    )
    exported = await lifecycle.export()

    facts = exported["stores"]["owner_facts"]
    assert facts["rows_held"] == 1
    assert facts["rows_exported"] == 1
    assert facts["truncated"] is False

    [record] = facts["records"]
    assert record["value"] == "cycles to work", "the export must carry what VAN believes"
    # Provenance, which is the difference between an export and a list of opinions.
    assert record["authority"] == "CANONICAL_OWNER"
    assert record["source_trust"] == "OWNER_EXPLICIT"
    assert record["source_ref"] == "owner:said-so"


@pytest.mark.asyncio
async def test_every_forgettable_store_appears_in_the_export(lifecycle):
    """The asymmetry that made this a finding, asserted against the real export.

    `forget.py` clears thirteen stores. `export_scope` covered two, behind an operator
    credential, by scope. So VAN would destroy on request material the owner had no way to
    see first — which is not a privacy control, it is a shredder.

    This compares the export's actual output to the erasure list, which is the only version
    of the assertion worth making. An earlier draft compared a module constant derived from
    `FORGETTABLE` back to `FORGETTABLE` and passed by construction while proving nothing.

    Empty is an answer; missing is not. A store with nothing in it must still be named, or
    "VAN holds nothing here" and "this export does not cover that" look the same to the
    person reading it.
    """
    exported = await lifecycle.export()
    assert set(exported["stores"]) == {entry.table for entry in FORGETTABLE}
    for entry in FORGETTABLE:
        assert entry.table in exported["stores"], f"{entry.table} is erasable but not readable"
        assert exported["stores"][entry.table]["holds"] == entry.description


@pytest.mark.asyncio
async def test_truncation_is_declared_rather_than_silent(lifecycle, store, monkeypatch):
    """A cap that hides rows is the export equivalent of lying by omission.

    The cap is real — an unbounded export of a graph that grows for years is its own
    failure — so what matters is that every store says whether it hit one.
    """
    import van_gateway.context.lifecycle as module

    monkeypatch.setattr(module, "MAX_ROWS_PER_STORE", 2)
    now = int(time.time() * 1000)
    for i in range(5):
        await lifecycle.context.admit_fact(
            _fact(f"f-{i}", f"value-{i}", predicate=f"p{i}", at=now)
        )

    facts = (await lifecycle.export())["stores"]["owner_facts"]
    assert facts["rows_held"] == 5
    assert facts["rows_exported"] == 2
    assert facts["truncated"] is True, (
        "the owner must be told the export is partial; a short list that looks complete is "
        "worse than no export"
    )


@pytest.mark.asyncio
async def test_the_export_needs_no_redaction_because_admission_refuses_secrets(store):
    """Why the export filters nothing, asserted where it can go wrong.

    `export_scope` carried `sensitivity != 'SECRET'`, which reads as a redaction and is in
    fact a filter over a provably empty set: admission refuses SECRET outright, for facts
    and for edges. Copying that filter into the owner export would have been harmless today
    and a silent omission the moment admission changed. So the export filters nothing and
    this test holds the precondition instead — if SECRET ever becomes admissible, this
    fails and the decision gets made deliberately rather than by a WHERE clause nobody
    re-read.
    """
    context = OwnerContextService(store)
    now = int(time.time() * 1000)

    with pytest.raises(ContextAdmissionError):
        await context.admit_fact(
            _fact("f-secret", "a token", at=now, sensitivity=SensitivityClass.SECRET)
        )
    with pytest.raises(ContextAdmissionError):
        await context.admit_edge(
            ContextEdgeCandidate(
                edge_id="e-secret",
                from_node="OWNER",
                predicate="holds",
                to_node="a token",
                authority=EpistemicState.CANONICAL_OWNER,
                source_trust=SourceTrust.OWNER_EXPLICIT,
                source_ref="owner:said-so",
                valid_from_ms=now,
                observed_at_ms=now,
                sensitivity=SensitivityClass.SECRET,
            )
        )


# -------------------------------------------------------------------- history


@pytest.mark.asyncio
async def test_a_correction_records_what_it_corrected(lifecycle):
    """The defect: supersedes_fact_id was read, used, and thrown away.

    admit_fact closed the prior record's validity window and did not persist the link,
    because owner_facts had no column for it (migration 25). Two facts with adjacent
    windows then look identical whether one replaced the other or both simply expired.
    """
    now = int(time.time() * 1000)
    await lifecycle.context.admit_fact(_fact("f-old", "cycles to work", at=now - 1000))
    await lifecycle.context.admit_fact(
        _fact("f-new", "drives to work", at=now, supersedes_fact_id="f-old")
    )

    history = await lifecycle.history(subject="OWNER", predicate="commute")
    chain = {r["fact_id"]: r for r in history["revisions"]}
    assert len(chain) == 2

    assert chain["f-new"]["supersedes_fact_id"] == "f-old"
    assert chain["f-new"]["superseded_by_fact_id"] is None
    # Read forwards, which is the direction the owner's question runs.
    assert chain["f-old"]["superseded_by_fact_id"] == "f-new"
    assert chain["f-old"]["valid_until_ms"] is not None, "the old belief must have ended"
    # A corrected fact is not a withdrawn one. Both have an end; only one was replaced,
    # and reporting a correction as a withdrawal would tell the owner VAN had dropped a
    # belief it in fact still holds in a newer form.
    assert history["withdrawn_without_replacement"] == []


@pytest.mark.asyncio
async def test_a_withdrawal_is_distinguishable_from_a_correction(lifecycle):
    """"I was wrong, it is this instead" and "forget I said that" are different acts.

    Both end a fact's validity. Only one replaces it. Collapsing them would tell the owner
    VAN still believes something about them when it has been told to stop.
    """
    now = int(time.time() * 1000)
    await lifecycle.context.admit_fact(_fact("f-withdrawn", "cycles to work", at=now - 1000))
    from van_gateway.context.authoring import OwnerFactAuthor

    await OwnerFactAuthor(lifecycle.context).forget(subject="OWNER", predicate="commute")

    history = await lifecycle.history(subject="OWNER", predicate="commute")
    assert history["withdrawn_without_replacement"] == ["f-withdrawn"]


@pytest.mark.asyncio
async def test_history_is_ordered_by_belief_not_by_insertion(lifecycle):
    """The owner asks what VAN believed *when*, not what arrived first.

    The three are admitted in an order that matches neither the belief order nor its
    reverse. My first version of this test inserted them newest-first, so row order and
    belief order agreed and the assertion held either way — a mutation replacing the ORDER
    BY with `rowid ASC` survived it. A test whose fixture makes two orderings coincide is
    not testing the ordering.
    """
    now = int(time.time() * 1000)
    await lifecycle.context.admit_fact(_fact("f-recent", "drives", at=now))
    await lifecycle.context.admit_fact(_fact("f-ancient", "walks", at=now - 90_000))
    await lifecycle.context.admit_fact(_fact("f-middle", "cycles", at=now - 45_000))

    history = await lifecycle.history(subject="OWNER", predicate="commute")
    assert [r["fact_id"] for r in history["revisions"]] == [
        "f-recent",
        "f-middle",
        "f-ancient",
    ]


@pytest.mark.asyncio
async def test_an_edge_correction_is_recorded_too(store):
    """Edges had the same hole: supersedes_edge_id was read and never stored."""
    context = OwnerContextService(store)
    now = int(time.time() * 1000)

    def edge(edge_id, to_node, **kw):
        return ContextEdgeCandidate(
            edge_id=edge_id,
            from_node="OWNER",
            predicate="works_at",
            to_node=to_node,
            authority=EpistemicState.CANONICAL_OWNER,
            source_trust=SourceTrust.OWNER_EXPLICIT,
            source_ref="owner:said-so",
            valid_from_ms=now,
            observed_at_ms=now,
            **kw,
        )

    await context.admit_edge(edge("e-old", "Acme"))
    await context.admit_edge(edge("e-new", "Globex", supersedes_edge_id="e-old"))

    row = await store.fetchone("SELECT * FROM owner_context_edges WHERE edge_id = ?", ("e-new",))
    assert context.row_to_edge(row).supersedes_edge_id == "e-old"


# ------------------------------------------------------------------ conflicts


@pytest.mark.asyncio
async def test_a_contradiction_nobody_queried_is_still_reported(lifecycle):
    """The isolation defect: CONFLICTED existed only where a requirement asked.

    resolve_requirement has always detected two same-authority facts with different
    content. Nothing enumerated them, so a contradiction sat in the graph indefinitely
    unless some command happened to need that exact subject and predicate.
    """
    now = int(time.time() * 1000)
    await lifecycle.context.admit_fact(_fact("f-a", "cycles to work", at=now))
    await lifecycle.context.admit_fact(_fact("f-b", "drives to work", at=now))

    report = await lifecycle.conflicts()
    assert report["total"] == 1
    [conflict] = report["blocking"]
    assert conflict["subject"] == "OWNER"
    assert conflict["predicate"] == "commute"
    # The values, not just the ids: an owner told only "two facts disagree" has to issue a
    # request per side to find out about what.
    assert {side["value"] for side in conflict["sides"]} == {
        "cycles to work",
        "drives to work",
    }


@pytest.mark.asyncio
async def test_agreement_is_not_a_conflict(lifecycle):
    """Two facts asserting the same thing are not a contradiction.

    Without this, the conflict report fires on every duplicated observation and the owner
    learns to ignore it — the failure mode an always-red signal always has.
    """
    now = int(time.time() * 1000)
    await lifecycle.context.admit_fact(_fact("f-a", "cycles to work", at=now))
    await lifecycle.context.admit_fact(
        _fact("f-b", "cycles to work", at=now, source_ref="owner:said-so-again")
    )
    assert (await lifecycle.conflicts())["total"] == 0


@pytest.mark.asyncio
async def test_a_superseded_fact_does_not_contradict_the_one_that_replaced_it(lifecycle):
    """Otherwise every correction the owner ever made would be reported as a conflict."""
    now = int(time.time() * 1000)
    await lifecycle.context.admit_fact(_fact("f-old", "cycles to work", at=now - 1000))
    await lifecycle.context.admit_fact(
        _fact("f-new", "drives to work", at=now, supersedes_fact_id="f-old")
    )
    assert (await lifecycle.conflicts())["total"] == 0


@pytest.mark.asyncio
async def test_an_inference_contradicting_an_inference_is_reported_separately(lifecycle):
    """Two readings, mirroring the blocking/advisory split ContextReadiness already makes.

    A default requirement excludes INFERRED, so a disagreement between two inferences will
    never block a command and would otherwise be invisible forever. It is reported, and
    reported as the different thing it is: VAN's guesses disagree, and nothing downstream
    is going to notice.
    """
    now = int(time.time() * 1000)
    inferred = {
        "authority": EpistemicState.INFERRED,
        "source_trust": SourceTrust.MODEL_DERIVED,
        "source_ref": "model:guess",
    }
    await lifecycle.context.admit_fact(_fact("f-i1", "cycles", at=now, **inferred))
    await lifecycle.context.admit_fact(_fact("f-i2", "drives", at=now, **inferred))

    report = await lifecycle.conflicts()
    assert report["blocking"] == []
    assert len(report["inferred_only"]) == 1
    assert report["total"] == 1


@pytest.mark.asyncio
async def test_van_does_not_resolve_the_owners_contradictions(lifecycle):
    """VAN reports and stops.

    Choosing between two things the owner is recorded as having said is not a retrieval
    decision, and a graph that quietly picks a winner is one that overwrites the owner with
    an inference — the failure the whole epistemic-state ladder exists to prevent.
    """
    now = int(time.time() * 1000)
    await lifecycle.context.admit_fact(_fact("f-a", "cycles to work", at=now))
    await lifecycle.context.admit_fact(_fact("f-b", "drives to work", at=now))

    report = await lifecycle.conflicts()
    assert report["resolution"] == "owner_only"
    # Both sides survive the report. A resolver would have ended one's validity.
    rows = await lifecycle.store.fetchall(
        "SELECT valid_until_ms FROM owner_facts WHERE fact_id IN ('f-a','f-b')", ()
    )
    assert [r["valid_until_ms"] for r in rows] == [None, None]


# --------------------------------------------------------------------- routes


@pytest.mark.asyncio
async def test_the_owner_routes_exist_and_belong_to_the_owner(client):
    """Reachability, and the control boundary.

    export_scope was reachable only through the internal-control runtime API. Putting the
    owner's own export behind an operator credential answers the finding for an operator
    and not for the person the data describes.
    """
    ac, app = client
    paths = ("/v1/context/export", "/v1/context/conflicts")

    # No device token: the middleware refuses before any handler runs. (The handlers also
    # check, like every neighbouring context route; that check is defence in depth and not
    # the boundary, so it is not what this asserts.)
    for path in paths:
        denied = await ac.get(path)
        assert denied.status_code == 401
        assert denied.json()["detail"] == "device_access_denied"

    # And the counterexample that matters for this finding. The defect was that the only
    # export lived behind an operator credential. A fix that is *also* reachable with one
    # would have moved the problem rather than solved it: an operator must not be able to
    # read the owner's graph by presenting the machine token.
    for path in paths:
        operator = await ac.get(path, headers={"X-Van-Internal-Token": INTERNAL})
        assert operator.status_code == 401
        assert operator.json()["detail"] == "device_access_denied"

    await _enrol(ac, app)
    export = await ac.get("/v1/context/export")
    assert export.status_code == 200
    assert set(export.json()["stores"]) == {entry.table for entry in FORGETTABLE}

    conflicts = await ac.get("/v1/context/conflicts")
    assert conflicts.status_code == 200
    assert conflicts.json()["total"] == 0

    history = await ac.get(
        "/v1/context/history", params={"subject": "OWNER", "predicate": "commute"}
    )
    assert history.status_code == 200
    assert history.json()["revisions"] == []


@pytest.mark.asyncio
async def test_reading_the_owners_own_graph_is_recorded(client):
    """An export is a bulk read of the most sensitive dataset VAN holds.

    If a device token is ever used to copy it, the audit chain is the only thing that will
    say so. The erasure route already records; the export must not be the quiet one.
    """
    ac, app = client
    await _enrol(ac, app)
    assert (await ac.get("/v1/context/export")).status_code == 200

    row = await app.state.store.fetchone(
        "SELECT capability FROM audit WHERE capability = ? ORDER BY id DESC LIMIT 1",
        ("context.export",),
    )
    assert row is not None, "a bulk read of the owner graph left no trace"


def test_the_cap_is_a_real_bound():
    """A cap of zero would make every export empty and every `truncated` true."""
    assert MAX_ROWS_PER_STORE > 0
