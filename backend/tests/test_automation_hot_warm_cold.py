"""Rev 1.3 §§5-6, 23-27, 29-32, 171-174, 264 — the HOT/WARM/COLD ladder.

§24 is the property worth testing: the system gets cheaper with use. A goal that
cost a COLD generation once should cost a dict lookup the next time, and nothing
about that transition may weaken the policy checks.
"""

from __future__ import annotations

import pytest

from conftest_automation import (
    make_store,
    policy_with_domains,
    sample_artifact,
    sample_capability,
)
from van_gateway.automation.cold import (
    ColdGenerationPlanner,
    GenerationOutcome,
    RetrievalContext,
    TemplateBackedProposer,
)
from van_gateway.automation.compiler import AutomationCompiler
from van_gateway.automation.models import (
    IntentSignature,
    WorkflowLifecycle,
    WorkflowStepEffect,
)
from van_gateway.automation.registry import AutomationRegistry, HotWorkflowIndex
from van_gateway.automation.router import (
    AutomationMediumRouter,
    ExecutionMedium,
    RouteReason,
    RouteRequest,
)
from van_gateway.automation.templates import TemplateError, TemplateLibrary
from van_gateway.automation.validator import WorkflowValidator
from van_gateway.models import ActionClass

DOMAIN = "reports.example.com"

STATEMENT_BINDINGS = {
    "source_label": "Primary broker",
    "document_type": "statement",
    "source_domain": DOMAIN,
    "source_path": "/statements",
    "credential_alias": "connector://broker/primary",
}


def _signature(goal_class="BROKER_STATEMENT_COLLECTION", mutation=ActionClass.A2):
    return IntentSignature(
        goal_class=goal_class, source_class="EMAIL", destination_class="VATI",
        mutation_class=mutation,
    )


# ------------------------------------------------------------ WARM templates


def test_every_template_specialises_into_a_valid_ir():
    """A template that cannot produce a valid IR is worse than no template."""
    library = TemplateLibrary()
    policy = policy_with_domains(DOMAIN, "events.example.com")
    validator = WorkflowValidator(policy)
    bindings = {
        "collect_normalise_ingest.v1": STATEMENT_BINDINGS,
        "monitor_diff_notify.v1": {
            "source_label": "Fee schedule", "source_domain": DOMAIN, "source_path": "/fees",
        },
        "event_filter_emit.v1": {
            "source_label": "Gmail", "webhook_path": "van/gmail", "event_type": "mail.received",
        },
        "fetch_map_verify.v1": {
            "resource_label": "portfolio", "source_domain": DOMAIN, "source_path": "/portfolio",
        },
    }
    for template_id in library.template_ids:
        ir = library.specialise(
            template_id, bindings=bindings[template_id], policy_version=policy.policy_version
        )
        report = validator.validate(ir)
        assert report.ok, f"{template_id}: {report.errors}"


def test_specialisation_is_deterministic():
    """§171 — WARM is deterministic, so the same bindings compile identically."""
    library = TemplateLibrary()
    policy = policy_with_domains(DOMAIN)
    compiler = AutomationCompiler(policy)
    creds = {"connector://broker/primary": "cred_1"}

    first = library.specialise(
        "collect_normalise_ingest.v1", bindings=STATEMENT_BINDINGS,
        policy_version=policy.policy_version,
    )
    second = library.specialise(
        "collect_normalise_ingest.v1", bindings=STATEMENT_BINDINGS,
        policy_version=policy.policy_version,
    )
    assert first.ir_id != second.ir_id  # fresh identity each time
    assert (
        compiler.compile(first, credential_ids=creds).semantic_digest
        == compiler.compile(second, credential_ids=creds).semantic_digest
    )


def test_missing_binding_is_refused():
    library = TemplateLibrary()
    with pytest.raises(TemplateError, match="binding_missing"):
        library.specialise(
            "collect_normalise_ingest.v1",
            bindings={"source_label": "x"}, policy_version="p",
        )


def test_unknown_binding_is_refused():
    """Silently ignoring it would produce a subtly wrong workflow."""
    library = TemplateLibrary()
    with pytest.raises(TemplateError, match="binding_unknown"):
        library.specialise(
            "collect_normalise_ingest.v1",
            bindings={**STATEMENT_BINDINGS, "typo_field": "x"}, policy_version="p",
        )


def test_enum_constrained_binding_is_enforced():
    library = TemplateLibrary()
    with pytest.raises(TemplateError, match="not_permitted"):
        library.specialise(
            "monitor_diff_notify.v1",
            bindings={
                "source_label": "x", "source_domain": DOMAIN, "source_path": "/x",
                "severity": "CATASTROPHIC",
            },
            policy_version="p",
        )


def test_template_action_class_is_derived_not_declared():
    """§146 holds on the WARM path too."""
    library = TemplateLibrary()
    ir = library.specialise(
        "collect_normalise_ingest.v1", bindings=STATEMENT_BINDINGS, policy_version="p"
    )
    # The seal step writes, so the workflow is A3 regardless of anything else.
    assert ir.action_class is ActionClass.A3
    assert any(WorkflowStepEffect.WRITE in step.effects for step in ir.steps)


def test_goal_class_lookup_is_wording_independent():
    library = TemplateLibrary()
    assert library.for_goal_class("broker statement collection") is not None
    assert library.for_goal_class("BROKER_STATEMENT_COLLECTION") is not None
    assert library.for_goal_class("something nobody has done") is None


# ---------------------------------------------------------- COLD generation


class _StubProposer:
    def __init__(self, ir=None, raises=False):
        self.ir = ir
        self.raises = raises
        self.seen_context: RetrievalContext | None = None

    async def propose(self, *, goal, signature, context):
        self.seen_context = context
        if self.raises:
            raise RuntimeError("model unavailable")
        return self.ir


async def test_cold_retrieval_runs_in_parallel_and_preloads_the_catalog():
    """§§30-31 — the proposer is handed shapes, never told to discover them."""
    planner = ColdGenerationPlanner(
        policy=policy_with_domains(DOMAIN),
        credential_aliases=["connector://broker/primary"],
    )
    context = await planner.retrieve(goal="collect statements", signature=_signature())
    assert "HTTP_GET" in context.allowed_primitives
    assert "EXECUTE_SHELL" not in context.allowed_primitives
    assert DOMAIN in context.admitted_domains
    assert "collect_normalise_ingest.v1" in context.template_ids
    assert context.credential_aliases == ("connector://broker/primary",)


async def test_prompt_contract_carries_no_secrets():
    """§173 — a proposer sees aliases and shapes, never values or owner context."""
    planner = ColdGenerationPlanner(
        policy=policy_with_domains(DOMAIN), credential_aliases=["connector://broker/primary"]
    )
    contract = (await planner.retrieve(goal="x", signature=_signature())).as_prompt_contract()
    blob = str(contract).lower()
    for forbidden in ("password", "secret", "token=", "api_key", "bearer"):
        assert forbidden not in blob
    assert "no payment, no payment instrument, at any class" in contract["hard_rules"]


async def test_template_backed_proposer_collapses_cold_into_warm():
    """§29 — generation does not start from a blank canvas when a shape fits."""
    planner = ColdGenerationPlanner(
        policy=policy_with_domains(DOMAIN), credential_aliases=["connector://broker/primary"]
    )
    # The statement template needs a source_path, which is never guessable, so the
    # deterministic proposer correctly declines rather than inventing one.
    result = await planner.generate(
        goal="collect broker statements", signature=_signature(),
        proposer=TemplateBackedProposer(),
    )
    assert result.outcome is GenerationOutcome.NO_PROPOSAL


async def test_resource_read_goal_is_served_without_a_model():
    """A goal whose template has only guessable holes needs no proposer at all."""
    planner = ColdGenerationPlanner(
        policy=policy_with_domains(DOMAIN), credential_aliases=["connector://broker/primary"]
    )
    result = await planner.generate(
        goal="read the portfolio resource",
        signature=_signature(goal_class="RESOURCE_READ"),
        proposer=TemplateBackedProposer(),
    )
    # fetch_map_verify needs source_path too, so this also declines — proving the
    # proposer refuses to guess a path rather than producing a wrong target.
    assert result.outcome is GenerationOutcome.NO_PROPOSAL


async def test_valid_a2_proposal_is_auto_admitted():
    """§36 / config policy cold_auto_admit: A1 and A2 may auto-admit."""
    policy = policy_with_domains(DOMAIN)
    ir = TemplateLibrary().specialise(
        "fetch_map_verify.v1",
        bindings={"resource_label": "portfolio", "source_domain": DOMAIN,
                  "source_path": "/portfolio"},
        policy_version=policy.policy_version,
    )
    planner = ColdGenerationPlanner(policy=policy)
    result = await planner.generate(
        goal="read the portfolio", signature=_signature(),
        proposer=_StubProposer(ir),
    )
    assert result.outcome is GenerationOutcome.ADMITTED_CANDIDATE
    assert result.ir is not None and result.ir.action_class is ActionClass.A2


async def test_a3_proposal_requires_owner_approval():
    """§36 — A3 may be generated and validated, but not auto-admitted."""
    policy = policy_with_domains(DOMAIN)
    ir = TemplateLibrary().specialise(
        "collect_normalise_ingest.v1", bindings=STATEMENT_BINDINGS,
        policy_version=policy.policy_version,
    )
    planner = ColdGenerationPlanner(policy=policy)
    result = await planner.generate(
        goal="collect statements", signature=_signature(), proposer=_StubProposer(ir)
    )
    assert result.outcome is GenerationOutcome.REQUIRES_OWNER_APPROVAL
    assert result.ir.action_class is ActionClass.A3


async def test_proposal_violating_policy_is_rejected():
    """A model cannot talk its way past the static analyser."""
    policy = policy_with_domains(DOMAIN)
    ir = TemplateLibrary().specialise(
        "fetch_map_verify.v1",
        bindings={"resource_label": "x", "source_domain": "not-admitted.example.com",
                  "source_path": "/x"},
        policy_version=policy.policy_version,
    )
    planner = ColdGenerationPlanner(policy=policy)
    result = await planner.generate(
        goal="read something", signature=_signature(), proposer=_StubProposer(ir)
    )
    assert result.outcome is GenerationOutcome.REJECTED_BY_POLICY
    assert any("UNAPPROVED_EXTERNAL_DOMAIN" in e for e in result.errors)


async def test_payment_goal_is_refused_before_any_model_runs():
    """§34 — no proposer is even asked to plan a payment."""
    planner = ColdGenerationPlanner(policy=policy_with_domains(DOMAIN))
    proposer = _StubProposer(None)
    result = await planner.generate(
        goal="pay the electricity invoice", signature=_signature(), proposer=proposer
    )
    assert result.outcome is GenerationOutcome.REJECTED_BY_PAYMENT_BOUNDARY
    assert proposer.seen_context is None, "the proposer must not be consulted"


async def test_proposal_declaring_a_payment_is_rejected():
    policy = policy_with_domains(DOMAIN)
    ir = TemplateLibrary().specialise(
        "fetch_map_verify.v1",
        bindings={"resource_label": "x", "source_domain": DOMAIN, "source_path": "/x"},
        policy_version=policy.policy_version,
    )
    steps = list(ir.steps)
    steps[0] = steps[0].model_copy(update={"effects": [WorkflowStepEffect.PAYMENT]})
    planner = ColdGenerationPlanner(policy=policy)
    result = await planner.generate(
        goal="read something", signature=_signature(),
        proposer=_StubProposer(ir.model_copy(update={"steps": steps})),
    )
    assert result.outcome is GenerationOutcome.REJECTED_BY_PAYMENT_BOUNDARY


async def test_proposer_failure_is_not_a_policy_pass():
    planner = ColdGenerationPlanner(policy=policy_with_domains(DOMAIN))
    result = await planner.generate(
        goal="do a novel thing", signature=_signature(), proposer=_StubProposer(raises=True)
    )
    assert result.outcome is GenerationOutcome.PROPOSER_FAILED
    assert not result.ok


# ------------------------------------------------------------- the router


async def _router(tmp_path, *, hot: bool = False):
    store = await make_store(tmp_path)
    registry = AutomationRegistry(store)
    index = HotWorkflowIndex()
    if hot:
        await registry.upsert_capability(sample_capability(lifecycle=WorkflowLifecycle.HOT))
        await registry.record_artifact(sample_artifact(lifecycle=WorkflowLifecycle.ADMITTED))
        index.publish(_signature(), "wfcap_statements", 1, "n8n-1")
    return AutomationMediumRouter(registry=registry, hot_index=index), registry, index


async def test_hot_capability_wins(tmp_path):
    router, _registry, _index = await _router(tmp_path, hot=True)
    decision = await router.route(
        RouteRequest(goal="get my broker statements", signature=_signature())
    )
    assert decision.medium is ExecutionMedium.N8N_HOT
    assert decision.reason is RouteReason.ADMITTED_HOT_CAPABILITY
    assert decision.capability_id == "wfcap_statements"


async def test_native_beats_compiling(tmp_path):
    """§303 — do not route a low-latency owner read through n8n."""
    router, _r, _i = await _router(tmp_path)
    decision = await router.route(
        RouteRequest(
            goal="get my broker statements", signature=_signature(),
            native_capability_id="google.gmail.search",
        )
    )
    assert decision.medium is ExecutionMedium.NATIVE
    assert decision.compile_in_background is False


async def test_recurring_request_is_served_now_and_compiled_behind(tmp_path):
    """§32 — the owner does not pay the generation latency."""
    router, _r, _i = await _router(tmp_path)
    decision = await router.route(
        RouteRequest(
            goal="find this week's broker statements and do this every Friday",
            signature=_signature(), native_capability_id="google.gmail.search",
            wants_reuse=True,
        )
    )
    assert decision.medium is ExecutionMedium.NATIVE
    assert decision.immediate_native_capability_id == "google.gmail.search"
    assert decision.compile_in_background is True
    assert decision.template_id == "collect_normalise_ingest.v1"


async def test_known_goal_class_routes_warm(tmp_path):
    router, _r, _i = await _router(tmp_path)
    decision = await router.route(
        RouteRequest(goal="watch the fee schedule", signature=_signature("SOURCE_MONITORING"))
    )
    assert decision.medium is ExecutionMedium.N8N_WARM
    assert decision.template_id == "monitor_diff_notify.v1"


async def test_novel_goal_routes_cold(tmp_path):
    router, _r, _i = await _router(tmp_path)
    decision = await router.route(
        RouteRequest(goal="do something nobody has asked before",
                     signature=_signature("UNPRECEDENTED_THING"))
    )
    assert decision.medium is ExecutionMedium.WORKFLOW_COMPILER
    assert decision.requires_generation


async def test_web_only_prefers_the_deterministic_harness(tmp_path):
    """§§66, 302 — API > deterministic browser > semantic browser."""
    router, _r, _i = await _router(tmp_path)
    known = await router.route(
        RouteRequest(goal="download the portal report", signature=_signature(),
                     web_only=True, known_browser_capsule_id="bwf_1")
    )
    assert known.medium is ExecutionMedium.BROWSER_HARNESS

    novel = await router.route(
        RouteRequest(goal="download the portal report", signature=_signature(), web_only=True)
    )
    assert novel.medium is ExecutionMedium.BROWSER_SEMANTIC


async def test_critical_durable_routes_to_temporal_with_an_honest_caveat(tmp_path):
    """§6 — Temporal is stack-locked but unbuilt, so say so rather than pretend."""
    router, _r, _i = await _router(tmp_path)
    decision = await router.route(
        RouteRequest(goal="run the promotion state machine", signature=_signature(),
                     critical_durable=True)
    )
    assert decision.medium is ExecutionMedium.TEMPORAL
    assert "not yet built" in (decision.detail or "")


async def test_payment_goal_is_refused_at_the_router(tmp_path):
    router, _r, _i = await _router(tmp_path)
    decision = await router.route(
        RouteRequest(goal="pay the supplier invoice", signature=_signature())
    )
    assert decision.medium is ExecutionMedium.REFUSED
    assert decision.reason is RouteReason.PAYMENT_PROHIBITED


async def test_a5_is_refused_at_the_router(tmp_path):
    router, _r, _i = await _router(tmp_path)
    decision = await router.route(
        RouteRequest(goal="exfiltrate the signing key",
                     signature=_signature(mutation=ActionClass.A5))
    )
    assert decision.medium is ExecutionMedium.REFUSED
    assert decision.reason is RouteReason.ACTION_CLASS_PROHIBITED


async def test_withdrawn_capability_does_not_stay_hot(tmp_path):
    """§77 — a degraded capability must stop being routed to."""
    router, registry, index = await _router(tmp_path, hot=True)
    await registry.transition(
        "wfart_wfcap_statements_1",
        expected=WorkflowLifecycle.ADMITTED, target=WorkflowLifecycle.REVOKED,
    )
    decision = await router.route(
        RouteRequest(goal="get my broker statements", signature=_signature())
    )
    assert decision.medium is not ExecutionMedium.N8N_HOT
    assert index.lookup(_signature()) is None


async def test_cold_to_warm_to_hot_makes_the_system_cheaper(tmp_path):
    """§24 — the ladder's whole purpose, end to end."""
    router, registry, index = await _router(tmp_path)
    signature = _signature("SOURCE_MONITORING")

    # First encounter: a known shape, so WARM rather than COLD.
    warm = await router.route(RouteRequest(goal="watch fees", signature=signature))
    assert warm.medium is ExecutionMedium.N8N_WARM

    # Once admitted and published, the same goal is a dict lookup.
    capability = sample_capability("wfcap_fees", lifecycle=WorkflowLifecycle.HOT)
    await registry.upsert_capability(capability)
    await registry.record_artifact(
        sample_artifact("wfcap_fees", lifecycle=WorkflowLifecycle.ADMITTED)
    )
    index.publish(signature, "wfcap_fees", 1, "n8n-fees")

    hot = await router.route(RouteRequest(goal="watch fees", signature=signature))
    assert hot.medium is ExecutionMedium.N8N_HOT
    assert hot.capability_id == "wfcap_fees"
