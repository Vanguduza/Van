"""Keep production HTTPS-only and the debug exception restricted to exact loopback hosts."""
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "android/app/src"
ANDROID = "{http://schemas.android.com/apk/res/android}"


def test_main_manifest_binds_an_explicit_cleartext_off_policy():
    app = ET.parse(SRC / "main/AndroidManifest.xml").getroot().find("application")
    assert app.get(ANDROID + "usesCleartextTraffic") == "false"
    assert app.get(ANDROID + "networkSecurityConfig") == "@xml/network_security_config"
    policy = ET.parse(SRC / "main/res/xml/network_security_config.xml").getroot()
    assert policy.find("base-config").get("cleartextTrafficPermitted") == "false"
    assert policy.findall("domain-config") == []
    assert all("RiveCandidateHostActivity" not in a.get(ANDROID + "name", "") for a in app.findall("activity"))


def test_debug_exception_cannot_expand_to_other_hosts_or_subdomains():
    app = ET.parse(SRC / "debug/AndroidManifest.xml").getroot().find("application")
    assert app.get(ANDROID + "usesCleartextTraffic") != "true"
    policy = ET.parse(SRC / "debug/res/xml/network_security_config.xml").getroot()
    assert policy.find("base-config").get("cleartextTrafficPermitted") == "false"
    configs = policy.findall("domain-config")
    assert len(configs) == 1
    assert configs[0].get("cleartextTrafficPermitted") == "true"
    domains = configs[0].findall("domain")
    assert {d.text for d in domains} == {"localhost", "127.0.0.1", "::1"}
    assert all(d.get("includeSubdomains") == "false" for d in domains)
    assert policy.findall("debug-overrides") == []


def test_debug_rig_is_protected_without_exposing_a_release_activity():
    app = ET.parse(SRC / "debug/AndroidManifest.xml").getroot().find("application")
    rig = next(a for a in app.findall("activity") if a.get(ANDROID + "name") == ".visual.RiveCandidateHostActivity")
    assert rig.get(ANDROID + "permission") == "android.permission.DUMP"
