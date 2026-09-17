from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from van_gateway.action.models import VerifierType
from van_gateway.action.registry import BUILTIN_ACTIONS
from van_gateway.models import ActionClass


class ResolutionMode(str, Enum):
    EXACT_ACTION = "EXACT_ACTION"
    HERMES_INTERPRETATION_REQUIRED = "HERMES_INTERPRETATION_REQUIRED"


class CommandResolution(BaseModel):
    resolver_version: str = "rev3.1.1"
    mode: ResolutionMode
    normalized_text: str
    intent_id: str
    action_id: str | None = None
    canonical_action_class: ActionClass | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    no_stale_replay: bool = False
    max_age_seconds: int | None = None
    verifier_type: VerifierType | None = None
    rule_id: str | None = None


_ACTIONS = {definition.action_id: definition for definition in BUILTIN_ACTIONS}
_MUTATION_WORDS = {
    "create", "update", "change", "modify", "delete", "remove", "send",
    "publish", "commit", "push", "merge", "buy", "sell", "trade", "execute",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).casefold()


def _has_composite_mutation(text: str) -> bool:
    if " and " not in text and " then " not in text:
        return False
    tail = re.split(r"\b(?:and|then)\b", text, maxsplit=1)[-1]
    words = set(re.findall(r"[a-z0-9]+", tail))
    return bool(words & _MUTATION_WORDS)


def _from_action(action_id: str, *, text: str, intent_id: str, parameters: dict[str, Any], rule_id: str) -> CommandResolution:
    definition = _ACTIONS[action_id]
    return CommandResolution(
        mode=ResolutionMode.EXACT_ACTION,
        normalized_text=text,
        intent_id=intent_id,
        action_id=action_id,
        canonical_action_class=definition.action_class,
        parameters=parameters,
        no_stale_replay=definition.no_stale_replay,
        max_age_seconds=definition.max_age_seconds,
        verifier_type=definition.verifier_type,
        rule_id=rule_id,
    )


class TypedCommandResolver:
    """Deterministic fast-path resolver for known VAN actions.

    This component is deliberately not an agent or planner. It only resolves
    conservative, explicit owner phrases to actions already registered by the
    gateway. Anything ambiguous/composite remains a Hermes interpretation task.
    """

    HALT_TRADING = {
        "halt trading",
        "stop trading",
        "pause trading",
        "halt autonomous trading",
        "stop autonomous trading",
        "pause autonomous trading",
        "emergency stop trading",
    }

    NOTE_PATTERNS = (
        re.compile(r"^(?:create|make) (?:a )?(?:new )?(?:notebooklm|notebook lm) note(?: (?:named|called))? (?P<title>.+)$"),
        re.compile(r"^(?:create|make) (?:a )?(?:new )?note in (?:notebooklm|notebook lm)(?: (?:named|called))? (?P<title>.+)$"),
    )

    RESEARCH_PATTERNS = (
        re.compile(r"^research (?P<query>.+)$"),
        re.compile(r"^search the web for (?P<query>.+)$"),
        re.compile(r"^look up (?P<query>.+)$"),
    )

    CONTEXT_PATTERNS = (
        re.compile(r"^what do you know about (?P<topic>.+)\??$"),
        re.compile(r"^what have i told you about (?P<topic>.+)\??$"),
    )

    def resolve(self, text: str) -> CommandResolution:
        normalized = _normalize(text)

        if normalized in self.HALT_TRADING:
            return _from_action(
                "trading.halt",
                text=normalized,
                intent_id="TRADING_HALT",
                parameters={},
                rule_id="trading.halt.exact.v1",
            )

        for pattern in self.NOTE_PATTERNS:
            match = pattern.fullmatch(normalized)
            if match:
                title = match.group("title").strip(" \"'")
                if title:
                    return _from_action(
                        "google.notebook.note.create",
                        text=normalized,
                        intent_id="NOTEBOOKLM_CREATE_NOTE",
                        parameters={"title": title},
                        rule_id="notebooklm.note.create.v1",
                    )

        for pattern in self.RESEARCH_PATTERNS:
            match = pattern.fullmatch(normalized)
            if match and not _has_composite_mutation(normalized):
                query = match.group("query").strip(" \"'")
                if query:
                    return _from_action(
                        "research.web.search",
                        text=normalized,
                        intent_id="WEB_RESEARCH",
                        parameters={"query": query},
                        rule_id="research.web.search.v1",
                    )

        for pattern in self.CONTEXT_PATTERNS:
            match = pattern.fullmatch(normalized)
            if match:
                topic = match.group("topic").rstrip("?").strip()
                if topic:
                    return _from_action(
                        "owner.context.read",
                        text=normalized,
                        intent_id="OWNER_CONTEXT_READ",
                        parameters={"topic": topic},
                        rule_id="owner.context.read.v1",
                    )

        return CommandResolution(
            mode=ResolutionMode.HERMES_INTERPRETATION_REQUIRED,
            normalized_text=normalized,
            intent_id="GENERAL_OWNER_INTENT",
        )

    @staticmethod
    def stronger_class(client: ActionClass, canonical: ActionClass | None) -> ActionClass:
        if canonical is None:
            return client
        rank = {ActionClass.A1: 1, ActionClass.A2: 2, ActionClass.A3: 3, ActionClass.A4: 4, ActionClass.A5: 5}
        return canonical if rank[canonical] > rank[client] else client
