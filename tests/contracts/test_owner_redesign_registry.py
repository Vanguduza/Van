"""The redesign contract must stay linked to real routes and authority gates."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(name):
    return json.loads((ROOT / "registries" / name).read_text())


def test_every_owner_feature_and_screen_has_a_resolvable_contract():
    features = read("owner_features.json")["features"]
    screens = read("owner_screens.json")["screens"]
    endpoints = {e["endpoint_id"]: e for e in read("owner_endpoints.json")["endpoints"]}
    by_feature = {f["id"]: f for f in features}
    by_screen = {s["id"]: s for s in screens}
    assert len(by_feature) == len(features) and len(by_screen) == len(screens)
    for f in features:
        assert f["owner_goal"] and f["information"] and f["actions"]
        assert f["required_acceptance_states"]
        assert f["screen_ids"], f"Feature has no redesign surface: {f['id']}"
        assert all(s in by_screen for s in f["screen_ids"])
        for sid in f["screen_ids"]:
            assert f["id"] in by_screen[sid]["feature_ids"]
    for row in features + screens:
        assert row["live_acceptance"] == "UNVERIFIED_IN_THIS_AUDIT"
        for ref in row["endpoint_refs"]:
            real = endpoints[ref["endpoint_id"]]
            assert (ref["method"], ref["path"]) == (real["method"], real["path"])
            assert ref["authentication"] == real["authentication"]
            if real["authentication"].startswith("INTERNAL_CONTROL:"):
                assert ref["frontend_access"] == "HERMES_SERVICE_ONLY"
                assert "internal token" in row["service_access_rule"]
            if real["authentication"].startswith("ATTESTED_ARTIFACT_PROVIDER:"):
                assert ref["frontend_access"] == "ATTESTED_ARTIFACT_PROVIDER_SERVICE_ONLY"
                assert ref["endpoint_id"] in row["service_endpoint_ids"]
                assert ref["endpoint_id"] not in row["owner_endpoint_ids"]
                assert not ref["client_symbol"] and not ref["android_callsites"]
        assert not set(row["owner_endpoint_ids"]) & set(row["service_endpoint_ids"])


def test_missing_and_external_features_cannot_be_presented_as_working():
    features = read("owner_features.json")["features"]
    screens = read("owner_screens.json")["screens"]
    assert any(f["baseline_coverage_status"] == "missing" for f in features)
    assert any(f["baseline_coverage_status"] == "external" for f in features)
    for s in screens:
        if s.get("proposed_route"):
            assert s["route"] is None
            assert s["frontend_integration_status"] == "REQUIRED_REDESIGN_SURFACE"


def test_existing_components_and_required_controls_are_not_fake_routes():
    features = {f["id"]: f for f in read("owner_features.json")["features"]}
    screens = {s["id"]: s for s in read("owner_screens.json")["screens"]}
    for sid, screen in screens.items():
        if sid.startswith("van.trading.") and sid != "van.trading.halt":
            assert screen["host_route"] == "trading"
            assert screen["route"] == screen["nested_route"]
            assert not screen["route"].startswith("trading/")
    halt = screens["van.trading.halt"]
    assert halt["route"] is None and halt["interaction_kind"] == "modal"
    assert halt["host_route"] == "trading"
    intake = screens["van.provisioning"]
    assert intake["route"] is None
    assert intake["interaction_kind"] == "headless_intake_activity"
    assert intake["frontend_integration_status"] == "HEADLESS_INSTALLER_INTAKE"
    assert "van.memory" in features["OF-MEMORY-003"]["screen_ids"]
    assert "van.work" in features["OF-APPROVAL-001"]["screen_ids"]
    intervention = features["OF-MISSION-002"]
    assert intervention["frontend_integration_status"] == "OWNER_CONTROLS_SOURCE_IMPLEMENTED"
    assert intervention["baseline_provenance"]["frontend_integration_status"] == "MISSING_OWNER_CONTROLS"
    assert {c["id"] for c in intervention["current_implementation"]["functions"]} == {
        "OF-MISSION-002:cancel", "OF-MISSION-002:message", "OF-MISSION-002:pause",
        "OF-MISSION-002:resume", "OF-MISSION-002:direction",
    }
    assert all(c["ui_status"] == "SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED" for c in intervention["owner_controls"])


def test_android_callsite_aggregation_preserves_exact_endpoint_and_namespace():
    rows = read("owner_features.json")["features"] + read("owner_screens.json")["screens"]
    for row in rows:
        expected = set()
        for endpoint in row["endpoint_refs"]:
            for citation in endpoint["client_citations"]:
                expected.add((endpoint["endpoint_id"], citation["file"], citation["line"],
                              "gateway_client_declaration", endpoint["client_symbol"]))
            for citation in endpoint["android_callsites"]:
                assert citation["receiver"] and citation["namespace"]
                if citation["invocation_kind"] == "direct_client_method":
                    assert citation["namespace"] == endpoint["client_namespace"]
                    assert citation["symbol"] == endpoint["client_symbol"]
                expected.add((endpoint["endpoint_id"], citation["file"], citation["line"],
                              citation["invocation_kind"], citation["symbol"]))
        actual = {(c["endpoint_id"], c["file"], c["line"], c["kind"], c["symbol"])
                  for c in row["android_callsites"]}
        assert actual == expected, row["id"]


def test_current_owner_surfaces_have_actual_navigation_or_honest_modal_hosts():
    screens = {s["id"]: s for s in read("owner_screens.json")["screens"]}
    expected = {
        "van.reminders.manage": "attention/reminders",
        "van.understanding": "memory/understanding",
        "van.learning.adaptations": "memory/adaptations",
        "van.learning.goals": "memory/goals",
        "van.permissions": "settings/permissions",
        "van.knowledge.sources": "owner/knowledge",
        "van.knowledge.research": "owner/research",
        "van.automation.library": "owner/automation",
        "van.diagnostics": "owner/diagnostics",
        "van.browser.outcome": "owner/browser-outcome/{taskId}",
    }
    nav = (ROOT / "android/app/src/main/java/com/dial/van/command/nav/VanRoute.kt").read_text()
    host = (ROOT / "android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt").read_text()
    import re
    constants = dict(re.findall(r'const val (\w+) = "([^"]+)"', nav))
    registered = set(re.findall(r'composable\(VanRoute\.(\w+)', host))
    for sid, route in expected.items():
        assert screens[sid]["route"] == route
        assert any(value == route and key in registered for key, value in constants.items()), sid
        assert screens[sid]["current_implementation"]["source_citations"]
        assert screens[sid]["live_acceptance"] == "UNVERIFIED_IN_THIS_AUDIT"
    for sid, owner_route, kind in [
        ("van.memory.history", "memory", "modal"),
        ("van.memory.privacy", "memory", "modal"),
        ("van.autonomy", "settings/permissions", "inline_section"),
        ("van.automation.intent", "owner/automation", "inline_section"),
    ]:
        assert screens[sid]["route"] is None
        assert screens[sid]["host_route"] == owner_route
        assert screens[sid]["interaction_kind"] == kind


def test_destructive_erasure_contract_uses_observed_a4_command_instead_of_legacy_delete():
    feature = next(f for f in read("owner_features.json")["features"] if f["id"] == "OF-MEMORY-002")
    deletion = next(e for e in feature["endpoint_refs"] if e["method"] == "DELETE")
    assert deletion["owner_ui_usage"] == "LEGACY_REFUSED_NO_UI_CALLER"
    assert not deletion["android_callsites"]
    erase = next(f for f in feature["current_implementation"]["functions"] if f["id"].endswith(":erase"))
    assert deletion["endpoint_id"] not in erase["endpoint_ids"]
    assert "A4" in erase["authority_gate"] and "biometric" in erase["authority_gate"]
    assert "terminal command success" in erase["authority_gate"]


def test_current_function_citations_and_callsites_are_exact_production_source():
    import hashlib
    import re
    rows = read("owner_features.json")["features"] + read("owner_screens.json")["screens"]
    for row in rows:
        endpoint_ids = {r["endpoint_id"] for r in row["endpoint_refs"]}
        functions = row["current_implementation"]["functions"]
        assert len({f["id"] for f in functions}) == len(functions), row["id"]
        for function in functions:
            assert function["owner_action"] and function["source_citations"]
            assert set(function["endpoint_ids"]) <= endpoint_ids, (row["id"], function["id"])
            for citation in function["source_citations"]:
                if citation["ref"] == "WORKSPACE_PATCH":
                    source = ROOT / citation["file"]
                    assert citation["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
                    assert 0 < citation["line"] <= len(source.read_text().splitlines())
        for endpoint in row["endpoint_refs"]:
            for call in endpoint["android_callsites"]:
                if call["ref"] != "WORKSPACE_PATCH" or call["invocation_kind"] != "direct_client_method":
                    continue
                line = (ROOT / call["file"]).read_text().splitlines()[call["line"] - 1]
                expression = call["receiver"] + "." + call["symbol"]
                if call["receiver"] == "this":
                    expression = call["symbol"]
                assert re.search(re.escape(expression) + r"\s*\(", line), (row["id"], call)
                assert not line.lstrip().startswith(("//", "*"))


def test_browser_current_contract_tracks_approved_effects_and_unbound_external_file_provider():
    screens = {s["id"]: s for s in read("owner_screens.json")["screens"]}
    browser = screens["van.browser.interactive"]
    implementation = browser["current_implementation"]
    assert implementation["control_outcome_guard"] == "LOCAL_GUARD_IMPLEMENTED_REMOTE_ACCEPTANCE_UNVERIFIED"
    assert {f["id"] for f in implementation["functions"]} == {
        "OF-BROWSER-002:viewport", "OF-BROWSER-002:pause", "OF-BROWSER-002:close",
        "OF-BROWSER-002:inventory", "OF-BROWSER-002:resume",
        "OF-BROWSER-003:take-control", "OF-BROWSER-003:delegate-control",
        "OF-BROWSER-004:review-downloads", "OF-BROWSER-004:remove-download-record",
        "OF-BROWSER-004:save-to-phone", "OF-BROWSER-004:upload-from-phone", "OF-BROWSER-004:explicit-clipboard",
        "OF-BROWSER-001:immutable-effect-plan", "OF-BROWSER-003:immutable-effect-plan",
        "OF-BROWSER-004:native-file-operation",
        "OF-BROWSER-004:open-in-van", "OF-BROWSER-004:external-file-contract",
        "OF-BROWSER-004:provider-draft", "OF-BROWSER-004:provider-admission",
        "OF-BROWSER-004:provider-observation",
    }
    assert browser["current_coverage_status"] == "partial"
    assert any("does not prove" in gap and "closure" in gap for gap in browser["gaps"])
    for symbol in ["interactiveBrowserTabs", "interactiveBrowserEvents", "interactiveBrowserDelegateControl", "interactiveBrowserTransferGrant"]:
        endpoint = next(e for e in browser["endpoint_refs"] if e.get("client_symbol") == symbol)
        assert endpoint["android_callsites"], symbol
    assert "EXTERNAL_PROVIDER" in browser["gap_categories"]
    assert browser["functional_wiring_status"] == "EXTERNAL_CONTRACT_OR_ASSET_REQUIRED"
    mutation = next(f for f in implementation["functions"] if f["id"] == "OF-BROWSER-003:immutable-effect-plan")
    assert "A4" in mutation["authority_gate"] and "uncertain" in mutation["authority_gate"]
    assert any("unbound/unqualified" in gap for gap in browser["gaps"])
    assert not read("owner_screens.json")["unhandled_mutations"]
    outcome = screens["van.browser.outcome"]
    assert outcome["current_coverage_status"] == "implemented"
    assert not outcome["missing_presentation_fields"]
    assert any("nullable" in field for field in outcome["information"])
    assert any("digest" in field for field in outcome["information"])
    assert any("postconditions" in field for field in outcome["information"])
    assert outcome["information"] == outcome["displayed_information"]
    downloads = screens["van.browser.downloads"]
    assert downloads["route"] is None and not downloads.get("proposed_route")
    assert downloads["interaction_kind"] == "modal"
    assert downloads["host_activity"] == "com.dial.van.browser.BrowserActivity"
    assert downloads["current_coverage_status"] == "partial"
    functions = downloads["current_implementation"]["functions"]
    assert {function["id"] for function in functions} == {
        "OF-BROWSER-004:review-downloads", "OF-BROWSER-004:remove-download-record",
        "OF-BROWSER-004:save-to-phone", "OF-BROWSER-004:upload-from-phone", "OF-BROWSER-004:explicit-clipboard",
        "OF-BROWSER-004:native-file-operation",
        "OF-BROWSER-004:open-in-van", "OF-BROWSER-004:external-file-contract",
        "OF-BROWSER-004:provider-draft", "OF-BROWSER-004:provider-admission",
        "OF-BROWSER-004:provider-observation",
    }
    removal = next(f for f in functions if f["id"].endswith(":remove-download-record"))
    assert "independent DELETED readback" in removal["authority_gate"]
    assert "does not prove host cleanup" in removal["authority_gate"]
    assert not any("upload" in value.lower() for value in downloads["unavailable_owner_controls"])
    assert downloads["external_provider_contract"]["owner_execution_available"] is False
    assert any("Oracle/VEKL" in value for value in downloads["unavailable_owner_controls"])
    provider = screens["van.browser.file-provider"]
    assert provider["route"] is None and provider["interaction_kind"] == "modal"
    assert provider["host_activity"] == "com.dial.van.browser.BrowserActivity"
    assert {f["id"] for f in provider["current_implementation"]["functions"]} == {
        "OF-BROWSER-004:external-file-contract", "OF-BROWSER-004:provider-draft", "OF-BROWSER-004:provider-admission",
        "OF-BROWSER-004:provider-observation",
    }
    assert provider["external_provider_contract"]["default_state"] == "UNAVAILABLE"
    assert provider["external_provider_contract"]["owner_action"] == {
        "action_id": "browser.file.provider.submit", "action_class": "A4",
        "exact_parameters": ["session_id", "request_id", "request_sha256"], "max_age_seconds": 30,
    }
    happy = downloads["acceptance_states"]["happy"]
    assert "byte/effect readback" in happy["expected"]
    assert happy["required_full_feature_expected"] == downloads["baseline_acceptance_states"]["happy"]
    takeover = next(f for f in implementation["functions"] if f["id"].endswith(":take-control"))
    assert "nondecreasing control generation/viewport revision" in takeover["authority_gate"]
    assert "no older heartbeat replacement" not in takeover["authority_gate"]


def test_file_provider_registry_matches_native_action_scope_without_phone_service_authority():
    from van_gateway.browser.artifact_admission import FILE_PROVIDER_ACTION

    feature = next(f for f in read("owner_features.json")["features"] if f["id"] == "OF-BROWSER-004")
    contract = feature["external_provider_contract"]
    action = contract["owner_action"]
    assert action["action_id"] == FILE_PROVIDER_ACTION.action_id
    assert action["action_class"] == FILE_PROVIDER_ACTION.action_class.value == "A4"
    assert set(action["exact_parameters"]) == set(FILE_PROVIDER_ACTION.parameter_schema["required"])
    assert FILE_PROVIDER_ACTION.parameter_schema["additionalProperties"] is False
    assert action["max_age_seconds"] == FILE_PROVIDER_ACTION.max_age_seconds == 30
    assert contract["production_target_bound"] is contract["production_target_qualified"] is contract["owner_execution_available"] is False
    assert contract["configured_is_qualified"] is False
    assert feature["functional_wiring_status"] == "EXTERNAL_CONTRACT_OR_ASSET_REQUIRED"
    provider_function = next(f for f in feature["current_implementation"]["functions"] if f["id"].endswith(":provider-admission"))
    callbacks = [r for r in feature["endpoint_refs"] if r["authentication"].startswith("ATTESTED_ARTIFACT_PROVIDER:")]
    assert len(callbacks) == 2
    assert {r["endpoint_id"] for r in callbacks} <= set(provider_function["endpoint_ids"])
    assert all(r["endpoint_id"] in feature["service_endpoint_ids"] and r["endpoint_id"] not in feature["owner_endpoint_ids"] for r in callbacks)


def test_voice_registry_distinguishes_actual_generic_runtime_from_owner_speaker_enrollment():
    feature = next(f for f in read("owner_features.json")["features"] if f["id"] == "OF-VOICE-001")
    functions = {f["id"]: f for f in feature["current_implementation"]["functions"]}
    assert "OF-VOICE-001:embedded-generic-voice" in functions
    assert "OF-VOICE-001:bounded-local-endpointing" in functions
    contract = feature["voice_runtime_contract"]
    assert contract["local_endpointing"] == "ACTUAL_ENERGY_VAD_AND_BOUNDED_PCM_TURN"
    assert contract["unused_neural_vad_ready"] is False
    assert contract["owner_speaker_enrollment_available"] is True
    assert contract["actual_owner_profile_observed"] is False
    assert contract["acoustic_model_accuracy_qualification"] == "UNVERIFIED"
    assert contract["owner_embedding_fabricated"] is False
    assert contract["generic_models_grant_owner_identity"] is False
    assert contract["physical_acoustic_qualification"] == "UNVERIFIED"


def test_local_speaker_registry_has_actual_hosted_controls_without_remote_action_authority():
    features = {f["id"]: f for f in read("owner_features.json")["features"]}
    screens = {s["id"]: s for s in read("owner_screens.json")["screens"]}
    feature, panel = features["OF-VOICE-002"], screens["van.settings.speaker-profile"]
    expected = {"OF-VOICE-002:local-owner-enrollment", "OF-VOICE-002:local-profile-readback", "OF-VOICE-002:local-profile-erasure"}
    assert {f["id"] for f in feature["current_implementation"]["functions"]} == expected
    assert {f["id"] for f in panel["current_implementation"]["functions"]} == expected
    assert panel["route"] is None and panel["host_route"] == "settings/voice"
    assert panel["component"] == "SpeakerEnrollmentPanel"
    assert not panel["endpoint_refs"] and not panel["service_endpoint_ids"]
    source = (ROOT / "android/app/src/main/java/com/dial/van/voice/SpeakerEnrollmentPanel.kt").read_text()
    for tag in panel["test_tags"]:
        assert f'"{tag}"' in source, tag
    contract = feature["speaker_profile_contract"]
    assert contract["consent_purpose"] == "van.local-speaker-profile"
    assert contract["consent_max_age_ms"] == 30_000
    assert contract["required_clips"] == 3 and contract["capture_sample_rate_hz"] == 16_000
    assert contract["stored_raw_audio"] is contract["actual_owner_profile_observed"] is False
    assert contract["speaker_similarity_grants_action_authority"] is False
    assert contract["physical_capture_qualification"] == contract["speaker_discrimination_qualification"] == "UNVERIFIED"
    erasure = next(f for f in feature["current_implementation"]["functions"] if f["id"].endswith(":local-profile-erasure"))
    assert "genuine local" in erasure["authority_gate"] and "without inventing" in erasure["authority_gate"]
    assert "independently read back absent" in erasure["authority_gate"]
    assert "offline backend failure" in feature["required_acceptance_states"]["offline"]


def test_provider_observation_registry_keeps_original_uncertainty_and_replacement_fence():
    feature = next(f for f in read("owner_features.json")["features"] if f["id"] == "OF-BROWSER-004")
    function = next(f for f in feature["current_implementation"]["functions"] if f["id"].endswith(":provider-observation"))
    endpoint = next(e for e in feature["endpoint_refs"] if e.get("client_symbol") == "browserFileProviderObservation")
    assert endpoint["method"] == "GET" and endpoint["path"].endswith("/file-provider-requests/{request_id}/observation")
    assert endpoint["frontend_access"] == "DIRECT_OWNER_ROUTE"
    assert function["endpoint_ids"] == [endpoint["endpoint_id"]]
    assert "STILL_UNKNOWN" in function["authority_gate"]
    assert "no replacement-fence release" in function["authority_gate"]
    assert "no old canonical UNKNOWN/UNVERIFIABLE promotion" in function["authority_gate"]
    assert "five-minute read-only observation scope" in function["authority_gate"]
    assert endpoint["android_callsites"]


def test_trading_ticket_surfaces_preserve_exact_receipt_authority_and_real_route():
    screens = {s["id"]: s for s in read("owner_screens.json")["screens"]}
    tickets = screens["van.trading.tickets"]
    assert tickets["route"] == tickets["nested_route"] == "tickets"
    assert tickets["host_route"] == "trading"
    confirmation = screens["van.approval.trading-ticket"]
    assert confirmation["route"] is None and confirmation["interaction_kind"] == "modal"
    action = next(f for f in confirmation["current_implementation"]["functions"] if f["id"].endswith(":confirm-fill"))
    assert "A4" in action["authority_gate"] and "biometric" in action["authority_gate"]
    assert "never executes an order" in action["authority_gate"]
    assert not confirmation["service_endpoint_ids"]


def test_current_registry_binds_current_review_and_keeps_local_vs_external_qualification_separate():
    import hashlib

    feature_doc = read("owner_features.json")
    screen_doc = read("owner_screens.json")
    features = {f["id"]: f for f in feature_doc["features"]}
    for document in (feature_doc, screen_doc):
        qualification = document["current_source_qualification"]
        review = ROOT / qualification["source_review_manifest"]
        assert qualification["source_review_manifest_sha256"] == hashlib.sha256(review.read_bytes()).hexdigest()
        assert qualification["physical_cases_executed"] == 0
        assert qualification["owner_release"] is False and qualification["deployment_accepted"] is False
        if qualification["status"] == "SOURCE_REVIEWED_LOCAL_VALIDATION_PASSED":
            manifest = ROOT / qualification["source_freeze_manifest"]
            assert qualification["source_freeze_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
            receipt = ROOT / qualification["android_receipt"]
            assert qualification["android_receipt_sha256"] == hashlib.sha256(receipt.read_bytes()).hexdigest()
        else:
            assert qualification["status"] == "SOURCE_REVIEWED_FINAL_VALIDATION_PENDING"
            assert qualification["android_receipt"] is None
    ceiling = features["OF-AUTHORITY-001"]
    change = next(f for f in ceiling["current_implementation"]["functions"] if f["id"].endswith(":set-domain-ceiling"))
    assert "A4" in change["authority_gate"] and "S0..S4" in change["authority_gate"]
    grant = next(f for f in ceiling["current_implementation"]["functions"] if f["id"].endswith(":grant-exact-consent"))
    assert "A4" in grant["authority_gate"] and "use limit" in grant["authority_gate"]
    assert ceiling["functional_wiring_status"] == "SOURCE_WIRED_REQUIRES_ACCEPTANCE"
    learning = features["OF-LEARNING-001"]
    for suffix in (":define-vocabulary", ":set-collaboration-preference"):
        action = next(f for f in learning["current_implementation"]["functions"] if f["id"].endswith(suffix))
        assert "owner" in action["authority_gate"] and "session/epoch" in action["authority_gate"]
    for identity in ("OF-BROWSER-001", "OF-LEARNING-003", "OF-AUTOMATION-001"):
        assert features[identity]["functional_wiring_status"] == "SOURCE_WIRED_REQUIRES_ACCEPTANCE"
    for row in feature_doc["features"] + screen_doc["screens"]:
        verification = row["current_implementation"]["verification"]
        assert verification["device_live"] == "UNVERIFIED"
        assert verification["deployment_live"] == "UNVERIFIED"
        history = row.get("historical_source_state")
        if history:
            path = ROOT / history["registry_snapshot"]
            assert history["registry_snapshot_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
