"""Programme B contract B2 — browser privacy eligibility (``browser/jev_eligibility.py``).

Two fixture sets, both FIXTURE corpora (not live measurements):

* ``dds57-inputs.v1.json`` — reconstructed inputs for the 57 fixtures of the DDS export
  ``dds-browser-payload-corpus.v1.json`` (vendored byte-for-byte from DDS 39d3777, blob
  90b1436c…). The classifier must reproduce every fixture's class, data class, reasons and
  payload; target ids and epochs are random per observation, so the payload comparison
  is exact after replacing those opaque ids positionally, and the whole export is then
  byte-compared with the DDS file.
* ``adversarial.v1.json`` — the extra adversarial set, kept separate so the 57-fixture
  export stays byte-comparable.

Schema validity is checked by a small in-repo interpreter of the vendored DDS schema
(``browser-action-payload.v1.schema.json``, DDS blob 3740580…). ``jsonschema`` is not a VAN
dependency and none is added; the interpreter refuses any keyword it does not implement.

Export mode: ``VAN_JEV_B2_EXPORT=<path>`` writes the 57-fixture corpus in the DDS format
(``tests/fixtures/jev/browser-payload-corpus.v1.json``), with this run's fresh opaque ids.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections import Counter
from pathlib import Path

import pytest

from van_gateway.automation.policy import load_browser_policy
from van_gateway.browser import jev_eligibility as je
from van_gateway.browser.jev_eligibility import (
    EligibilityClass,
    JevEligibilityPolicy,
    JevPageObservation,
    ObservedElement,
    classify_observation,
    payload_violations,
    private_data_findings,
    withheld_reason,
)
from van_gateway.browser.models import BrowserObservation, InjectionAssessment
from van_gateway.models import ActionClass

FIXTURES = Path(__file__).parent / "fixtures" / "browser_jev"
INPUTS = json.loads((FIXTURES / "dds57-inputs.v1.json").read_text(encoding="utf-8"))
ADVERSARIAL = json.loads((FIXTURES / "adversarial.v1.json").read_text(encoding="utf-8"))
DDS_EXPORT_PATH = FIXTURES / "dds-browser-payload-corpus.v1.json"
DDS_EXPORT = json.loads(DDS_EXPORT_PATH.read_text(encoding="utf-8"))
SCHEMA_PATH = FIXTURES / "browser-action-payload.v1.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
DDS_BLOBS = {
    SCHEMA_PATH: ("374058016454b2bd8b12c858c6b27be23952d49a", "agent-system/schemas/jev/browser-action-payload.v1.schema.json"),
    DDS_EXPORT_PATH: ("90b1436c3de78b9ab4f74638ca1437a1802a730d", "tests/fixtures/jev/browser-payload-corpus.v1.json"),
}
DDS_COMMIT = "39d3777"
OPS = INPUTS["call"]["closed_operation_set"]
CEILING = INPUTS["call"]["action_class_ceiling"]
ELIGIBLE = {EligibilityClass.PUBLIC_ELIGIBLE, EligibilityClass.SANITIZABLE_ELIGIBLE}
PRIVACY = {EligibilityClass.OWNER_PRIVATE, EligibilityClass.CREDENTIAL, EligibilityClass.TRADING_PROTECTED}


def _policy(**overrides) -> JevEligibilityPolicy:
    base = dict(
        browser_policy=load_browser_policy(),
        public_allowlist=frozenset(INPUTS["policy"]["public_allowlist"]),
        owner_private_terms=tuple(INPUTS["policy"]["owner_private_terms"]),
    )
    base.update(overrides)
    return JevEligibilityPolicy(**base)


def _observation(fx: dict) -> JevPageObservation:
    if "repeat_elements" in fx:
        spec = fx["repeat_elements"]
        raw = [{"role": spec["role"], "label": spec["label"].format(i=i + 1)} for i in range(spec["count"])]
    else:
        raw = fx["elements"]
    elements = tuple(
        ObservedElement(ref=e.get("ref", f"el-{i}"), **{k: v for k, v in e.items() if k != "ref"})
        for i, e in enumerate(raw)
    )
    return JevPageObservation(
        url=fx["url"],
        profile_alias=fx.get("profile_alias", "public_research"),
        authenticated=fx.get("authenticated", False),
        cookies_present=fx.get("cookies_present", False),
        elements=elements,
        page_title=fx.get("page_title", ""),
        injection_assessment=InjectionAssessment(fx.get("injection", "NONE_DETECTED")),
    )


def _classify(fx: dict, *, policy: JevEligibilityPolicy | None = None, ceiling=CEILING, ops=OPS):
    return classify_observation(_observation(fx), closed_operation_set=ops, action_class_ceiling=ceiling,
                                policy=policy or _policy())


DDS57 = {fx["fixture"]: (fx, _classify(fx)) for fx in INPUTS["fixtures"]}
ADV = {fx["fixture"]: (fx, _classify(fx)) for fx in ADVERSARIAL["fixtures"]}
ALL = {**DDS57, **ADV}


# ------------------------------------------------------------------------ export


def _metrics(results) -> dict:
    per_class = Counter(r.eligibility_class.value for _, r in results)
    total = len(results)
    eligible = per_class["PUBLIC_ELIGIBLE"] + per_class["SANITIZABLE_ELIGIBLE"]
    return {
        "eligibility_rate": round(eligible / total, 4),
        "eligible": eligible,
        "measurement_kind": "FIXTURE_CORPUS_NOT_LIVE",
        "per_class": {c.value: per_class[c.value] for c in EligibilityClass if per_class[c.value]},
        "policy_rejection_rate": round(per_class["POLICY_DENIED"] / total, 4),
        "privacy_rejection_rate": round(sum(per_class[c.value] for c in PRIVACY) / total, 4),
        "total": total,
    }


def build_export(results=None) -> dict:
    results = list((results or DDS57).values())
    return {
        "corpus": INPUTS["corpus"],
        "fixtures": [
            {
                "category": fx["category"], "data_class": r.data_class, "eligibility": r.eligibility_class.value,
                "expected": fx["expected"], "fixture": fx["fixture"], "jev_payload": r.jev_payload,
                "reasons": list(r.reasons),
            }
            for fx, r in results
        ],
        "metrics": _metrics(results),
        "module": INPUTS["module"],
    }


def dump_export(export: dict) -> str:
    # The DDS file's exact serialisation: sorted keys, 2-space indent, ASCII escapes, final newline.
    return json.dumps(export, indent=2, sort_keys=True) + "\n"


def _with_ids_from(export: dict, reference: dict) -> dict:
    """Replace opaque ids (target_id, observation_epoch) positionally with the reference's."""
    out = json.loads(json.dumps(export))
    for mine, ref in zip(out["fixtures"], reference["fixtures"]):
        p, q = mine["jev_payload"], ref["jev_payload"]
        if p is None or q is None or len(p["targets"]) != len(q["targets"]):
            continue
        p["observation_epoch"] = q["observation_epoch"]
        for t, u in zip(p["targets"], q["targets"]):
            t["target_id"] = u["target_id"]
    return out


def test_export_mode_writes_dds_format():
    target = os.environ.get("VAN_JEV_B2_EXPORT")
    export = build_export()
    if target:
        Path(target).write_text(dump_export(export), encoding="utf-8")
    assert set(export) == set(DDS_EXPORT)
    assert [set(f) for f in export["fixtures"]] == [set(f) for f in DDS_EXPORT["fixtures"]]


# -------------------------------------------------------------- DDS reproduction


def test_vendored_dds_files_are_the_audited_blobs():
    for path, (blob, _) in DDS_BLOBS.items():
        out = subprocess.run(["git", "hash-object", str(path)], capture_output=True, text=True, check=True)
        assert out.stdout.strip() == blob, path.name
    dds = Path(os.environ.get("DIAL_DDS_ROOT", "/home/user/dial-development-system"))
    if not (dds / ".git").exists():
        pytest.skip("DDS checkout not present; blob hashes pinned above")
    for path, (blob, rel) in DDS_BLOBS.items():
        got = subprocess.run(["git", "-C", str(dds), "rev-parse", f"{DDS_COMMIT}:{rel}"], capture_output=True, text=True)
        assert got.returncode == 0 and got.stdout.strip() == blob, rel


def test_inputs_cover_exactly_the_dds_fixtures_in_order():
    assert [f["fixture"] for f in INPUTS["fixtures"]] == [f["fixture"] for f in DDS_EXPORT["fixtures"]]
    assert [f["category"] for f in INPUTS["fixtures"]] == [f["category"] for f in DDS_EXPORT["fixtures"]]
    assert [f["expected"] for f in INPUTS["fixtures"]] == [f["expected"] for f in DDS_EXPORT["fixtures"]]


@pytest.mark.parametrize("index", range(len(DDS_EXPORT["fixtures"])), ids=[f["fixture"] for f in DDS_EXPORT["fixtures"]])
def test_each_dds_fixture_is_reproduced(index):
    want = DDS_EXPORT["fixtures"][index]
    fx, r = DDS57[want["fixture"]]
    assert r.eligibility_class.value == want["eligibility"], (want["fixture"], r.reasons)
    assert r.data_class == want["data_class"]
    assert list(r.reasons) == want["reasons"], want["fixture"]
    if want["jev_payload"] is None:
        assert r.jev_payload is None
        return
    mine = _with_ids_from({"fixtures": [{"jev_payload": r.jev_payload}]}, {"fixtures": [want]})["fixtures"][0]["jev_payload"]
    assert mine == want["jev_payload"], want["fixture"]
    # the replaced ids were well-formed and unique in their own right
    assert re.fullmatch(r"e_[0-9a-f]{16}", r.jev_payload["observation_epoch"])
    ids = [t["target_id"] for t in r.jev_payload["targets"]]
    assert len(set(ids)) == len(ids) and all(re.fullmatch(r"t_[0-9a-f]{16}", i) for i in ids)


def test_fresh_export_is_byte_identical_to_dds_modulo_opaque_ids():
    fresh = build_export()
    assert fresh["metrics"] == DDS_EXPORT["metrics"]
    assert dump_export(_with_ids_from(fresh, DDS_EXPORT)) == DDS_EXPORT_PATH.read_text(encoding="utf-8")
    # and without the substitution the only differences are the opaque ids
    raw, ref = dump_export(fresh).splitlines(), DDS_EXPORT_PATH.read_text(encoding="utf-8").splitlines()
    assert len(raw) == len(ref)
    diff = [(a, b) for a, b in zip(raw, ref) if a != b]
    assert diff and all(re.search(r'"(?:target_id|observation_epoch)": "[te]_[0-9a-f]{16}"', a) for a, _ in diff)


# ------------------------------------------------------------- adversarial set


@pytest.mark.parametrize("fixture_id", list(ADV))
def test_adversarial_fixture(fixture_id):
    fx, r = ADV[fixture_id]
    assert r.eligibility_class.value == fx["expected"], (fixture_id, r.reasons)
    for reason in fx.get("expect_reasons", []):
        assert reason in r.reasons, (fixture_id, r.reasons)


def test_both_sets_cover_every_class():
    assert {r.eligibility_class for _, r in DDS57.values()} == set(EligibilityClass)
    assert {r.eligibility_class for _, r in ADV.values()} >= ELIGIBLE | {EligibilityClass.POLICY_DENIED,
                                                                         EligibilityClass.OWNER_PRIVATE,
                                                                         EligibilityClass.CREDENTIAL}


# ------------------------------------------------------------- vendored schema check

_SUPPORTED_KEYWORDS = {
    "$schema", "$id", "title", "description", "type", "additionalProperties", "required",
    "properties", "const", "enum", "items", "minItems", "maxItems", "uniqueItems", "pattern",
    "minLength", "maxLength",
}


def schema_errors(instance, schema=SCHEMA, path="$") -> list[str]:
    unknown = set(schema) - _SUPPORTED_KEYWORDS
    if unknown:
        raise AssertionError(f"schema keyword(s) not implemented by the test validator: {sorted(unknown)}")
    errs: list[str] = []
    t = schema.get("type")
    types = {"object": dict, "array": list, "string": str}
    if t is not None and not isinstance(instance, types[t]):
        return [f"{path}: type {t}"]
    if "const" in schema and instance != schema["const"]:
        errs.append(f"{path}: const")
    if "enum" in schema and instance not in schema["enum"]:
        errs.append(f"{path}: enum")
    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            errs.append(f"{path}: minLength")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errs.append(f"{path}: maxLength")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errs.append(f"{path}: pattern")
    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            errs.append(f"{path}: minItems")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errs.append(f"{path}: maxItems")
        if schema.get("uniqueItems") and len({json.dumps(i, sort_keys=True) for i in instance}) != len(instance):
            errs.append(f"{path}: uniqueItems")
        for i, item in enumerate(instance):
            errs += schema_errors(item, schema.get("items", {}), f"{path}[{i}]")
    if isinstance(instance, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in instance:
                errs.append(f"{path}: required {key}")
        if schema.get("additionalProperties") is False:
            for key in set(instance) - set(props):
                errs.append(f"{path}: additional {key}")
        for key, sub in props.items():
            if key in instance:
                errs += schema_errors(instance[key], sub, f"{path}.{key}")
    return errs


def test_schema_validator_is_live():
    good = DDS57["pub-01"][1].jev_payload
    assert schema_errors(good) == []
    renamed = {**good, "targets": [{"target_id": t["target_id"], "role": t["role"], "name": t["label"]} for t in good["targets"]]}
    assert schema_errors(renamed)
    assert schema_errors({**good, "url": "https://example.com/?q=1"})
    assert schema_errors({**good, "targets": [{**good["targets"][0], "target_id": "t_XYZ"}]})
    assert schema_errors({**good, "action_class_ceiling": "A4"})
    assert schema_errors({**good, "targets": [{**good["targets"][0], "label": "x" * 65}]})
    assert schema_errors({**good, "targets": good["targets"][:1] * 41})
    assert schema_errors({**good, "closed_operation_set": ["click", "click"]})


def test_module_constants_mirror_schema():
    p = SCHEMA["properties"]
    t = p["targets"]["items"]["properties"]
    assert p["payload_schema"]["const"] == je.PAYLOAD_SCHEMA
    assert p["effect_direction"]["const"] == je.EFFECT_DIRECTION
    assert tuple(p["closed_operation_set"]["items"]["enum"]) == je.CLOSED_OPERATIONS
    assert tuple(p["origin_class"]["enum"]) == je.ORIGIN_CLASSES
    assert tuple(p["action_class_ceiling"]["enum"]) == je.CEILINGS
    assert set(t["role"]["enum"]) == je.ALLOWED_ROLES
    assert p["targets"]["maxItems"] == je.MAX_TARGETS
    assert t["label"]["maxLength"] == je.MAX_LABEL_LEN
    assert t["target_id"]["pattern"] == je.TARGET_ID_RE.pattern
    assert p["observation_epoch"]["pattern"] == je.EPOCH_RE.pattern
    assert set(SCHEMA["required"]) == je.PAYLOAD_KEYS == set(p)
    assert set(p["targets"]["items"]["required"]) == je.TARGET_KEYS


# ---------------------------------------------------------------- payload checks

#: Python restatement of DDS data-classification.mjs / data-policy.mjs key rules and the
#: van.browser.ultrafast.action.v1 prohibited fields, independent of the module under test.
_DDS_IDENTIFIER_KEY = re.compile(r"(?:^|_)(?:name|full_name|email|phone|mobile|address|street|passport|national_id|customer_id|employee_id|patient_id|card_number|bank_account|latitude|longitude|gps)(?:$|_)", re.I)
_DDS_TIMESTAMP_KEY = re.compile(r"(?:^|_)(?:timestamp|occurred_at|created_at|updated_at|event_time|datetime)(?:$|_)", re.I)
_DDS_PROHIBITED = {"token", "password", "secret", "credential", "private_key", "session_cookie", "card_number", "bank_account"}
_DDS_SECRETS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{12,}\b", re.I),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:API_KEY|ACCESS_TOKEN|REFRESH_TOKEN|CLIENT_SECRET|PASSWORD|SIGNING_KEY)\b\s*[=:]\s*[^\s,;]+", re.I),
]
#: The DDS privacy test's independent value scan, plus URL/selector and invisible-char shapes.
_INDEPENDENT_PRIVATE_VALUE = [
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"(?<![\w.])@[A-Za-z0-9_]{2,}"),
    re.compile(r"\d[\d \-.()]{3,}\d"),
    re.compile(r"\b\d{1,2}:\d{2}\b"),
    re.compile(r"\b(?:pass(?:word|code)|otp|one[- ]time|verification code|cvv|cvc|card number|expiry|iban|sort code)\b", re.I),
    re.compile(r"\b(?:stop[- ]?loss|take[- ]?profit|leverage|market order|limit order)\b", re.I),
    re.compile(r"https?://|www\.|\?[a-z]+=|xpath=", re.I),
    re.compile(r"[​-‏‪-‮⁠-⁤﻿]"),
]


def _dds_key_violations(value, path="$") -> list[str]:
    out = []
    if isinstance(value, list):
        for i, v in enumerate(value):
            out += _dds_key_violations(v, f"{path}[{i}]")
    elif isinstance(value, dict):
        for k, v in value.items():
            if _DDS_IDENTIFIER_KEY.search(k) or k in _DDS_PROHIBITED or _DDS_TIMESTAMP_KEY.search(k):
                out.append(f"{path}.{k}")
            out += _dds_key_violations(v, f"{path}.{k}")
    return out


def _eligible():
    return [(fx, r) for fx, r in ALL.values() if r.eligibility_class in ELIGIBLE]


def test_every_emitted_payload_is_schema_valid_and_egress_clean():
    eligible = _eligible()
    assert len(eligible) >= 12
    for fx, r in eligible:
        p = r.jev_payload
        assert schema_errors(p) == [], (fx["fixture"], schema_errors(p))
        assert payload_violations(p) == [], fx["fixture"]
        assert _dds_key_violations(p) == [], fx["fixture"]
        assert not any(rx.search(json.dumps(p)) for rx in _DDS_SECRETS), fx["fixture"]
        assert r.data_class == ("PUBLIC" if r.eligibility_class is EligibilityClass.PUBLIC_ELIGIBLE else "INTERNAL_SANITIZED")


def test_independent_value_scan_of_every_emitted_label():
    for fx, r in _eligible():
        for t in r.jev_payload["targets"]:
            for rx in _INDEPENDENT_PRIVATE_VALUE:
                assert not rx.search(t["label"]), (fx["fixture"], t["label"], rx.pattern)
            for term in INPUTS["policy"]["owner_private_terms"]:
                assert term.lower() not in t["label"].lower(), fx["fixture"]


def test_payload_carries_no_url_host_ref_title():
    for fx, r in _eligible():
        blob = json.dumps(r.jev_payload, ensure_ascii=False)
        host = re.sub(r"^https?://", "", fx["url"]).split("/")[0]
        assert host not in blob and fx["url"] not in blob, fx["fixture"]
        for ref in r.target_map.values():
            assert f'"{ref}"' not in blob, fx["fixture"]
        assert set(r.target_map) == {t["target_id"] for t in r.jev_payload["targets"]}
        assert r.jev_payload["observation_epoch"] == r.observation_epoch
        if fx.get("page_title"):
            assert fx["page_title"] not in blob


def test_every_ineligible_fixture_emits_nothing_and_reasons_are_codes_only():
    blocked = [(fx, r) for fx, r in ALL.values() if r.eligibility_class not in ELIGIBLE]
    assert blocked
    for fx, r in blocked:
        assert r.jev_payload is None and r.target_map == {} and r.data_class is None, fx["fixture"]
        assert r.reasons and r.observation_epoch, fx["fixture"]
        for reason in r.reasons:  # never a URL, host, label or title fragment
            assert re.fullmatch(r"[A-Z0-9_]+(?::[A-Z0-9_,]+)?", reason), (fx["fixture"], reason)


def test_target_ids_and_epochs_are_fresh_per_observation():
    fx = DDS57["pub-01"][0]
    a, b = _classify(fx), _classify(fx)
    assert a.observation_epoch != b.observation_epoch
    assert not set(a.target_map) & set(b.target_map)
    assert sorted(a.target_map.values()) == sorted(b.target_map.values())


# ------------------------------------------------------------------ default deny


def test_default_policy_admits_no_public_allowlisted_origin():
    r = _classify(DDS57["pub-01"][0], policy=_policy(public_allowlist=frozenset()))
    assert r.eligibility_class is EligibilityClass.SANITIZABLE_ELIGIBLE
    assert r.jev_payload["origin_class"] == "PUBLIC_UNLISTED"
    assert JevEligibilityPolicy().public_allowlist == frozenset()


def test_existing_browser_observation_model_is_denied():
    obs = BrowserObservation(task_id="t1", controls=[{"role": "button", "label": "Search"}])
    r = classify_observation(obs, closed_operation_set=OPS, action_class_ceiling="A1")
    assert r.eligibility_class is EligibilityClass.POLICY_DENIED
    assert r.reasons == ("AMBIGUOUS_OBSERVATION_TYPE",)


@pytest.mark.parametrize("ceiling", ["A4", "A5", ActionClass.A4, ActionClass.A5, "A9", None, "a1"])
def test_ceiling_outside_a0_a3_is_refused(ceiling):
    r = _classify(DDS57["pub-01"][0], ceiling=ceiling)
    assert r.eligibility_class is EligibilityClass.POLICY_DENIED and r.jev_payload is None
    # the ceiling guard itself, not the payload self-check behind it, must refuse
    assert r.reasons == ("POLICY_ACTION_CLASS_CEILING",)


def test_action_class_enum_ceiling_is_accepted():
    assert _classify(DDS57["pub-01"][0], ceiling=ActionClass.A2).jev_payload["action_class_ceiling"] == "A2"


@pytest.mark.parametrize("ops", [[], ["click", "execute_js"], "click", None, ["navigate"]])
def test_operation_set_outside_closed_set_is_refused(ops):
    r = _classify(DDS57["pub-01"][0], ops=ops)
    assert r.eligibility_class is EligibilityClass.POLICY_DENIED


def test_duplicate_operations_are_collapsed_for_unique_items():
    r = _classify(DDS57["pub-01"][0], ops=["click", "click", "done"])
    assert r.jev_payload["closed_operation_set"] == ["click", "done"]


def test_payload_violations_catches_tampering():
    good = DDS57["pub-01"][1].jev_payload
    assert payload_violations(good) == []
    assert payload_violations({**good, "url": "https://x"})
    assert payload_violations({**good, "targets": [{"target_id": "t_0123456789abcdef", "role": "button", "name": "x"}]})
    assert payload_violations({**good, "targets": [{"target_id": "sel:#btn", "role": "button", "label": "x"}]})
    assert payload_violations({**good, "observation_epoch": "2026-09-29T10:00:00Z"})
    assert payload_violations({**good, "targets": [{"target_id": "t_0123456789abcdef", "role": "button", "label": "Bearer abcdefghijklmnop"}]})


def test_withheld_reason_and_private_findings_units():
    el = lambda **kw: ObservedElement(ref="r", **{"role": "link", **kw})  # noqa: E731
    assert withheld_reason(el(label="Home")) is None
    assert withheld_reason(el(label="login")) == "AUTH_ENTRYPOINT"
    assert withheld_reason(el(label="Ѕearch")) == "LABEL_OBFUSCATED"
    assert withheld_reason(el(label="example[.]com")) == "URL_IN_LABEL"
    assert withheld_reason(el(label="x", role="treeitem")) == "ROLE_UNKNOWN"
    assert private_data_findings("jane (at) example (dot) org") == ["EMAIL"]
    assert private_data_findings("٠٧٩٤٦٠") == ["DIGIT_RUN"]
    assert private_data_findings("Glacier mass balance") == []


# ------------------------------------------------------------------------- stats


def test_corpus_stats(capsys):
    dds = _metrics(list(DDS57.values()))
    adv = _metrics(list(ADV.values()))
    both = _metrics(list(ALL.values()))
    assert dds == DDS_EXPORT["metrics"]
    for m in (dds, adv, both):
        assert sum(m["per_class"].values()) == m["total"]
    with capsys.disabled():
        print("\nB2 FIXTURE corpus stats (not a live measurement)")
        for name, m in (("dds57", dds), ("adversarial", adv), ("combined", both)):
            print(f"  {name}:", json.dumps(m, sort_keys=True))
