"""P0-CTX-001 and P0-CTX-002: the context kernel was real and was never asked anything.

The orchestrator sealed every snapshot with an empty requirements list, so readiness was
trivially CURRENT, `fact_ids` was always empty, and the canonical context handed to Hermes
carried a snapshot id, a digest, a Project Truth SHA and policy references — and not one
owner fact.

Underneath, the store could not have answered anyway. The only production write path was
the Hermes admission route, correctly gated to INFERRED/MODEL_DERIVED because a model must
not write canonical truth. But readiness, graph and lexical queries exclude INFERRED by
default, so the only facts production could write were the only facts retrieval refused to
read, and CANONICAL_OWNER, PROJECT_TRUTH and the VERIFIED_* tiers were empty everywhere.
"""

from __future__ import annotations

import time

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.auth.service import AuthService
from van_gateway.command import context_requirements
from van_gateway.config import get_settings
from van_gateway.context.authoring import (
    AUTHOR_TIERS,
    ContextAuthoringError,
    OwnerFactAuthor,
    ProjectTruthImporter,
)
from van_gateway.context.models import (
    ContextRequirement,
    EpistemicState,
    ReadinessState,
    SourceTrust,
)

INGRESS = "ctx-ingress-token-0123456789abcdef"


class TestRequirementsAreDerived:
    def test_a_bare_command_still_asks_something(self):
        """The empty list was the defect; one requirement is the floor, not the ceiling."""
        derived = context_requirements.derive(text="Van, brief me.", project_id=None, action_id=None)
        assert derived
        assert ("OWNER", "timezone") in {(r.subject, r.predicate) for r in derived}

    def test_a_project_command_asks_about_the_project(self):
        derived = context_requirements.derive(
            text="what changed this week", project_id="van", action_id=None
        )
        subjects = {(r.subject, r.predicate, r.scope) for r in derived}
        for predicate in context_requirements.PROJECT_PREDICATES:
            assert ("van", predicate, "project:van") in subjects

    def test_a_typed_action_inherits_its_familys_requirements(self):
        derived = context_requirements.derive(
            text="halt autonomous trading", project_id=None, action_id="trading.halt"
        )
        assert ("OWNER", "risk_posture") in {(r.subject, r.predicate) for r in derived}

    def test_an_unknown_action_family_adds_nothing_speculative(self):
        derived = context_requirements.derive(
            text="do a thing", project_id=None, action_id="unheard.of.action"
        )
        assert {(r.subject, r.predicate) for r in derived} == {("OWNER", "timezone")}

    @pytest.mark.parametrize("text", ["Remind Thandi about the deposit", "remind Thandi", "Tell Thandi I am late"])
    def test_a_named_person_becomes_a_requirement(self, text):
        derived = context_requirements.derive(text=text, project_id=None, action_id=None)
        assert ("Thandi", "contact", "people") in {
            (r.subject, r.predicate, r.scope) for r in derived
        }

    @pytest.mark.parametrize("text", ["remind me at 5pm", "remind alice", "tell the bank"])
    def test_something_that_is_not_a_name_is_not_asked_about(self, text):
        """A capital letter is the only signal separating a person from a pronoun here."""
        derived = context_requirements.derive(text=text, project_id=None, action_id=None)
        assert {r.subject for r in derived} == {"OWNER"}

    def test_requirements_are_not_asked_twice(self):
        derived = context_requirements.derive(
            text="tell Thandi and remind Thandi", project_id=None, action_id="trading.halt"
        )
        keys = [(r.subject, r.predicate, r.scope) for r in derived]
        assert len(keys) == len(set(keys))

    def test_nothing_derived_admits_an_inferred_fact(self):
        """A model's guess about the owner is not a basis for acting on their behalf."""
        derived = context_requirements.derive(
            text="Remind Thandi", project_id="van", action_id="trading.halt"
        )
        assert all(not r.allow_inferred for r in derived)

    def test_everything_derived_is_advisory(self):
        """The gates that refuse a command already exist and are stricter."""
        derived = context_requirements.derive(
            text="Remind Thandi", project_id="van", action_id="trading.halt"
        )
        assert all(not r.blocking for r in derived)

    def test_a_requirement_written_before_this_field_existed_still_blocks(self):
        """The default preserves every caller's behaviour exactly."""
        assert ContextRequirement(subject="X", predicate="y").blocking is True


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "ctx.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.invalid")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", "ctx-internal-token-0123456789abc")
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", "ctx-enrolment-token-0123456789ab")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client(monkeypatch):
    app = create_app()

    async def fake_health():
        return {"ok": True, "profile": "van"}

    async def fake_create_run(text, metadata=None):
        fake_create_run.metadata = metadata
        return {"id": "run-ctx-1", "status": "accepted"}

    monkeypatch.setattr(app.state.orchestrator.hermes, "health", fake_health)
    monkeypatch.setattr(app.state.orchestrator.hermes, "create_run", fake_create_run)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"X-Van-Ingress-Token": INGRESS}
    ) as ac:
        async with app.router.lifespan_context(app):
            yield ac, app, fake_create_run


async def _enrol(ac, app, device_id="ctx-dev"):
    ticket = await app.state.auth.create_pairing_ticket(device_id)
    enrolled = await app.state.auth.pair_device(ticket.token, device_id, "s" * 32, "PEM", device_id)
    ac.headers.update({"X-Van-Device-Token": enrolled.access_token})
    return device_id


def _signed(app, device_id, text, *, key):
    issued = int(time.time())
    cid = f"ctx-{key}"
    canonical = AuthService.canonical_command(
        command_id=cid, idempotency_key=key, device_id=device_id, issued_at_unix=issued,
        text=text, action_class="A1", project_id=None,
    )
    return {
        "command_id": cid, "idempotency_key": key, "device_id": device_id,
        "issued_at_unix": issued, "signature": app.state.auth.sign(device_id, canonical),
        "text": text, "action_class": "A1",
    }


@pytest.mark.asyncio
class TestTheSnapshotCarriesFacts:
    async def test_a_command_now_asks_and_the_snapshot_records_it(self, client):
        ac, app, hermes = client
        device_id = await _enrol(ac, app)
        await ac.post("/v1/commands", json=_signed(app, device_id, "Van, brief me.", key="k1"))

        context = hermes.metadata["canonical_context"]
        assert context["requirements_asked"] >= 1, "the snapshot asked nothing again"
        assert context["readiness"] == "MISSING", (
            "a fresh system knows nothing, and should say so rather than claim CURRENT"
        )

    async def test_an_owner_stated_fact_reaches_the_canonical_context(self, client):
        """The end to end claim: the owner says something, and a command is answered with it."""
        ac, app, hermes = client
        device_id = await _enrol(ac, app)

        stated = await ac.post(
            "/v1/context/facts",
            json={"subject": "OWNER", "predicate": "timezone", "value": "Africa/Harare"},
        )
        assert stated.status_code == 200, stated.text
        assert stated.json()["authority"] == "CANONICAL_OWNER"

        await ac.post("/v1/commands", json=_signed(app, device_id, "Van, brief me.", key="k2"))
        context = hermes.metadata["canonical_context"]
        assert context["fact_ids"], "the canonical context still carried no owner facts"
        assert context["readiness"] == "CURRENT"

    async def test_a_fact_the_owner_forgets_stops_being_current(self, client):
        ac, app, hermes = client
        device_id = await _enrol(ac, app)
        await ac.post(
            "/v1/context/facts",
            json={"subject": "OWNER", "predicate": "timezone", "value": "Africa/Harare"},
        )
        forgotten = await ac.delete(
            "/v1/context/facts", params={"subject": "OWNER", "predicate": "timezone"}
        )
        assert forgotten.json()["ended"] == 1

        await ac.post("/v1/commands", json=_signed(app, device_id, "Van, brief me.", key="k3"))
        assert hermes.metadata["canonical_context"]["readiness"] == "MISSING"

    async def test_an_unpaired_caller_cannot_state_an_owner_fact(self, client):
        ac, app, _ = client
        # No device token on the session at all.
        resp = await ac.post(
            "/v1/context/facts",
            json={"subject": "OWNER", "predicate": "timezone", "value": "UTC"},
        )
        assert resp.status_code in (401, 403)


@pytest.mark.asyncio
class TestTheAuthoritativeTiersHaveWriters:
    async def test_the_owner_writer_writes_canonical_owner_only(self, client):
        ac, app, _ = client
        device_id = await _enrol(ac, app)
        author = OwnerFactAuthor(app.state.owner_runtime.context)
        record = await author.state(
            device_id=device_id, subject="OWNER", predicate="home_city", value="Harare"
        )
        assert record.authority is EpistemicState.CANONICAL_OWNER
        assert record.source_trust is SourceTrust.OWNER_EXPLICIT
        assert record.source_ref == f"owner-device:{device_id}"

    async def test_restating_supersedes_rather_than_conflicting(self, client):
        """The owner changing their mind is not two sources disagreeing."""
        ac, app, _ = client
        device_id = await _enrol(ac, app)
        author = OwnerFactAuthor(app.state.owner_runtime.context)
        await author.state(device_id=device_id, subject="OWNER", predicate="home_city", value="Harare")
        await author.state(device_id=device_id, subject="OWNER", predicate="home_city", value="Bulawayo")

        readiness = await app.state.owner_runtime.context.readiness(
            "cmd", [ContextRequirement(subject="OWNER", predicate="home_city")]
        )
        assert readiness.state is ReadinessState.CURRENT
        assert readiness.requirements[0].fact.value == "Bulawayo"

    async def test_project_truth_imports_at_the_project_truth_tier(self, client):
        ac, app, _ = client
        importer = ProjectTruthImporter(app.state.owner_runtime.context)
        written = await importer.import_truth(
            "van",
            {"truth_sha": "sha-1", "branch": "main", "stack": "python", "nested": {"a": 1}},
        )
        assert {r.predicate for r in written} == {"branch", "stack"}, (
            "only top-level scalars; flattening would invent relationships"
        )
        assert all(r.authority is EpistemicState.PROJECT_TRUTH for r in written)
        assert all(r.source_ref == "project-truth:van:sha-1" for r in written)

    async def test_truth_without_a_sha_is_refused(self, client):
        ac, app, _ = client
        importer = ProjectTruthImporter(app.state.owner_runtime.context)
        with pytest.raises(ContextAuthoringError, match="truth_sha"):
            await importer.import_truth("van", {"branch": "main"})

    async def test_a_new_sha_supersedes_the_old_facts(self, client):
        ac, app, _ = client
        importer = ProjectTruthImporter(app.state.owner_runtime.context)
        await importer.import_truth("van", {"truth_sha": "sha-1", "branch": "main"})
        await importer.import_truth("van", {"truth_sha": "sha-2", "branch": "release"})

        readiness = await app.state.owner_runtime.context.readiness(
            "cmd",
            [ContextRequirement(subject="van", predicate="branch", scope="project:van")],
        )
        assert readiness.state is ReadinessState.CURRENT, "two SHAs left a conflict"
        assert readiness.requirements[0].fact.value == "release"

    async def test_each_author_is_bound_to_one_tier(self):
        """Not a tier parameter the caller supplies — that is the shape the audit found."""
        assert AUTHOR_TIERS["owner_device"] == (
            EpistemicState.CANONICAL_OWNER, SourceTrust.OWNER_EXPLICIT
        )
        assert AUTHOR_TIERS["hermes"] == (EpistemicState.INFERRED, SourceTrust.MODEL_DERIVED)
        assert len({tier for tier, _ in AUTHOR_TIERS.values()}) == len(AUTHOR_TIERS)

    async def test_the_tiers_retrieval_reads_are_now_writable(self, client):
        """The finding in one line: what production could write, retrieval excluded."""
        ac, app, _ = client
        device_id = await _enrol(ac, app)
        context = app.state.owner_runtime.context
        await OwnerFactAuthor(context).state(
            device_id=device_id, subject="OWNER", predicate="timezone", value="UTC"
        )
        await ProjectTruthImporter(context).import_truth(
            "van", {"truth_sha": "sha-1", "branch": "main"}
        )
        for requirement in (
            ContextRequirement(subject="OWNER", predicate="timezone"),
            ContextRequirement(subject="van", predicate="branch", scope="project:van"),
        ):
            resolution = await context.resolve_requirement(requirement)
            assert resolution.state is ReadinessState.CURRENT
            assert resolution.fact.authority is not EpistemicState.INFERRED
