"""Export the actual gateway contract for the owner frontend redesign.

No service is started and no external request is made. Optional browser routers
are inspected with inert dependencies; they are explicitly conditional, never
reported as available or live. Authentication comes from the gateway's actual
middleware classifiers, because OpenAPI alone omits those middleware gates.
"""
from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
import re
import sys
import warnings

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "trading"), str(ROOT)]


def endpoint_id(method: str, path: str) -> str:
    return "VE-" + hashlib.sha256(f"{method} {path}".encode()).hexdigest()[:12]


def flatten(routes):
    for route in routes:
        if hasattr(route, "original_router"):
            yield from flatten(route.original_router.routes)
        else:
            yield route


def export() -> dict:
    from fastapi import FastAPI
    from van_gateway.app import app
    from van_gateway.browser.interactive_api import build_interactive_router
    from van_gateway.browser.downloads_api import build_download_report_router
    from van_gateway.browser.quality_api import build_quality_router
    from van_gateway.browser.producer_api import build_browser_producer_router
    from van_gateway.browser.action_plans import build_action_plan_router
    from van_gateway.auth.provider_transport import is_artifact_provider_route

    dispatch = next(m.kwargs["dispatch"] for m in app.user_middleware
                    if m.kwargs.get("dispatch", None)
                    and m.kwargs["dispatch"].__name__ == "require_ingress_auth")
    closure = inspect.getclosurevars(dispatch).nonlocals
    scope_for = closure["control_scope_for"]
    proof_for = closure["requires_device_proof"]
    artemis_console = closure["artemis_console"]

    # Building these route declarations does not mint grants, read keys or call
    # dependencies. A configured signing key is required to mount them for real.
    optional = FastAPI()
    optional.include_router(build_interactive_router(
        sessions=None, control=None, grants=None, agent_grants=None,
        downloads_broker=None, signal_url="", ice_servers=[]))
    optional.include_router(build_download_report_router(broker=None, sessions=None))
    optional.include_router(build_quality_router(controllers=None, sessions=None))
    optional.include_router(build_browser_producer_router(service=None, settings=None))
    optional.include_router(build_action_plan_router(service=None))

    def auth(method, path):
        # The exact production predicate accepts concrete admission identities,
        # while OpenAPI records a template. Substitute only that route parameter
        # to classify the declaration; this grants no principal or admission.
        if is_artifact_provider_route({"type": "http", "method": method,
                "path": path.replace("{admission_id}", "registry_admission")}):
            return "ATTESTED_ARTIFACT_PROVIDER:CURRENT_PINNED_MTLS_AND_SIGNED_EXACT_ADMISSION", False
        if method == "WEBSOCKET":
            # The socket authenticates the device token and checks ownership of
            # van_session_id; that identifier is not a separate session token.
            # A bound device proves the handshake unless verified mTLS does so.
            return "PAIRED_DEVICE_TOKEN_AND_OWNED_SESSION", True
        if method == "GET" and path.startswith(artemis_console.LAUNCH_PREFIX):
            return "SINGLE_USE_ARTEMIS_LAUNCH_TOKEN", False
        if method == "POST" and path == "/v1/devices/pair":
            return "PAIRING_TICKET_AND_ATTESTED_BOUND_DEVICE_PROOF; EXACT_RECOVERY_WITH_CLIENT_TOKEN", True
        if method == "POST" and path == "/v1/devices/bootstrap/challenge":
            return "SINGLE_USE_BOOTSTRAP_TOKEN", False
        if method == "POST" and path == "/v1/devices/bootstrap/attest":
            return "SINGLE_USE_BOOTSTRAP_TOKEN_AND_PINNED_ATTESTATION_CHAIN_AND_FRESH_DEVICE_PROOF", True
        if method == "POST" and path == "/v1/devices/bootstrap/recover":
            return "CONSUMED_BOOTSTRAP_TOKEN_AND_EXACT_ACTIVE_DEVICE_PROOF", True
        if method == "GET" and path.startswith("/v1/trading/oauth/") and path.endswith("/callback"):
            return "BROKER_OAUTH_CALLBACK_STATE", False
        scope = scope_for(method, path)
        if scope is not None:
            return "INTERNAL_CONTROL:" + scope.value, False
        if path == "/health":
            return "INGRESS_BEARER", False
        # Reuse the middleware's exact resource predicate: the session-minting
        # POST explicitly excludes browser-cookie authority and requires the
        # regular ingress/device gates plus a bound device proof.
        if artemis_console.is_console_resource_path(path):
            return "INGRESS_BEARER_AND_PAIRED_DEVICE_OR_AUTHORIZED_ARTEMIS_BROWSER_SESSION", proof_for(method, path)
        return "INGRESS_BEARER_AND_PAIRED_DEVICE", proof_for(method, path)

    endpoints = {}
    for application, conditional in ((app, False), (optional, True)):
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Duplicate Operation ID")
            spec = application.openapi()
        route_lookup = {}
        for route in flatten(application.routes):
            path = getattr(route, "path", None)
            if path is None or not hasattr(route, "endpoint"):
                continue
            handler = route.endpoint
            source = inspect.getsourcefile(handler)
            citation = None
            if source and Path(source).is_relative_to(ROOT):
                citation = f"{Path(source).relative_to(ROOT)}:{inspect.getsourcelines(handler)[1]}"
            methods = getattr(route, "methods", None) or {"WEBSOCKET"}
            for method in methods:
                # OpenAPI strips Starlette converter suffixes such as :path.
                schema_path = re.sub(r"\{([^}:]+):[^}]+\}", r"{\1}", path)
                route_lookup[(method, schema_path)] = citation
            if not getattr(route, "methods", None) and path.startswith("/v1/"):
                authentication, proof = auth("WEBSOCKET", path)
                endpoints[("WEBSOCKET", path)] = {
                    "endpoint_id": endpoint_id("WEBSOCKET", path),
                    "method": "WEBSOCKET", "path": path,
                    "authentication": authentication, "device_proof_required_when_bound": proof,
                    "registration": "CONDITIONAL" if conditional else "DEFAULT",
                    "source": citation, "contract": "session envelope/event protocol; see session/api.py",
                }
        for path, operations in spec["paths"].items():
            for method, operation in operations.items():
                if method not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                    continue
                verb = method.upper()
                authentication, proof = auth(verb, path)
                endpoints[(verb, path)] = {
                    "endpoint_id": endpoint_id(verb, path), "method": verb, "path": path,
                    "authentication": authentication,
                    "device_proof_required_when_bound": proof,
                    "registration": "CONDITIONAL" if conditional else "DEFAULT",
                    "condition": ("browser_stream_signing_key_file configured; dedicated producer scope and authenticated private ingress required; runtime host acceptance pending"
                                  if conditional and ("/stream-producer/" in path or "/control-producer/" in path)
                                  else "browser_stream_signing_key_file configured; stream host and canaries required for live use" if conditional else None),
                    "source": route_lookup.get((verb, path)),
                    "summary": operation.get("summary", ""),
                    "tags": operation.get("tags", []),
                    "parameters": operation.get("parameters", []),
                    "request_body": operation.get("requestBody"),
                    "responses": operation.get("responses", {}),
                    "openapi_components": "owner_endpoint_schemas.json",
                    "readiness": "REPOSITORY_DECLARATION_ONLY",
                }
        # Components are shared Pydantic contracts. The browser extension adds
        # schemas absent from the default gateway configuration.
        if conditional:
            schemas.update(spec.get("components", {}).get("schemas", {}))
        else:
            schemas = dict(spec.get("components", {}).get("schemas", {}))
    return {
        "schema_version": 1,
        "purpose": "Derived frontend endpoint inventory; source and security policy remain authoritative.",
        "scope": "Gateway default HTTP/WebSocket routes plus explicitly conditional interactive browser routes. No live readiness claim.",
        "authentication_notes": [
            "INTERNAL_CONTROL routes are service-to-service; never ship internal credentials in Android. Owner intent must use a supported signed owner/session path.",
            "ATTESTED_ARTIFACT_PROVIDER routes require HTTPS and the actual TLS-verified client leaf matched to a current provider/owner/project pin, plus an exact fresh signed admission and current execution introspection. Owner device credentials, forwarded identity headers and static internal bearers cannot authorize this separate service lane; Android uses only owner draft/read/cancel and signed A4 command routes.",
            "Proof requirements come from actual middleware and apply when device binding is enforced; mTLS is an additional transport/device gate on the direct listener.",
            "The session WebSocket uses a paired-device token and an owned session ID. A bound-device handshake proof is required unless verified mTLS supplies the same device identity; the session ID is not a second credential.",
            "ARTEMIS session minting requires ingress and paired-device authority plus bound-device proof. A one-use launch token redeems a browser cookie; that cookie authorizes only the console resource predicate, with origin checks on mutations.",
            "Request handlers may impose additional HMAC, owner signature, approval, grant, ownership, freshness and scope checks; endpoint existence grants no authority.",
            "OpenAPI does not enumerate every runtime/domain refusal. Feature acceptance contracts define UI recovery and evidence states.",
        ],
        "endpoints": [endpoints[key] for key in sorted(endpoints)],
        "schemas": schemas,
    }


if __name__ == "__main__":
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "registries"
    destination.mkdir(parents=True, exist_ok=True)
    result = export()
    schemas = result.pop("schemas")
    (destination / "owner_endpoints.json").write_text(json.dumps(result, indent=2) + "\n")
    (destination / "owner_endpoint_schemas.json").write_text(
        json.dumps({"components": {"schemas": schemas}}, indent=2) + "\n")
    print(f"Exported {len(result['endpoints'])} endpoints and {len(schemas)} schemas")
