"""Provider invokers for shadow cognition (GAP-F-004).

GAP-F-004 recorded the exact shape of the defect: `ShadowCognitionRuntime` has
an `invoker` parameter, `cognition/providers.py` has a four-rung hierarchy, and
nothing in production ever constructed either — so the whole cognition package
abstained `MODEL_UNAVAILABLE` forever while the owner read model advertised a
model hierarchy. The missing piece was an *injection point*, not an algorithm.

This module is that injection point, and it is deliberately narrow.

Three invokers, one interface
-----------------------------
An invoker is `(ProviderLease, context_mapping) -> raw_mapping`. It returns raw
data; it never returns a `CognitiveAssessment`. Normalisation and refusal stay
in `cognition/contracts.py`, which is the single place the closed vocabulary,
the reduce-only multiplier and the order-field refusal are enforced
(INV-AUTH-001, INV-EXEC-001). An invoker that tried to build the assessment
itself would be a second gate, and two gates means one of them is wrong.

* `NullInvoker` — refuses every call with an explicit `MODEL_UNAVAILABLE`.
  It exists so "no model" is an object with a reason rather than a `None` that
  different call sites interpret differently.
* `HttpJsonInvoker` — one POST, one strict JSON envelope, timeout, **no
  retries**. A retry against a decision point whose market state has already
  moved is a different question being asked with the old context, and the
  budget accounting (096) would be wrong about what was spent.
* `HermesRunInvoker` — the same contract carried over the Hermes run API,
  shaped like `backend/van_gateway/hermes/bridge.py`. Hermes is evidence, never
  authority: its reply is parsed as *only* a CognitiveAssessment JSON object and
  anything else — prose, a fence, a second object, a field the contract does not
  know — is refused rather than salvaged.

Fail-closed, everywhere
-----------------------
Every failure path raises. `ShadowCognitionRuntime._invoke` catches, excludes
that model, tries the next rung, and finally records a sealed abstention. So a
broken endpoint, a wrong credential, an HTML error page or a chatty model all
produce the same observable outcome as having no invoker at all: the
deterministic RiskAuthority decision stands untouched (INV-FAIL-001).

Credentials
-----------
Resolved the way broker tokens already are — a *reference* to a 0600 secrets
file or an environment variable, never a value in configuration. `secretref://`
handles resolve under the service's secrets directory, which is the same
mechanism `vati_secrets_dir` names on the gateway side. The resolved value is
used to build one Authorization header and is never logged, never returned and
never placed in a ledger payload.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Protocol

from vati.cognition.contracts import CONTRACT_VERSION, AssessmentRejected
from vati.cognition.providers import ProviderLease

#: The request envelope this repository speaks. A responder that echoes a
#: different version is answering a contract we did not ask about.
REQUEST_VERSION = "cognitive-assessment-request/5.1.0"

#: Invoker modes. Closed by construction: an unknown mode is a configuration
#: error, never a silent fall back to "none" (a silently disabled invoker is
#: indistinguishable from a working one in the read model).
INVOKER_MODES = ("none", "http_json", "hermes_run")

#: Said in the read model when no invoker is configured. GAP-F-004's acceptance
#: criterion is that the abstention is stated explicitly rather than dressed up
#: as an active shadow mode.
UNCONFIGURED_STATE = "MODEL_INVOKER_UNCONFIGURED"

#: Hard ceiling on a response body. A model endpoint that wants to send more
#: than this is not sending an assessment.
MAX_RESPONSE_BYTES = 256 * 1024

DEFAULT_TIMEOUT_S = 20.0


class CognitionConfigError(ValueError):
    """The cognition configuration cannot be honoured, so nothing is built."""


class InvokerRefused(RuntimeError):
    """This invocation produced nothing usable. The caller falls back.

    Carries a code so the runtime's handoff record says *why* a rung was left,
    which is the difference between "the provider was down" and "the provider
    answered something we refuse to read".
    """

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


# --------------------------------------------------------------- configuration
@dataclass(frozen=True)
class CognitionConfig:
    """Per-account cognition wiring. `none` is the default and changes nothing.

    GAP-F-004's acceptance criterion in both directions: with an invoker
    configured `wake()` records a real assessment; without one the read model
    states the abstention. Neither changes the RiskAuthority decision.
    """

    invoker: str = "none"
    endpoint: str = ""
    credential_ref: str = ""
    model_id: str = ""
    timeout_s: float = DEFAULT_TIMEOUT_S
    #: Where `secretref://` handles resolve. Mirrors the gateway's
    #: `vati_secrets_dir`; empty means only `env://` references are usable.
    secrets_dir: str = ""
    #: Bounded research the runtime may commission per wake (item 6). Zero
    #: disables it; research is never opened without an explicit budget.
    research_budget_micros: int = 0
    research_roles: tuple[str, ...] = ("evidence", "contradiction")
    #: Where a research agent's request goes. For `hermes_run` this defaults to
    #: the same run API `endpoint` names, because a run is a run and only the
    #: prompt differs. For `http_json` it must be given explicitly: a research
    #: request and an assessment request are different questions, and posting
    #: one to the other's responder is how a system starts answering the wrong
    #: one. Empty (with `http_json`) means no research invoker is built at all.
    research_endpoint: str = ""

    def __post_init__(self) -> None:
        if self.invoker not in INVOKER_MODES:
            raise CognitionConfigError(
                f"unknown cognition invoker {self.invoker!r}; "
                f"expected one of {', '.join(INVOKER_MODES)}")
        if self.invoker != "none" and not self.endpoint:
            raise CognitionConfigError(
                f"cognition invoker {self.invoker!r} requires an endpoint")
        if self.timeout_s <= 0:
            raise CognitionConfigError(f"cognition timeout_s {self.timeout_s} is not positive")
        if self.research_budget_micros < 0:
            raise CognitionConfigError("research budget cannot be negative")

    @classmethod
    def from_mapping(cls, m: Optional[Mapping[str, Any]], *,
                     secrets_dir: str = "") -> "CognitionConfig":
        """Build from the session config block, refusing anything unrecognised.

        A silently ignored key is an operator believing cognition is wired when
        it is not — the same failure GAP-F-004 records, one layer up.
        """
        data = dict(m or {})
        known = set(cls.__dataclass_fields__)
        unknown = sorted(set(data) - known)
        if unknown:
            raise CognitionConfigError(
                f"unknown cognition config fields: {', '.join(unknown)}")
        kwargs: dict[str, Any] = {}
        for key in ("invoker", "endpoint", "credential_ref", "model_id", "secrets_dir",
                    "research_endpoint"):
            if key in data and data[key] is not None:
                kwargs[key] = str(data[key])
        if "timeout_s" in data and data["timeout_s"] is not None:
            kwargs["timeout_s"] = float(data["timeout_s"])
        if "research_budget_micros" in data and data["research_budget_micros"] is not None:
            kwargs["research_budget_micros"] = int(data["research_budget_micros"])
        if "research_roles" in data and data["research_roles"] is not None:
            kwargs["research_roles"] = tuple(str(r) for r in data["research_roles"])
        kwargs.setdefault("secrets_dir", secrets_dir)
        return cls(**kwargs)

    @property
    def configured(self) -> bool:
        return self.invoker != "none"

    def read_model(self) -> dict[str, Any]:
        """What the owner surface says about this wiring. No secret material."""
        return {
            "cognition_invoker": self.invoker,
            "endpoint_configured": bool(self.endpoint),
            "credential_configured": bool(self.credential_ref),
            "model_id": self.model_id or None,
            "timeout_s": self.timeout_s,
            "state": "CONFIGURED" if self.configured else UNCONFIGURED_STATE,
            "research_budget_micros": self.research_budget_micros,
            "research_configured": bool(
                self.configured and self.research_budget_micros > 0
                and (self.research_endpoint or self.invoker == "hermes_run")),
        }


def resolve_credential(ref: str, *, secrets_dir: str = "") -> str:
    """Resolve a credential *reference* to its value, or refuse.

    Accepted forms, all of which keep the secret out of configuration and out
    of the ledger — the same rule `AccountRegistry.credentials` applies to
    broker tokens:

      ``env://NAME``                     an environment variable
      ``secretref://<path>#<KEY>``       ``<secrets_dir>/<path>``, KEY=VALUE line
      ``file://<path>#<KEY>``            an explicit 0600 secrets file

    An empty reference resolves to an empty string: an endpoint that needs no
    credential is legitimate, and inventing one would be worse.
    """
    ref = (ref or "").strip()
    if not ref:
        return ""
    if "://" not in ref:
        raise CognitionConfigError(
            f"credential_ref {ref!r} is not a reference; credentials are never "
            "written into configuration (use env://, secretref:// or file://)")
    scheme, rest = ref.split("://", 1)
    scheme = scheme.lower()
    if scheme == "env":
        value = os.environ.get(rest, "")
        if not value:
            raise CognitionConfigError(f"environment variable {rest} is not set")
        return value
    if scheme not in ("secretref", "file"):
        raise CognitionConfigError(f"unsupported credential scheme {scheme!r}")

    path_part, _, key = rest.partition("#")
    key = key or "TOKEN"
    if scheme == "secretref":
        if not secrets_dir:
            raise CognitionConfigError(
                "secretref:// needs a secrets directory; none is configured")
        path = Path(secrets_dir) / path_part
    else:
        path = Path(path_part)

    from vati.accounts.registry import AccountRegistryError, load_secret_file

    try:
        secrets = load_secret_file(str(path))
    except AccountRegistryError as exc:
        raise CognitionConfigError(str(exc)) from exc
    value = secrets.get(key, "")
    if not value:
        raise CognitionConfigError(f"{path} has no value for {key}")
    return value


# ------------------------------------------------------------------ transports
class HttpTransport(Protocol):
    """One request, one response. Small on purpose so tests can substitute it."""

    def __call__(self, *, url: str, headers: Mapping[str, str], body: bytes,
                 timeout_s: float) -> tuple[int, bytes]:
        ...


class HttpxTransport:
    """The production transport: httpx, one attempt, no redirects, no retries."""

    def __init__(self, *, verify: bool = True) -> None:
        self._verify = verify
        self.calls = 0

    def __call__(self, *, url: str, headers: Mapping[str, str], body: bytes,
                 timeout_s: float) -> tuple[int, bytes]:
        import httpx

        self.calls += 1
        try:
            # transport=... with retries=0 is the default; stated here because
            # "no retries" is a contract of this module, not an accident.
            with httpx.Client(timeout=timeout_s, verify=self._verify,
                              follow_redirects=False,
                              transport=httpx.HTTPTransport(retries=0)) as client:
                resp = client.post(url, headers=dict(headers), content=body)
                return resp.status_code, resp.content[:MAX_RESPONSE_BYTES + 1]
        except httpx.HTTPError as exc:
            raise InvokerRefused("TRANSPORT_ERROR", f"{type(exc).__name__}: {exc}"[:200]) from exc


def _decode_json_object(raw: bytes, *, code: str) -> dict[str, Any]:
    if len(raw) > MAX_RESPONSE_BYTES:
        raise InvokerRefused(code, f"response exceeds {MAX_RESPONSE_BYTES} bytes")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvokerRefused(code, f"response is not JSON: {exc}"[:200]) from exc
    if not isinstance(parsed, dict):
        raise InvokerRefused(code, f"response is a {type(parsed).__name__}, not an object")
    return parsed


# -------------------------------------------------------------------- invokers
class NullInvoker:
    """Refuses every invocation with an explicit MODEL_UNAVAILABLE.

    The runtime's own `invoker is None` branch produces the same sealed
    abstention without consuming a provider lease, so production passes `None`.
    This exists for the call sites that need an invoker *object* and must not
    get a silently permissive one.
    """

    mode = "none"

    def __call__(self, lease: ProviderLease, context: Mapping[str, Any]) -> Mapping[str, Any]:
        raise InvokerRefused(
            "MODEL_UNAVAILABLE",
            f"no model invoker is configured; {lease.model_id} was not called")


@dataclass
class HttpJsonInvoker:
    """POST one sealed context, receive one CognitiveAssessment envelope.

    The request/response contract is strict in both directions:

    request  ``{"contract_version", "request_version", "model_id", "role",
                "context_hash", "context"}``
    response ``{"contract_version": "cognitive-assessment/5.1.0",
                "assessment": {...}}``

    The assessment body is handed to `contracts.normalise` untouched, which is
    where a verdict outside the vocabulary, a multiplier above 1 or any order
    field is refused. This class refuses only what normalisation cannot see: a
    non-200, a non-JSON body, a wrong contract version, a missing envelope.
    """

    endpoint: str
    transport: HttpTransport
    credential: str = ""
    model_id_override: str = ""
    timeout_s: float = DEFAULT_TIMEOUT_S
    mode: str = field(default="http_json", init=False)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Vati-Cognition": REQUEST_VERSION,
        }
        if self.credential:
            headers["Authorization"] = f"Bearer {self.credential}"
        return headers

    def __call__(self, lease: ProviderLease, context: Mapping[str, Any]) -> Mapping[str, Any]:
        payload = {
            "request_version": REQUEST_VERSION,
            "contract_version": CONTRACT_VERSION,
            "model_id": self.model_id_override or lease.model_id,
            "role": lease.role.value,
            "control_profile": lease.control_profile,
            "context_hash": str(context.get("context_hash", "")),
            "deadline_ms": lease.deadline_ms,
            "context": {k: v for k, v in context.items() if k != "context_hash"},
        }
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        status, raw = self.transport(
            url=self.endpoint, headers=self._headers(), body=body,
            timeout_s=self.timeout_s)
        if status != 200:
            raise InvokerRefused("HTTP_STATUS", f"endpoint answered HTTP {status}")
        envelope = _decode_json_object(raw, code="RESPONSE_MALFORMED")
        version = str(envelope.get("contract_version", ""))
        if version != CONTRACT_VERSION:
            raise InvokerRefused(
                "CONTRACT_VERSION",
                f"response declares {version!r}, this runtime speaks {CONTRACT_VERSION!r}")
        assessment = envelope.get("assessment")
        if not isinstance(assessment, dict):
            raise InvokerRefused(
                "ENVELOPE_MALFORMED", "response carries no `assessment` object")
        return assessment


#: What Hermes is asked for. It names the vocabulary, forbids order fields and
#: forbids prose, because the parser refuses anything else and a model that was
#: not told the rule will be refused for following a different one.
HERMES_PROMPT_TEMPLATE = """\
You are answering a VATI trading decision point as SHADOW cognition.

The deterministic Risk Authority has ALREADY decided this trade. Your answer is
measured against that decision and cannot change it. You do not size, route or
place anything.

Reply with EXACTLY ONE JSON object and nothing else: no prose, no explanation
before or after, no markdown fence.

The object must have exactly these keys:
  "verdict"        one of {verdicts}
  "reason_codes"   array of codes from {reasons}
                   (required for every verdict except CONCUR)
  "risk_multiplier" decimal string in [0, 1]; "1" leaves size alone. A value
                   above 1 is a contract breach and will be refused.
  "confidence"     decimal string in [0, 1]
  "narrative"      one short owner-readable sentence
  "horizon_ms"     integer milliseconds this assessment claims to be valid for

Any of "approved_size", "lots", "stake", "order", "stop", "entry", "venue",
"account_alias" or "mandate" present in your object will cause it to be
refused: an assessment that carries order fields is trying to be an order.

Optional Jev System-1 support:
- If the Hermes runtime exposes the `dial_jev` MCP server, you MAY call
  `jev_registered_batch` during this active cognition run with project_id `van`
  and only registered `van.trading.*` modules.
- Jev is subordinate evidence only. Use it in the reasoning result only when the
  returned registered judgment has apply_effect=true; SHADOW/ADVISORY output is
  comparison evidence only. It cannot create this CognitiveAssessment, alter
  risk_multiplier, size, route, stop, mandate or execution.
- If Jev is unavailable, disabled, unqualified, abstains, or conflicts with your
  reasoning, continue normally and increase uncertainty rather than inventing a
  Jev answer. Never call Jev as an independent/background trading loop.
- A Jev conflict may support REDUCE/ABSTAIN/PROPOSE_RESEARCH, but must never be
  used to justify raising risk above the deterministic decision.

Decision context (sealed, hash {context_hash}):
{context_json}
"""


@dataclass
class HermesRunInvoker:
    """Ask Hermes profile `van` for one CognitiveAssessment JSON object.

    Shaped like `backend/van_gateway/hermes/bridge.py`: `POST {base}/p/van/v1/runs`
    with `{"profile", "input", "metadata"}` and a bearer token. Hermes output is
    evidence or a proposal and never authority, so the reply is read under the
    narrowest possible rule — the text must be exactly one JSON object — and
    everything else is refused. There is no repair pass, no fence stripping and
    no "take the last JSON-looking thing": each of those turns a model that
    ignored the contract into one that appears to have followed it.
    """

    base_url: str
    transport: HttpTransport
    credential: str = ""
    profile: str = "van"
    model_id_override: str = ""
    timeout_s: float = DEFAULT_TIMEOUT_S
    mode: str = field(default="hermes_run", init=False)

    #: Where a run response may carry its text. Checked in order; the first
    #: present string wins. A response with none of them is refused.
    TEXT_KEYS = ("output_text", "output", "text", "result", "content")

    def _url(self) -> str:
        return f"{self.base_url.rstrip('/')}/p/{self.profile}/v1/runs"

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Hermes-Profile": self.profile,
        }
        if self.credential:
            headers["Authorization"] = f"Bearer {self.credential}"
        return headers

    def prompt_for(self, context: Mapping[str, Any]) -> str:
        from vati.cognition.contracts import REASON_VOCABULARY, Verdict

        body = {k: v for k, v in context.items() if k != "context_hash"}
        return HERMES_PROMPT_TEMPLATE.format(
            verdicts=", ".join(v.value for v in Verdict),
            reasons=", ".join(sorted(REASON_VOCABULARY)),
            context_hash=str(context.get("context_hash", "")),
            context_json=json.dumps(body, sort_keys=True, indent=2, default=str)[:20_000],
        )

    def __call__(self, lease: ProviderLease, context: Mapping[str, Any]) -> Mapping[str, Any]:
        payload = {
            "profile": self.profile,
            "input": self.prompt_for(context),
            "metadata": {
                "purpose": "vati-shadow-cognition",
                "contract_version": CONTRACT_VERSION,
                "context_hash": str(context.get("context_hash", "")),
                "model_id": self.model_id_override or lease.model_id,
                "role": lease.role.value,
                "authority": "EVIDENCE_ONLY_NEVER_AN_ORDER",
            },
        }
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        status, raw = self.transport(
            url=self._url(), headers=self._headers(), body=body,
            timeout_s=self.timeout_s)
        if status != 200:
            raise InvokerRefused("HTTP_STATUS", f"Hermes answered HTTP {status}")
        run = _decode_json_object(raw, code="RESPONSE_MALFORMED")
        text = next(
            (run[k] for k in self.TEXT_KEYS
             if isinstance(run.get(k), str) and run[k].strip()),
            None,
        )
        if text is None:
            raise InvokerRefused(
                "NO_RUN_OUTPUT",
                f"run response carries no text under {', '.join(self.TEXT_KEYS)}")
        stripped = text.strip()
        if not (stripped.startswith("{") and stripped.endswith("}")):
            raise InvokerRefused(
                "NOT_ONLY_JSON",
                "Hermes replied with something other than a single JSON object")
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise InvokerRefused("NOT_ONLY_JSON", f"unparseable JSON: {exc}"[:200]) from exc
        if not isinstance(parsed, dict):
            raise InvokerRefused("NOT_ONLY_JSON", "Hermes replied with a JSON non-object")
        return parsed


#: The research request envelope. Distinct from the assessment envelope on
#: purpose: a responder must be able to tell the two questions apart.
RESEARCH_REQUEST_VERSION = "research-packet-request/5.1.0"
RESEARCH_CONTRACT_VERSION = "research-packet/5.1.0"

#: What a research agent is asked for. Every field the packet contract requires
#: is named, because `ResearchAgentFactory.run` refuses a result that is missing
#: claims, source ids, evidence refs or methods — and refusing is the right
#: outcome for an answer with no provenance, not something to paper over.
RESEARCH_PROMPT_TEMPLATE = """\
You are a bounded VATI research specialist in the role "{role}".

You produce EVIDENCE, never a decision. Nothing you return can size, route,
approve, open, close or modify a position. The deterministic Risk Authority has
already decided and your answer cannot change it.

Mission question:
{question}

Reply with EXACTLY ONE JSON object and nothing else: no prose, no markdown
fence. The object must have exactly these keys:
  "claims"                  array of short factual statements
  "source_ids"              array of source identifiers, one per source used
  "retrieval_timestamps_ms" array of integers, one per entry in source_ids
  "evidence_refs"           array of evidence references supporting the claims
  "methods"                 array naming how each claim was established
  "counterevidence"         array of findings that argue against the claims
  "limitations"             array of what this research could not establish
  "confidence"              one short word

An empty "claims", "source_ids", "evidence_refs" or "methods" will be refused:
a claim without provenance is not research.

Allowed data domains: {domains}
Allowed tools: {tools}
"""


def _research_payload_context(mission, spec) -> dict[str, Any]:
    return {
        "mission_id": mission.mission_id,
        "mission_seal": mission.seal,
        "question": mission.hypothesis,
        "prohibited_live_actions": list(mission.prohibited_live_actions),
        "output_schema": mission.output_schema,
        "role": spec.role,
        "allowed_tools": list(spec.allowed_tools),
        "allowed_data_domains": list(spec.allowed_data_domains),
        "max_tokens": spec.max_tokens,
        "max_runtime_ms": spec.max_runtime_ms,
        "source_policy": spec.source_policy,
        "authority": "EVIDENCE_ONLY_NEVER_AN_ORDER",
    }


@dataclass
class HttpJsonResearchInvoker:
    """POST one bounded research mission, receive one research packet body.

    Same rules as `HttpJsonInvoker`: one attempt, no retries, strict envelope.
    The body is handed to `ResearchAgentFactory.run` untouched, which is the
    single place the provenance requirement is enforced.
    """

    endpoint: str
    transport: HttpTransport
    credential: str = ""
    model_id_override: str = ""
    timeout_s: float = DEFAULT_TIMEOUT_S
    mode: str = field(default="http_json", init=False)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Vati-Research": RESEARCH_REQUEST_VERSION,
        }
        if self.credential:
            headers["Authorization"] = f"Bearer {self.credential}"
        return headers

    def __call__(self, lease: ProviderLease, mission, spec) -> Mapping[str, Any]:
        payload = {
            "request_version": RESEARCH_REQUEST_VERSION,
            "contract_version": RESEARCH_CONTRACT_VERSION,
            "model_id": self.model_id_override or lease.model_id,
            "deadline_ms": lease.deadline_ms,
            "mission": _research_payload_context(mission, spec),
        }
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        status, raw = self.transport(
            url=self.endpoint, headers=self._headers(), body=body,
            timeout_s=self.timeout_s)
        if status != 200:
            raise InvokerRefused("HTTP_STATUS", f"endpoint answered HTTP {status}")
        envelope = _decode_json_object(raw, code="RESPONSE_MALFORMED")
        version = str(envelope.get("contract_version", ""))
        if version != RESEARCH_CONTRACT_VERSION:
            raise InvokerRefused(
                "CONTRACT_VERSION",
                f"response declares {version!r}, this runtime speaks "
                f"{RESEARCH_CONTRACT_VERSION!r}")
        packet = envelope.get("packet")
        if not isinstance(packet, dict):
            raise InvokerRefused(
                "ENVELOPE_MALFORMED", "response carries no `packet` object")
        return packet


@dataclass
class HermesResearchInvoker:
    """Ask Hermes for one research packet body, under the same one-object rule.

    Hermes is evidence, never authority, so the reply is read exactly as
    `HermesRunInvoker` reads an assessment: the text must be one JSON object,
    with no repair pass and no fence stripping.
    """

    base_url: str
    transport: HttpTransport
    credential: str = ""
    profile: str = "van"
    model_id_override: str = ""
    timeout_s: float = DEFAULT_TIMEOUT_S
    mode: str = field(default="hermes_run", init=False)

    def prompt_for(self, mission, spec) -> str:
        return RESEARCH_PROMPT_TEMPLATE.format(
            role=spec.role,
            question=mission.hypothesis,
            domains=", ".join(spec.allowed_data_domains),
            tools=", ".join(spec.allowed_tools),
        )

    def __call__(self, lease: ProviderLease, mission, spec) -> Mapping[str, Any]:
        runner = HermesRunInvoker(
            base_url=self.base_url, transport=self.transport,
            credential=self.credential, profile=self.profile,
            model_id_override=self.model_id_override, timeout_s=self.timeout_s)
        payload = {
            "profile": self.profile,
            "input": self.prompt_for(mission, spec),
            "metadata": {
                "purpose": "vati-bounded-research",
                "contract_version": RESEARCH_CONTRACT_VERSION,
                "mission_seal": mission.seal,
                "model_id": self.model_id_override or lease.model_id,
                "role": spec.role,
                "authority": "EVIDENCE_ONLY_NEVER_AN_ORDER",
            },
        }
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        status, raw = self.transport(
            url=runner._url(), headers=runner._headers(), body=body,
            timeout_s=self.timeout_s)
        if status != 200:
            raise InvokerRefused("HTTP_STATUS", f"Hermes answered HTTP {status}")
        run = _decode_json_object(raw, code="RESPONSE_MALFORMED")
        text = next(
            (run[k] for k in runner.TEXT_KEYS
             if isinstance(run.get(k), str) and run[k].strip()),
            None,
        )
        if text is None:
            raise InvokerRefused(
                "NO_RUN_OUTPUT",
                f"run response carries no text under {', '.join(runner.TEXT_KEYS)}")
        stripped = text.strip()
        if not (stripped.startswith("{") and stripped.endswith("}")):
            raise InvokerRefused(
                "NOT_ONLY_JSON",
                "Hermes replied with something other than a single JSON object")
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise InvokerRefused("NOT_ONLY_JSON", f"unparseable JSON: {exc}"[:200]) from exc
        if not isinstance(parsed, dict):
            raise InvokerRefused("NOT_ONLY_JSON", "Hermes replied with a JSON non-object")
        return parsed


InvokeFn = Callable[[ProviderLease, Mapping[str, Any]], Mapping[str, Any]]


def build_research_invoker(cfg: CognitionConfig, *,
                           transport: Optional[HttpTransport] = None):
    """Construct the research invoker, or `None` when research is not opened.

    Three conditions, all required: an invoker is configured at all, a positive
    research budget was granted, and there is somewhere to send the request.
    `ShadowCognitionRuntime.run_research` returns nothing when this is None, so
    an unconfigured deployment commissions no research and records none —
    rather than recording a synthesised packet, which would be a fabricated
    finding in an evidence ledger (INV-EVID-001).
    """
    if not cfg.configured or cfg.research_budget_micros <= 0:
        return None
    credential = resolve_credential(cfg.credential_ref, secrets_dir=cfg.secrets_dir)
    http = transport if transport is not None else HttpxTransport()
    if cfg.invoker == "hermes_run":
        return HermesResearchInvoker(
            base_url=cfg.research_endpoint or cfg.endpoint, transport=http,
            credential=credential, model_id_override=cfg.model_id,
            timeout_s=cfg.timeout_s)
    if cfg.invoker == "http_json":
        if not cfg.research_endpoint:
            return None
        return HttpJsonResearchInvoker(
            endpoint=cfg.research_endpoint, transport=http, credential=credential,
            model_id_override=cfg.model_id, timeout_s=cfg.timeout_s)
    raise CognitionConfigError(f"unhandled invoker mode {cfg.invoker!r}")


def build_invoker(cfg: CognitionConfig, *,
                  transport: Optional[HttpTransport] = None) -> Optional[InvokeFn]:
    """Construct the configured invoker, or `None` for the `none` default.

    `None` rather than `NullInvoker` on purpose: `ShadowCognitionRuntime` already
    has an explicit `invoker is None` branch that records the sealed
    `MODEL_UNAVAILABLE` abstention *without* consuming a provider lease or a
    budget slice. Burning four leases to learn what configuration already says
    would make the provider snapshot lie about availability.
    """
    if not cfg.configured:
        return None
    credential = resolve_credential(cfg.credential_ref, secrets_dir=cfg.secrets_dir)
    http = transport if transport is not None else HttpxTransport()
    if cfg.invoker == "http_json":
        return HttpJsonInvoker(
            endpoint=cfg.endpoint, transport=http, credential=credential,
            model_id_override=cfg.model_id, timeout_s=cfg.timeout_s)
    if cfg.invoker == "hermes_run":
        return HermesRunInvoker(
            base_url=cfg.endpoint, transport=http, credential=credential,
            model_id_override=cfg.model_id, timeout_s=cfg.timeout_s)
    raise CognitionConfigError(f"unhandled invoker mode {cfg.invoker!r}")


__all__ = [
    "CONTRACT_VERSION", "INVOKER_MODES", "REQUEST_VERSION", "UNCONFIGURED_STATE",
    "AssessmentRejected", "CognitionConfig", "CognitionConfigError",
    "HermesResearchInvoker", "HermesRunInvoker", "HttpJsonInvoker",
    "HttpJsonResearchInvoker", "HttpTransport", "HttpxTransport",
    "InvokeFn", "InvokerRefused", "NullInvoker",
    "RESEARCH_CONTRACT_VERSION", "RESEARCH_REQUEST_VERSION",
    "build_invoker", "build_research_invoker", "resolve_credential",
]
