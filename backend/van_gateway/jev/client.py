from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


class JevProjectionError(RuntimeError):
    pass


class JevProjectionClient:
    def __init__(
        self, *, base_url: str, read_token_file: str, control_token_file: str,
        enabled: bool, timeout_seconds: float = 5.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._read_token_file = read_token_file
        self._control_token_file = control_token_file
        self._enabled = enabled
        self._timeout = timeout_seconds

    @property
    def configured(self) -> bool:
        return self._enabled and bool(self._base_url) and bool(self._read_token_file)

    @staticmethod
    def _token(path: str, *, kind: str) -> str:
        if not path:
            raise JevProjectionError(f"jev_{kind}_token_file_unconfigured")
        token = Path(path).read_text(encoding="utf-8").strip()
        if not token:
            raise JevProjectionError(f"jev_{kind}_token_empty")
        return token

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        if not self.configured:
            raise JevProjectionError("jev_projection_unconfigured")
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{self._base_url}{path}",
                params=params,
                headers={"X-Dial-Jev-Token": self._token(self._read_token_file, kind="projection")},
            )
        if response.status_code >= 400:
            raise JevProjectionError(f"jev_projection_http_{response.status_code}")
        body = response.json()
        if not isinstance(body, dict):
            raise JevProjectionError("jev_projection_invalid_payload")
        return body

    async def _post(self, path: str, payload: dict[str, Any]) -> dict:
        if not self.configured:
            raise JevProjectionError("jev_projection_unconfigured")
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}{path}",
                json=payload,
                headers={"X-Dial-Jev-Token": self._token(self._control_token_file, kind="control")},
            )
        if response.status_code >= 400:
            detail = response.text[:240]
            raise JevProjectionError(f"jev_projection_http_{response.status_code}:{detail}")
        body = response.json()
        if not isinstance(body, dict):
            raise JevProjectionError("jev_projection_invalid_payload")
        return body

    async def health(self) -> dict:
        if not self._enabled or not self._base_url:
            return {"status": "disabled", "enabled": False}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(f"{self._base_url}/health")
        if response.status_code >= 400:
            raise JevProjectionError(f"jev_health_http_{response.status_code}")
        body = response.json()
        return body if isinstance(body, dict) else {"status": "invalid"}

    async def status(self) -> dict:
        return await self._get("/v1/status")

    async def provider(self) -> dict:
        return await self._get("/v1/provider")

    async def modules(self) -> dict:
        return await self._get("/v1/modules")

    async def module(self, module_id: str) -> dict:
        return await self._get(f"/v1/modules/{module_id}")

    async def activity(self, *, project_id: str, limit: int = 100) -> dict:
        return await self._get("/v1/activity", {"project_id": project_id, "limit": limit})

    async def outcomes(self, *, project_id: str, limit: int = 100) -> dict:
        return await self._get("/v1/outcomes", {"project_id": project_id, "limit": limit})

    async def performance(self, *, project_id: str, module_id: str | None = None) -> dict:
        params: dict[str, Any] = {"project_id": project_id}
        if module_id:
            params["module_id"] = module_id
        return await self._get("/v1/performance", params)

    async def contribution(self, *, project_id: str, module_id: str) -> dict:
        return await self._get("/v1/contribution", {"project_id": project_id, "module_id": module_id})

    async def safety(self, *, project_id: str, module_id: str) -> dict:
        return await self._get("/v1/safety", {"project_id": project_id, "module_id": module_id})

    async def evaluation_packet(self, *, project_id: str, module_id: str) -> dict:
        return await self._get("/v1/evaluation/packet", {"project_id": project_id, "module_id": module_id})

    async def evaluation_proposals(self, *, module_id: str | None = None, limit: int = 100) -> dict:
        params: dict[str, Any] = {"limit": limit}
        if module_id:
            params["module_id"] = module_id
        return await self._get("/v1/evaluation/proposals", params)

    async def evaluation_reviews(self, *, proposal_id: str | None = None, limit: int = 100) -> dict:
        params: dict[str, Any] = {"limit": limit}
        if proposal_id:
            params["proposal_id"] = proposal_id
        return await self._get("/v1/evaluation/reviews", params)

    async def evaluation_candidates(self, *, module_id: str | None = None, limit: int = 100) -> dict:
        params: dict[str, Any] = {"limit": limit}
        if module_id:
            params["module_id"] = module_id
        return await self._get("/v1/evaluation/candidates", params)

    async def transition_module(
        self, *, module_id: str, target_state: str, authority_ref: str,
        reason: str | None = None, owner_approved: bool = False,
    ) -> dict:
        return await self._post(
            f"/v1/modules/{module_id}/transition",
            {
                "to": target_state,
                "authority_ref": authority_ref,
                "reason": reason,
                "owner_approved": owner_approved,
                "evidence_refs": [authority_ref],
            },
        )

    async def global_control(
        self, *, authority_ref: str, owner_active: bool | None = None,
        bypassed: bool | None = None, project_id: str | None = None,
        project_enabled: bool | None = None, reason: str | None = None,
    ) -> dict:
        payload: dict[str, Any] = {"authority_ref": authority_ref, "reason": reason}
        if owner_active is not None:
            payload["owner_active"] = owner_active
        if bypassed is not None:
            payload["bypassed"] = bypassed
        if project_id is not None:
            payload["project_id"] = project_id
        if project_enabled is not None:
            payload["project_enabled"] = project_enabled
        return await self._post("/v1/control/global", payload)


# --------------------------------------------------------------------------------------
# B1 PROPOSE_ACTION (Programme B, Jev x OpenMuse Convergence Rev 1, contract B5 caller side)
# --------------------------------------------------------------------------------------

PROPOSE_ACTION_ROUTE = "/v1/judgments/propose-action"
BROWSER_ACTION_MODULE = "van.browser.ultrafast.action.v1"

#: Keys the unit-E contract names, plus the three the DDS route is known to add
#: (`action_class`, `apply_effect`, `lifecycle_state`). Anything else is a schema mismatch.
_PROPOSE_RESPONSE_REQUIRED = frozenset(
    {"outcome", "state", "proposal", "confidence", "reasons", "executes", "verified_success"}
)
_PROPOSE_RESPONSE_OPTIONAL = frozenset({"action_class", "apply_effect", "lifecycle_state"})
_PROPOSAL_KEYS = frozenset({"operation", "target_id", "value_ref"})
#: The unit-E contract says `PROPOSE`; the DDS reference route emits `PROPOSED`. Both mean
#: "a proposal is attached". Everything else is an abstention.
_PROPOSE_OUTCOMES = frozenset({"PROPOSE", "PROPOSED"})


@dataclass(frozen=True)
class ProposeActionResponse:
    """What dial-jev said, reduced to the fields VAN is prepared to act on.

    ``transport_ok`` is False when the answer never arrived in a usable form (transport
    error, timeout, non-200, schema mismatch). Those are all ABSTAIN to the router.
    """

    outcome: str
    state: str
    proposal: dict[str, Any] | None
    confidence: float | None
    reasons: tuple[str, ...]
    action_class: str | None = None
    transport_ok: bool = True

    @property
    def proposes(self) -> bool:
        return self.outcome == "PROPOSE" and self.proposal is not None


def _abstain(reason: str, *, transport_ok: bool = False) -> ProposeActionResponse:
    return ProposeActionResponse(
        outcome="ABSTAIN", state="ABSTAINED", proposal=None, confidence=None,
        reasons=(reason,), transport_ok=transport_ok,
    )


def parse_propose_action_response(body: Any) -> ProposeActionResponse:
    """Schema check. Any mismatch degrades to ABSTAIN, never to a partial proposal."""
    if not isinstance(body, dict):
        return _abstain("JEV_RESPONSE_NOT_OBJECT")
    keys = set(body)
    missing = _PROPOSE_RESPONSE_REQUIRED - keys
    if missing:
        return _abstain(f"JEV_RESPONSE_KEY_MISSING:{sorted(missing)[0]}")
    unknown = keys - _PROPOSE_RESPONSE_REQUIRED - _PROPOSE_RESPONSE_OPTIONAL
    if unknown:
        return _abstain(f"JEV_RESPONSE_UNKNOWN_KEY:{sorted(unknown)[0]}")
    # Jev never executes and never verifies. A response claiming otherwise is not one
    # VAN will act on, whatever else it says.
    if body["executes"] is not False:
        return _abstain("JEV_RESPONSE_CLAIMS_EXECUTION")
    if body["verified_success"] is not False:
        return _abstain("JEV_RESPONSE_CLAIMS_VERIFIED_SUCCESS")
    # dial-jev reports apply_effect=false while the module is SHADOW. A browser proposal
    # never carries effect in Rev 1, so a true here is a contract violation.
    if body.get("apply_effect", False) is not False:
        return _abstain("JEV_RESPONSE_APPLY_EFFECT_NOT_FALSE")
    reasons = body["reasons"]
    if not isinstance(reasons, list) or not all(isinstance(r, str) for r in reasons):
        return _abstain("JEV_RESPONSE_REASONS_INVALID")
    outcome = body["outcome"]
    if not isinstance(outcome, str) or not isinstance(body["state"], str):
        return _abstain("JEV_RESPONSE_OUTCOME_INVALID")
    if outcome not in _PROPOSE_OUTCOMES:
        # A well-formed abstention: transport fine, Jev simply did not propose.
        return ProposeActionResponse(
            outcome="ABSTAIN", state=str(body["state"]), proposal=None, confidence=None,
            reasons=tuple(reasons) or ("JEV_ABSTAINED",),
        )
    proposal = body["proposal"]
    if not isinstance(proposal, dict) or set(proposal) != _PROPOSAL_KEYS:
        return _abstain("JEV_RESPONSE_PROPOSAL_SHAPE_INVALID")
    confidence = body["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return _abstain("JEV_RESPONSE_CONFIDENCE_INVALID")
    action_class = body.get("action_class")
    if action_class is not None and not isinstance(action_class, str):
        return _abstain("JEV_RESPONSE_ACTION_CLASS_INVALID")
    return ProposeActionResponse(
        outcome="PROPOSE",
        state=str(body["state"]),
        proposal={k: proposal[k] for k in ("operation", "target_id", "value_ref")},
        confidence=float(confidence),
        reasons=tuple(reasons),
        action_class=action_class,
    )


class JevProposeActionClient:
    """VAN caller of ``POST /v1/judgments/propose-action`` on the single dial-jev service.

    Uses the consumer-scoped (JUDGE) credential only. It returns a proposal or an
    abstention; it has no method that executes anything. Every failure mode — disabled,
    unconfigured, transport error, timeout, non-200, schema mismatch — is an ABSTAIN with
    ``transport_ok=False`` so the router falls through to its next lane.
    """

    def __init__(
        self,
        *,
        base_url: str,
        token_file: str,
        enabled: bool,
        timeout_seconds: float = 1.2,
        project_id: str = "van",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = (base_url or "").rstrip("/")
        self._token_file = token_file
        self._enabled = enabled
        self._timeout = timeout_seconds
        self._project_id = project_id
        self._transport = transport

    @property
    def configured(self) -> bool:
        return self._enabled and bool(self._base_url) and bool(self._token_file)

    async def propose_action(
        self,
        *,
        request: dict[str, Any],
        caller_action_classes: list[dict[str, Any]],
        current_epoch: str,
    ) -> ProposeActionResponse:
        if not self.configured:
            return _abstain("JEV_CLIENT_UNCONFIGURED")
        try:
            token = Path(self._token_file).read_text(encoding="utf-8").strip()
        except OSError:
            return _abstain("JEV_CLIENT_TOKEN_UNREADABLE")
        if not token:
            return _abstain("JEV_CLIENT_TOKEN_EMPTY")
        body = {
            "project_id": self._project_id,
            "module_id": BROWSER_ACTION_MODULE,
            "request": request,
            "caller_action_classes": caller_action_classes,
            "current_epoch": current_epoch,
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self._base_url}{PROPOSE_ACTION_ROUTE}",
                    json=body,
                    headers={"X-Dial-Jev-Token": token},
                )
        except httpx.TimeoutException:
            return _abstain("JEV_TIMEOUT")
        except (httpx.HTTPError, OSError):
            return _abstain("JEV_TRANSPORT_ERROR")
        if response.status_code != 200:
            return _abstain(f"JEV_HTTP_{response.status_code}")
        try:
            payload = response.json()
        except ValueError:
            return _abstain("JEV_RESPONSE_NOT_JSON")
        return parse_propose_action_response(payload)
