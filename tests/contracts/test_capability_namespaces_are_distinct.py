"""Three vocabularies that look like one, and the mistake of merging them.

`registries/capabilities.json` declares capability ids the router may route to.
`audit.record(capability=...)` takes a label describing what happened. They are spelled
the same way — dotted, lowercase, `browser.interactive.create` — and they are not the same
namespace.

This file exists because the resemblance is actively misleading. Sweeping the Gateway for
`capability="..."` finds fourteen strings the registry does not declare, which looks
exactly like the P0 that made every Mission-bound browser session a 500: a capability the
router needed and nobody had declared. It is not that. Those fourteen are audit labels,
and "fixing" them by declaring them would make fourteen descriptions of past events into
routable capabilities that nothing implements — the same defect, facing the other way.

There is a third, found while writing this file: `CAPABILITY = "stagehand"` and its three
siblings in the adapters and the n8n client are *runtime names* — which adapter handled
something. They are single words with no dot, and that turns out to be the only thing
telling the three apart in source.

So the rules are written down and checked:

* every **dotted** capability id the router can be asked for is declared, which is the
  P0's rule;
* an audit label is not required to be, and the set that is not is named here, so adding
  one is a deliberate act rather than a thing that drifts in;
* a runtime name is neither, and the dot is the discriminator.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "registries/capabilities.json"
GATEWAY = ROOT / "backend/van_gateway"

#: Audit labels the Gateway records that are deliberately not routing capabilities.
#:
#: Each is a description of something that happened — a session ended, a download was
#: quarantined, a provisioning payload was issued. None is a thing a planner can ask for,
#: and declaring one would make it look like it is.
AUDIT_ONLY_LABELS = frozenset({
    "browser.download.delete",
    "browser.download.quarantine",
    "browser.interactive.create",
    "browser.interactive.end",
    "context.export",
    "context.memory.forget",
    "context.owner_fact.forget",
    "context.owner_fact.state",
    "device.bootstrap.attest",
    "device.bootstrap.create",
    "device.provisioning.issue",
    "device.rebind",
    "trading.owner_halt",
    "trading.ticket_confirm",
})


def _declared() -> set[str]:
    doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
    key = next(
        k for k, v in doc.items()
        if isinstance(v, list) and v and isinstance(v[0], dict) and "capability_id" in v[0]
    )
    return {c["capability_id"] for c in doc[key]}


def _audit_labels() -> set[str]:
    labels: set[str] = set()
    for path in GATEWAY.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        labels |= set(re.findall(r'capability="([a-z0-9_.]+)"', text))
    return labels


def test_the_two_vocabularies_are_written_down_and_still_agree():
    """The audit labels that are not routing capabilities, named.

    Named rather than counted, so that adding one is a deliberate edit to this list and
    not something that drifts in — and so that the next person to sweep for
    `capability="..."` finds this file before concluding fourteen things are undeclared.
    """
    labels = _audit_labels()
    declared = _declared()
    assert AUDIT_ONLY_LABELS <= labels, sorted(AUDIT_ONLY_LABELS - labels)
    assert (labels - declared) == AUDIT_ONLY_LABELS, {
        "not in the list": sorted(labels - declared - AUDIT_ONLY_LABELS),
        "in the list and no longer recorded": sorted(AUDIT_ONLY_LABELS - labels),
    }


def test_a_runtime_adapter_name_is_not_mistaken_for_a_capability():
    """The third vocabulary, pinned by the one property that separates it.

    `CAPABILITY = "stagehand"` names which adapter ran. If one of these ever gained a dot
    it would start reading as a capability id, and the check above would demand it be
    declared — so this fails first, and says why.
    """
    undotted: set[str] = set()
    for path in GATEWAY.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        undotted |= {
            value for value in re.findall(r'\w*CAPABILITY\w*\s*=\s*"([a-z0-9_.]+)"', text)
            if "." not in value
        }
    assert undotted == {"n8n", "worker", "browser_harness", "stagehand"}, sorted(undotted)
    assert not (undotted & _declared())


def test_no_audit_only_label_is_also_a_declared_capability():
    """The two sets are disjoint, which is what makes the distinction usable.

    A string that is both would be ambiguous at every call site: the reader could not tell
    whether the Gateway was routing to something or describing something it had done.
    """
    overlap = AUDIT_ONLY_LABELS & _declared()
    assert overlap == set(), sorted(overlap)


def test_every_capability_the_router_can_be_asked_for_is_declared():
    """P0's rule, restated as a live check rather than as a memory.

    `browser.interactive.session` was needed by the Mission binder and declared by nobody,
    so every Mission-bound browser session was a 500 — the route existed, the binder
    existed, and the capability between them did not. `registry.require` raises
    `CAPABILITY_NOT_DECLARED`, which is the right refusal and arrives at runtime.
    """
    declared = _declared()
    asked: set[str] = set()
    for path in GATEWAY.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        # A literal handed to `require`, and the constants that hold one. The second
        # form is how the P0's id is actually written — `INTERACTIVE_BROWSER_CAPABILITY`
        # in `mission/binding.py` — and a check that matched only the call site would
        # have found nothing and passed, which is the shape of vacuous test this
        # programme keeps finding.
        asked |= set(re.findall(r'\.require\(\s*"([a-z0-9_.]+)"\s*\)', text))
        asked |= {
            value for value in
            re.findall(r'\w*CAPABILITY\w*\s*=\s*"([a-z0-9_.]+)"', text)
            # Dotted, because an undotted `CAPABILITY = "stagehand"` is an adapter's
            # runtime name rather than a capability id. The dot is the only thing that
            # distinguishes the three vocabularies in source, which is worth knowing
            # before anyone tries to unify them.
            if "." in value
        }
    assert asked, "nothing names a capability id as a literal any more"
    assert asked <= declared, sorted(asked - declared)


def test_the_browser_session_capability_is_still_declared():
    """The specific one, by name, because it is the one that was missing.

    A general rule passes when nothing looks anything up. This fails if the declaration
    that closed the P0 is removed, whatever else changes.
    """
    assert "browser.interactive.session" in _declared()
