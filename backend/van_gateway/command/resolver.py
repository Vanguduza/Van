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

    def __init__(self, default_notebook_id: str = "") -> None:
        """P1-GOOG-002 — where a note goes is the owner's to decide, not the model's.

        `google.notebook.note.create` requires `notebook_id` and this resolver sealed only
        `title`, so the parameter was unconstrained at execution and Hermes chose which of
        the owner's notebooks the note landed in. The authority check now refuses an A3
        action whose required parameters are not all sealed, so the destination has to come
        from somewhere the owner controls: either they named it, or they configured a
        default. Empty means neither, and the command is refused with a reason rather than
        landing somewhere.
        """
        self.default_notebook_id = (default_notebook_id or "").strip()

    HALT_TRADING = {
        "halt trading",
        "stop trading",
        "pause trading",
        "halt autonomous trading",
        "stop autonomous trading",
        "pause autonomous trading",
        "emergency stop trading",
    }

    #: P4-CMD-001 — matched case-insensitively against the *original* text.
    #:
    #: These used to be matched against casefolded text, so the title the owner typed was
    #: extracted already lowercased and then sealed and created that way at the provider.
    #: "Note that Dial Health is due" produced a note called "dial health is due". The
    #: sealed authority record carried the lowercase title too, so the corruption was
    #: cryptographically bound to the owner's command: nothing downstream could recover it.
    NOTE_PATTERNS = (
        re.compile(
            r"^(?:create|make) (?:a )?(?:new )?(?:notebooklm|notebook lm) note"
            r"(?: (?:named|called))? (?P<title>.+)$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:create|make) (?:a )?(?:new )?note in (?:notebooklm|notebook lm)"
            r"(?: (?:named|called))? (?P<title>.+)$",
            re.IGNORECASE,
        ),
    )

    NOTEBOOK_ENTERPRISE_DELETE_PATTERN = re.compile(
        r"^(?:delete|remove)\s+(?:the\s+)?(?:gemini\s+)?notebook enterprise notebook id\s+"
        r"(?P<notebook_id>[A-Za-z0-9._:/-]+)$",
        re.IGNORECASE,
    )
    NOTEBOOK_ENTERPRISE_DELETE_SOURCES_PATTERN = re.compile(
        r"^(?:delete|remove)\s+(?:the\s+)?(?:notebook enterprise\s+)?sources?\s+"
        r"(?P<source_names>[A-Za-z0-9._:/-]+(?:\s*,\s*[A-Za-z0-9._:/-]+)*)\s+from\s+"
        r"(?:the\s+)?(?:gemini\s+)?notebook enterprise notebook id\s+"
        r"(?P<notebook_id>[A-Za-z0-9._:/-]+)$",
        re.IGNORECASE,
    )

    #: "... in my <notebook> notebook" / "... in notebook <id>". Tried before the
    #: destination-less patterns so naming a notebook wins over the configured default.
    NOTE_WITH_NOTEBOOK_PATTERNS = (
        re.compile(
            r"^(?:create|make) (?:a )?(?:new )?(?:notebooklm|notebook lm) note"
            r"(?: (?:named|called))? (?P<title>.+?) in notebook (?P<notebook_id>[A-Za-z0-9._:/-]+)$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:create|make) (?:a )?(?:new )?note in notebook (?P<notebook_id>[A-Za-z0-9._:/-]+)"
            r"(?: (?:named|called))? (?P<title>.+)$",
            re.IGNORECASE,
        ),
    )

    RESEARCH_PATTERNS = (
        re.compile(r"^research (?P<query>.+)$", re.IGNORECASE),
        re.compile(r"^search the web for (?P<query>.+)$", re.IGNORECASE),
        re.compile(r"^look up (?P<query>.+)$", re.IGNORECASE),
    )

    CONTEXT_PATTERNS = (
        re.compile(r"^what do you know about (?P<topic>.+)\??$", re.IGNORECASE),
        re.compile(r"^what have i told you about (?P<topic>.+)\??$", re.IGNORECASE),
    )

    def resolve(self, text: str) -> CommandResolution:
        raw_compact = re.sub(r"\s+", " ", text.strip())
        normalized = raw_compact.casefold()

        if normalized in self.HALT_TRADING:
            return _from_action(
                "trading.halt",
                text=normalized,
                intent_id="TRADING_HALT",
                parameters={},
                rule_id="trading.halt.exact.v1",
            )

        for pattern in self.NOTE_WITH_NOTEBOOK_PATTERNS:
            match = pattern.fullmatch(raw_compact)
            if match:
                title = match.group("title").strip(" \"'")
                notebook_id = match.group("notebook_id").strip()
                if title and notebook_id:
                    return _from_action(
                        "google.notebook.note.create",
                        text=normalized,
                        intent_id="NOTEBOOKLM_CREATE_NOTE",
                        parameters={"notebook_id": notebook_id, "title": title},
                        rule_id="notebooklm.note.create.named-notebook.v1",
                    )

        for pattern in self.NOTE_PATTERNS:
            match = pattern.fullmatch(raw_compact)
            if match:
                title = match.group("title").strip(" \"'")
                if title:
                    # The destination is sealed from the owner's configured default. With
                    # no default the note-create action is resolved *without* it, which the
                    # authority check refuses rather than letting Hermes choose — a refusal
                    # the owner can act on beats a note in a notebook they did not pick.
                    parameters: dict[str, Any] = {"title": title}
                    if self.default_notebook_id:
                        parameters["notebook_id"] = self.default_notebook_id
                    return _from_action(
                        "google.notebook.note.create",
                        text=normalized,
                        intent_id="NOTEBOOKLM_CREATE_NOTE",
                        parameters=parameters,
                        rule_id="notebooklm.note.create.v1",
                    )

        match = self.NOTEBOOK_ENTERPRISE_DELETE_SOURCES_PATTERN.fullmatch(raw_compact)
        if match:
            notebook_id = match.group("notebook_id")
            source_names = [item.strip() for item in match.group("source_names").split(",") if item.strip()]
            if source_names:
                return _from_action(
                    "google.notebook.enterprise.sources.delete",
                    text=normalized,
                    intent_id="NOTEBOOK_ENTERPRISE_DELETE_SOURCES",
                    parameters={"notebook_id": notebook_id, "source_names": source_names},
                    rule_id="notebook.enterprise.sources.delete.exact.v1",
                )

        match = self.NOTEBOOK_ENTERPRISE_DELETE_PATTERN.fullmatch(raw_compact)
        if match:
            return _from_action(
                "google.notebook.enterprise.delete",
                text=normalized,
                intent_id="NOTEBOOK_ENTERPRISE_DELETE",
                parameters={"notebook_id": match.group("notebook_id")},
                rule_id="notebook.enterprise.delete.exact.v1",
            )

        for pattern in self.RESEARCH_PATTERNS:
            match = pattern.fullmatch(raw_compact)
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
            match = pattern.fullmatch(raw_compact)
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