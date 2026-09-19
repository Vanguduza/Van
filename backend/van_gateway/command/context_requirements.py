"""What a command actually needs to know before it is answered.

P0-CTX-001: the orchestrator sealed every context snapshot with an empty requirements
list. Readiness was therefore trivially CURRENT, `fact_ids` was always empty, and the
`canonical_context` handed to Hermes carried a snapshot id, a digest, a Project Truth SHA
and policy references — and not one owner fact. The context kernel was real, tested and
never asked a question.

Requirements are derived here rather than in the orchestrator because deciding what a
command needs is a judgement, and a judgement belongs somewhere it can be read and
disagreed with.

The rules are deliberately few. A requirement that is usually MISSING trains everyone to
ignore readiness, which is worse than having none: the point of asking is that the answer
sometimes changes what happens. So this asks for what the owner would expect VAN to know
before acting, and nothing speculative.
"""

from __future__ import annotations

import re

from van_gateway.context.models import ContextRequirement

#: The owner themselves. Asked on every command, because a system that does not know who
#: it is acting for cannot act well, and because this is the requirement whose absence
#: most deserves to be visible.
OWNER_SUBJECT = "OWNER"

#: Predicates read from Project Truth when a command names a project. These are the
#: questions a project command's answer actually turns on.
PROJECT_PREDICATES = ("branch", "stack", "deploy_target", "owner")

#: Predicates a typed action needs, by the action's family. Keyed on the prefix so a new
#: action in a known family inherits the requirement rather than silently having none.
ACTION_FAMILY_PREDICATES: dict[str, tuple[str, ...]] = {
    "trading.": ("risk_posture", "trading_account"),
    "calendar.": ("timezone", "working_hours"),
    "message.": ("timezone", "preferred_channel"),
    "travel.": ("home_city", "timezone"),
}

#: People a command names, so "remind Thandi" can resolve to a person VAN knows about.
#: The verb may be capitalised at the start of a sentence; the name must be, because that
#: is the only signal separating "remind Thandi" from "remind me".
_NAME = re.compile(
    r"\b(?i:tell|remind|ask|message|email|call|text)\s+([A-Z][a-z]{2,})\b"
)


def derive(
    *,
    text: str,
    project_id: str | None,
    action_id: str | None,
    max_age_ms: int | None = None,
) -> list[ContextRequirement]:
    """The facts this command should be answered against.

    `allow_inferred` stays false throughout. A model's guess about the owner is not a
    basis for acting on their behalf, and admitting one here would quietly undo the one
    boundary the admission route does enforce.

    Everything derived here is advisory. The gates that refuse a command already exist and
    are stricter — the project truth gate, the action class gate, the trust gate — and a
    second gate that disagreed with them would make the system harder to reason about, not
    safer. What was missing was not another refusal; it was the record of what VAN knew
    when it acted.
    """
    # Advisory: a brief computed without knowing the owner's timezone is a worse brief,
    # not a wrong action. Blocking on it would stop every command on a fresh system.
    requirements: list[ContextRequirement] = [
        ContextRequirement(
            subject=OWNER_SUBJECT, predicate="timezone", max_age_ms=max_age_ms, blocking=False
        ),
    ]

    if project_id:
        requirements += [
            # Advisory. The project truth gate already refuses a mutation against stale
            # truth; these are here so the snapshot records what was known, not to add a
            # second gate that would disagree with the first.
            ContextRequirement(
                subject=project_id, predicate=predicate, scope=f"project:{project_id}",
                max_age_ms=max_age_ms, blocking=False,
            )
            for predicate in PROJECT_PREDICATES
        ]

    if action_id:
        for family, predicates in ACTION_FAMILY_PREDICATES.items():
            if action_id.startswith(family):
                requirements += [
                    ContextRequirement(
                        subject=OWNER_SUBJECT, predicate=predicate, max_age_ms=max_age_ms,
                        blocking=False,
                    )
                    for predicate in predicates
                ]
                break

    for person in dict.fromkeys(_NAME.findall(text or "")):
        requirements.append(
            ContextRequirement(
                subject=person, predicate="contact", scope="people", blocking=False
            )
        )

    # Deduplicated, because the same requirement asked twice would make a readiness report
    # look more thorough than it is.
    seen: set[tuple[str, str, str]] = set()
    unique: list[ContextRequirement] = []
    for requirement in requirements:
        key = (requirement.subject, requirement.predicate, requirement.scope)
        if key not in seen:
            seen.add(key)
            unique.append(requirement)
    return unique


__all__ = ["ACTION_FAMILY_PREDICATES", "OWNER_SUBJECT", "PROJECT_PREDICATES", "derive"]
