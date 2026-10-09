"""Remote Git/CI proof is bound to fixed origins, exact head, workflow and attempt."""
from datetime import datetime, timezone
import json

import httpx
import pytest

from van_gateway.mission.models import SuccessContract, VerificationStatus
from van_gateway.mission.verifiers import RepositoryShaVerifier, CiRunVerifier
from van_gateway.verification.github import (GithubVerificationConfig, GithubVerificationSource,
    RepositoryHeadPostconditions, CiRunPostconditions)

SHA = "a" * 40
HEAD = {"repository": "Vanguduza/Van", "branch": "main", "commit_sha": SHA, "repository_head_matches": True}
CI = {**HEAD, "run_id": "123", "workflow_id": "789", "run_attempt": 2,
    "ci_requested_after_unix_ms": 1000, "ci_run_matches": True, "ci_completed": True, "ci_success": True}


def _run(**changes):
    return {"id": 123, "workflow_id": 789, "run_attempt": 2, "repository": {"full_name": "Vanguduza/Van"},
        "head_sha": SHA, "head_branch": "main", "status": "completed", "conclusion": "success",
        "created_at": "2026-10-06T00:00:00Z", "run_started_at": "2026-10-06T00:02:00Z",
        "updated_at": "2026-10-06T00:10:00Z", **changes}


def _source(handler, *, config=None):
    return GithubVerificationSource(config or GithubVerificationConfig(frozenset({"vanguduza/van"})), transport=httpx.MockTransport(handler))


def _ref(sha=SHA):
    return {"ref": "refs/heads/main", "object": {"type": "commit", "sha": sha}}


async def _verify_head(source, conditions=HEAD):
    return await RepositoryShaVerifier(source.repository_head).verify(SuccessContract(verifier_class="repository-sha", postconditions=conditions), {})


async def _verify_ci(source, conditions=CI):
    return await CiRunVerifier(source.ci_run).verify(SuccessContract(verifier_class="ci-run", postconditions=conditions), {})


@pytest.mark.asyncio
async def test_fresh_remote_head_and_ci_attempt_are_verified_on_fixed_read_only_origin():
    seen = []
    def handler(request):
        seen.append(request)
        assert request.method == "GET" and request.url.scheme == "https" and request.url.host == "api.github.com"
        assert "Authorization" not in request.headers
        if request.url.path.endswith("/git/ref/heads/main"):
            return httpx.Response(200, json=_ref())
        assert request.url.path.endswith("/actions/runs/123/attempts/2")
        return httpx.Response(200, json=_run())
    source = _source(handler)
    head = await _verify_head(source)
    ci = await _verify_ci(source)
    assert head.status is VerificationStatus.VERIFIED and ci.status is VerificationStatus.VERIFIED
    assert head.evidence_refs == [f"https://github.com/Vanguduza/Van/commit/{SHA}"]
    assert ci.evidence_refs == ["https://github.com/Vanguduza/Van/actions/runs/123/attempts/2"]
    assert len(seen) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [{"head_sha": "b" * 40}, {"head_branch": "other"}, {"workflow_id": 1},
    {"id": 124}, {"run_attempt": 3}, {"repository": {"full_name": "attacker/Van"}}, {"conclusion": "failure"},
    {"status": "in_progress"}, {"run_attempt": True}, {"run_started_at": "2020-01-01T00:00:00Z"}])
async def test_wrong_head_workflow_attempt_repo_or_outcome_cannot_certify_ci(change):
    def handler(request):
        return httpx.Response(200, json=_ref() if "/git/ref/" in request.url.path else _run(**change))
    outcome = await _verify_ci(_source(handler))
    assert outcome.status is VerificationStatus.FAILED


@pytest.mark.asyncio
async def test_remote_branch_movement_refuses_ci_even_when_old_exact_run_is_green():
    def handler(request):
        return httpx.Response(200, json=_ref("b" * 40) if "/git/ref/" in request.url.path else _run())
    outcome = await _verify_ci(_source(handler))
    assert outcome.status is VerificationStatus.FAILED and "repository_head_matches" in outcome.missing_postconditions


@pytest.mark.asyncio
async def test_run_must_start_after_the_owner_contract_not_merely_be_green():
    requested = int(datetime(2026, 10, 6, 0, 5, tzinfo=timezone.utc).timestamp() * 1000)
    def handler(request):
        return httpx.Response(200, json=_ref() if "/git/ref/" in request.url.path else _run())
    outcome = await _verify_ci(_source(handler), {**CI, "ci_requested_after_unix_ms": requested})
    assert outcome.status is VerificationStatus.FAILED and "ci_run_matches" in outcome.missing_postconditions


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [httpx.Response(302, headers={"location": "https://attacker.test/secret"}),
    httpx.Response(503), httpx.Response(200, text="bad JSON"), httpx.Response(200, json=[]),
    httpx.Response(200, content=b"x" * (512 * 1024 + 1))])
async def test_redirect_error_malformed_and_oversized_provider_responses_are_unverifiable(response):
    seen = []
    def handler(request):
        seen.append(request)
        return response
    outcome = await _verify_head(_source(handler))
    assert outcome.status is VerificationStatus.UNVERIFIABLE and len(seen) == 1


@pytest.mark.asyncio
async def test_unconfigured_or_nonallowlisted_repo_performs_no_request():
    def forbidden(request):
        raise AssertionError("unconfigured repository reached network")
    outcome = await _verify_head(_source(forbidden, config=GithubVerificationConfig()))
    assert outcome.status is VerificationStatus.UNVERIFIABLE
    outcome = await _verify_head(_source(forbidden), {**HEAD, "repository": "attacker/repo"})
    assert outcome.status is VerificationStatus.UNVERIFIABLE


@pytest.mark.asyncio
async def test_file_bound_credential_is_rotated_and_never_returned_on_echo(tmp_path):
    credential = tmp_path / "github-read.token"
    credential.write_text("g" * 40)
    credential.chmod(0o600)
    seen = []
    def handler(request):
        seen.append(request.headers["Authorization"])
        return httpx.Response(200, json=_ref())
    source = _source(handler, config=GithubVerificationConfig(frozenset({"vanguduza/van"}), str(credential)))
    assert (await _verify_head(source)).status is VerificationStatus.VERIFIED
    credential.write_text("h" * 40)
    assert (await _verify_head(source)).status is VerificationStatus.VERIFIED
    assert seen == ["Bearer " + "g" * 40, "Bearer " + "h" * 40]
    source.transport = httpx.MockTransport(lambda request: httpx.Response(200, json={**_ref(), "echo": "h" * 40}))
    outcome = await _verify_head(source)
    assert outcome.status is VerificationStatus.UNVERIFIABLE and "h" * 40 not in outcome.model_dump_json()
    credential.chmod(0o644)
    assert (await _verify_head(source)).status is VerificationStatus.UNVERIFIABLE


@pytest.mark.parametrize("conditions", [{**HEAD, "commit_sha": "short"}, {**HEAD, "branch": "../main"},
    {**HEAD, "repository": "https://attacker.test/repo"}, {**HEAD, "extra": "ignored?"}, {**HEAD, "repository_head_matches": False}])
def test_remote_contract_schema_requires_immutable_exact_bounded_identities(conditions):
    with pytest.raises(ValueError):
        RepositoryHeadPostconditions.model_validate(conditions)


@pytest.mark.parametrize("change", [{"run_attempt": True}, {"run_id": "latest"}, {"workflow_id": 789},
    {"ci_requested_after_unix_ms": "0"}, {"ci_success": False}])
def test_ci_contract_schema_rejects_implicit_or_nonexact_proof(change):
    with pytest.raises(ValueError):
        CiRunPostconditions.model_validate({**CI, **change})


@pytest.mark.asyncio
async def test_production_registry_uses_real_source_only_when_allowlist_is_bound():
    from van_gateway.verification.production import build_mission_registry
    from van_gateway.mission.verifiers import UnobservableStrategyVerifier
    source = _source(lambda request: httpx.Response(200, json=_ref()))
    registry = build_mission_registry(store=object(), trading=None, knowledge=None, github=source)
    outcome = await registry.verify(strategy="repository-sha", contract=SuccessContract(postconditions=HEAD), context={})
    assert outcome.status is VerificationStatus.VERIFIED and outcome.verifier_version == "repository-sha/1"
    source = _source(lambda request: (_ for _ in ()).throw(AssertionError("network")), config=GithubVerificationConfig())
    registry = build_mission_registry(store=object(), trading=None, knowledge=None, github=source)
    outcome = await registry.verify(strategy="repository-sha", contract=SuccessContract(postconditions=HEAD), context={})
    assert outcome.status is VerificationStatus.UNVERIFIABLE and outcome.verifier_version == "unobservable/repository-sha/1"


@pytest.mark.asyncio
@pytest.mark.parametrize("observed", ["true", "false", 1, None])
async def test_generic_verifier_does_not_promote_truthy_untyped_booleans(observed):
    from van_gateway.mission.verifiers import ObservationVerifier
    async def source(context):
        return {"completed": observed, "evidence_ref": "provider://real"}
    outcome = await ObservationVerifier(source, verifier_version="test", evidence_prefix="provider://").verify(
        SuccessContract(postconditions={"completed": True}), {})
    assert outcome.status is VerificationStatus.FAILED


@pytest.mark.asyncio
@pytest.mark.parametrize("observed", [True, float("nan"), float("inf"), "5"])
async def test_generic_verifier_requires_finite_typed_numeric_evidence(observed):
    from van_gateway.mission.verifiers import ObservationVerifier
    async def source(context):
        return {"minimum_sources": observed, "evidence_ref": "provider://real"}
    outcome = await ObservationVerifier(source, verifier_version="test", evidence_prefix="provider://").verify(
        SuccessContract(postconditions={"minimum_sources": 1}), {})
    assert outcome.status is VerificationStatus.FAILED
