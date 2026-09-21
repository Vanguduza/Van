"""Scoped internal-control credentials.

P0-SEC-001: one static token was gateway root. `X-Van-Internal-Token` alone minted a
pairing ticket; `/v1/devices/pair` then needed no authentication at all and returned both
the ingress bearer and a device access token — owner-device authority, from one string.
The same token also reached Project Truth injection, device revocation, Google connect and
revoke, the trading halt, every automation route, browser mutations and context scope
delete. It is read by the Hermes MCP shim from `~/.config/van/gateway.env`, so a
model-driven runtime holds it.

Three things were wrong and each needs its own fix:

**It was one credential for everything.** A scope now names what a credential may reach,
and a credential carries a set of them. The Hermes runtime's token is not given
`device_enrolment`, so the path from "the agent runtime is compromised" to "the attacker
holds owner-device authority" is cut at the first step rather than at the last.

**Device enrolment was in the agent-reachable set.** It is now its own scope with its own
credential, which the shim does not read. An operator who configures nothing gets a
gateway that cannot mint a pairing ticket at all — which is inconvenient once, and is the
right way round.

**A failed internal check fell through.** The middleware tried the internal token, and on
a mismatch carried on to ingress plus device authentication. So a route declared
Hermes-only was reachable with an owner device token. The check is now terminal: an
internal-control route answers 403 and stops.

Credentials are configured as `<scope>,<scope>:<token>` entries. That is deliberately
plain text in the environment rather than a format needing tooling, because a credential
scheme nobody can configure by hand is one that ends up as a single shared token again.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from enum import Enum


class ControlScope(str, Enum):
    """What a privileged credential is allowed to reach."""

    RUNTIME = "runtime"
    AUTOMATION = "automation"
    BROWSER = "browser"
    GOOGLE = "google"
    TRADING = "trading"
    PROJECTS = "projects"
    MISSIONS = "missions"
    UNDERSTANDING = "understanding"
    #: Deliberately separate: this is the scope that can mint owner-device authority.
    DEVICE_ENROLMENT = "device_enrolment"
    #: Gate 11's operator surface — metrics, alerts, health and the command trace.
    #: Also deliberately separate: a trace names device ids, command ids and failure
    #: reasons across the whole system, which is exactly the shape of thing a
    #: model-driven runtime should not be able to read just because it can drive
    #: automation. An operator grants it on purpose, like device enrolment.
    OBSERVABILITY = "observability"


#: What the legacy single token is granted when nothing finer is configured. Everything
#: except device enrolment: an existing deployment keeps working, and the one scope that
#: turns a control credential into owner authority has to be granted on purpose.
DEFAULT_SCOPES = frozenset(
    s for s in ControlScope
    if s not in (ControlScope.DEVICE_ENROLMENT, ControlScope.OBSERVABILITY)
)


@dataclass(frozen=True)
class ControlCredential:
    token: str
    scopes: frozenset[ControlScope]
    label: str


class ControlScopeError(ValueError):
    """A scoped-credential configuration that cannot be honoured."""


def parse_scoped_credentials(raw: str) -> list[ControlCredential]:
    """Parse `scope,scope:token; scope:token` into credentials.

    An entry naming an unknown scope is a configuration error rather than something to
    skip: silently dropping it would leave an operator believing a surface was reachable.
    """
    credentials: list[ControlCredential] = []
    for entry in (raw or "").replace("\n", ";").split(";"):
        entry = entry.strip()
        if not entry:
            continue
        scopes_part, separator, token = entry.partition(":")
        if not separator or not token.strip():
            raise ControlScopeError(f"scoped credential {entry.split(':')[0]!r} has no token")
        names = [n.strip() for n in scopes_part.split(",") if n.strip()]
        if not names:
            raise ControlScopeError("a scoped credential names no scopes")
        try:
            scopes = frozenset(ControlScope(n) for n in names)
        except ValueError as exc:
            raise ControlScopeError(
                f"unknown control scope in {scopes_part!r}; known scopes are "
                f"{sorted(s.value for s in ControlScope)}"
            ) from exc
        if len(token.strip()) < 32:
            raise ControlScopeError(
                f"scoped credential for {scopes_part!r} is shorter than 32 characters"
            )
        credentials.append(
            ControlCredential(token.strip(), scopes, ",".join(sorted(s.value for s in scopes)))
        )
    return credentials


class ControlAuthority:
    """Answers one question: may this presented token reach this scope?"""

    def __init__(
        self,
        *,
        legacy_token: str = "",
        scoped: str = "",
        device_enrolment_token: str = "",
        observability_token: str = "",
        legacy_scopes: frozenset[ControlScope] = DEFAULT_SCOPES,
    ) -> None:
        self.credentials = parse_scoped_credentials(scoped)
        if legacy_token.strip():
            self.credentials.append(
                ControlCredential(legacy_token.strip(), legacy_scopes, "legacy")
            )
        # Its own credential, configured separately and never read by the Hermes shim. If
        # it happens to equal the legacy token the operator has chosen to collapse the
        # split, and `describe()` says so rather than hiding it.
        if device_enrolment_token.strip():
            self.credentials.append(
                ControlCredential(
                    device_enrolment_token.strip(),
                    frozenset({ControlScope.DEVICE_ENROLMENT}),
                    "device_enrolment",
                )
            )
        if observability_token.strip():
            self.credentials.append(
                ControlCredential(
                    observability_token.strip(),
                    frozenset({ControlScope.OBSERVABILITY}),
                    "observability",
                )
            )

    @property
    def configured(self) -> bool:
        return bool(self.credentials)

    def granted_scopes(self, presented: str | None) -> frozenset[ControlScope]:
        """Every scope the presented token holds, or an empty set.

        Compared in constant time against each configured credential, and the loop does
        not stop early, so the number of configured credentials is not observable.
        """
        if not presented or not presented.strip():
            return frozenset()
        candidate = presented.strip()
        granted: set[ControlScope] = set()
        for credential in self.credentials:
            if hmac.compare_digest(credential.token, candidate):
                granted |= credential.scopes
        return frozenset(granted)

    def permits(self, presented: str | None, scope: ControlScope) -> bool:
        return scope in self.granted_scopes(presented)

    def describe(self) -> dict:
        """What is configured, for the health surface. Never the tokens themselves."""
        return {
            "configured": self.configured,
            "credentials": [
                {"label": c.label, "scopes": sorted(s.value for s in c.scopes)}
                for c in self.credentials
            ],
            "device_enrolment_granted": any(
                ControlScope.DEVICE_ENROLMENT in c.scopes for c in self.credentials
            ),
            # Named because an operator who set both to the same string has rebuilt the
            # single-root-token shape and should be able to see that they did.
            "device_enrolment_shares_a_token": any(
                ControlScope.DEVICE_ENROLMENT in c.scopes
                and any(
                    other is not c
                    and other.token == c.token
                    and ControlScope.DEVICE_ENROLMENT not in other.scopes
                    for other in self.credentials
                )
                for c in self.credentials
            ),
        }


__all__ = [
    "DEFAULT_SCOPES",
    "ControlAuthority",
    "ControlCredential",
    "ControlScope",
    "ControlScopeError",
    "parse_scoped_credentials",
]


def authority_from_settings(settings) -> "ControlAuthority":
    """The one ControlAuthority every surface must consult.

    GAP-F-009 — six routers compared the presented token against the legacy
    `internal_control_token` alone, so a deployment that had migrated to scoped
    credentials (the point of P0-SEC-001) found those surfaces answering 503 even
    with a correctly scoped token. Building the authority from settings here means
    a router cannot drift back to a single-string comparison.
    """
    return ControlAuthority(
        legacy_token=getattr(settings, "internal_control_token", "") or "",
        scoped=getattr(settings, "internal_control_scoped_tokens", "") or "",
        device_enrolment_token=getattr(settings, "device_enrolment_token", "") or "",
        observability_token=getattr(settings, "observability_token", "") or "",
    )


def require_scoped_internal(settings, token, scope: "ControlScope") -> None:
    """Handler-level scoped check that agrees with the middleware (GAP-F-009).

    Raises fastapi.HTTPException 503 when no privileged credential is configured and
    403 when the presented token does not hold `scope`.
    """
    from fastapi import HTTPException

    authority = authority_from_settings(settings)
    if not authority.configured:
        raise HTTPException(status_code=503, detail="internal_control_token_unconfigured")
    if not authority.permits(token, scope):
        raise HTTPException(status_code=403, detail="internal_control_unauthorized")
