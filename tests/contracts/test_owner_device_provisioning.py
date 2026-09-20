"""Rev 1.5 §0D.2 / ADR-RB-026 — the owner types nothing, and this is what keeps it true.

§0D.2 lists eleven fields the owner production build must not ask for or expose. Two of
them shipped as text boxes: "Gateway address" and "Pairing code" on the onboarding screen,
and the same pair again on the Connections admin screen.

That is not a cosmetic finding. A box asking the owner to type a server address is a
phishing surface with their whole assistant behind it — anyone who persuades them to retype
an address owns every command from that moment, and nothing on the phone looks wrong
afterwards. A pairing code is worse, because it is exactly the kind of string somebody can
be talked into reading out.

So this file reads the Android sources and the installer, and fails on the shape rather
than on the text. A removal that only changed a label would pass a test that looked for
"Gateway address"; what these look for is an editable field anywhere near the fields §0D.2
names, and the private setter that is the actual enforcement.
"""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "android/app/src/main/java/com/dial/van"
MANIFEST = ROOT / "android/app/src/main/AndroidManifest.xml"
TOOL = ROOT / "tools/provisioning/provision_owner_device.py"
ACTIVITY = APP / "provisioning/ProvisioningActivity.kt"
GATEWAY_CLIENT = APP / "gateway/VanGatewayClient.kt"
VERIFIER = APP / "connectivity/ProvisioningPayload.kt"
GATEWAY_PROVISIONING = ROOT / "backend/van_gateway/connectivity/provisioning.py"

#: §0D.2's list, as the section spells it. Read as substrings of a field's label.
FORBIDDEN_LABELS = (
    "gateway url", "gateway address", "hermes url", "websocket url",
    "browser stream host", "turn host", "stun host", "pairing token", "pairing code",
    "device id", "ingress token", "fallback endpoint", "certificate pin",
    "transport priority",
)

#: The Compose editable-field composables. A production build uses no other.
EDITABLE = ("OutlinedTextField", "TextField", "BasicTextField")


def _kotlin_sources() -> list[Path]:
    return sorted(APP.rglob("*.kt"))


def test_no_screen_offers_an_editable_field_for_anything_section_0D2_names():
    """The rule, over every Kotlin file, by shape rather than by wording.

    The match is an editable composable whose `label` names one of §0D.2's fields. A
    screen that renamed "Gateway address" to "Server" would still be caught, because the
    label is read case-insensitively against the list and "url"/"address"/"token" are the
    words that matter — and a screen that removed the label entirely would fail the second
    test below, which refuses an editable field on those screens at all.
    """
    offences = []
    for path in _kotlin_sources():
        text = path.read_text(encoding="utf-8")
        for field in EDITABLE:
            for match in re.finditer(rf"\b{field}\s*\(", text):
                window = text[match.start(): match.start() + 900].lower()
                for label in FORBIDDEN_LABELS:
                    if f'text("{label}' in window or f"label = \"{label}" in window:
                        offences.append(f"{path.relative_to(ROOT)}: {field} labelled {label!r}")
    assert offences == [], offences


def test_the_two_screens_that_carried_the_forms_have_no_editable_field_at_all():
    """Stronger than the label rule, and only for the two screens that had the problem.

    `OnboardingActivity` and the Connections admin module exist to say what is set up,
    not to set it up. Any editable field on either is a new form, whatever it is labelled,
    so this refuses the composable rather than the wording — the check the first version of
    this file did not have, and the one that would have caught an unlabelled rebuild.
    """
    for path in (
        APP / "onboarding/OnboardingActivity.kt",
        APP / "command/modules/AdminModules.kt",
    ):
        text = path.read_text(encoding="utf-8")
        found = [field for field in EDITABLE if re.search(rf"\b{field}\s*\(", text)]
        assert found == [], f"{path.relative_to(ROOT)} has an editable field: {found}"


def test_the_client_cannot_be_pointed_somewhere_new_from_outside():
    """RB-121 — a private setter is the enforcement, not a convention.

    A public `baseUrl` setter is all a "change server address" screen needs. Making it
    private means a new one cannot be written without also editing this file's premise.
    """
    text = GATEWAY_CLIENT.read_text(encoding="utf-8")
    assert "private set(value) = prefs.edit().putString(KEY_BASE" in text, (
        "baseUrl has a public setter again"
    )
    # And the pairing call that used to take owner-typed strings is private too.
    assert "private suspend fun pairThisDevice(" in text
    assert "suspend fun provisionThisDevice(" in text


def test_provisioning_is_the_only_caller_of_pairing():
    """A private method with a second caller inside the class is a second path.

    Read across the whole app rather than the one file, because the failure this guards is
    a new screen that reaches pairing through some other helper.
    """
    callers = []
    for path in _kotlin_sources():
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"\bpairThisDevice\s*\(", text):
            line_start = text.rfind("\n", 0, match.start()) + 1
            line = text[line_start: text.find("\n", match.start())]
            if "private suspend fun" in line:
                continue
            callers.append(f"{path.relative_to(ROOT)}: {line.strip()}")
    assert len(callers) == 1, callers
    assert "provisionThisDevice" in GATEWAY_CLIENT.read_text(encoding="utf-8")


def test_the_installer_and_the_app_agree_on_how_the_payload_arrives():
    """Two processes, one handover. A rename on either side is a silent failure.

    The installer's `am start` succeeds whatever extra it passes; the activity simply finds
    nothing and finishes. Nothing anywhere reports a mismatch, so the contract is here.
    """
    tool = TOOL.read_text(encoding="utf-8")
    activity = ACTIVITY.read_text(encoding="utf-8")

    extra = re.search(r'PROVISIONING_EXTRA = "([a-z_]+)"', tool).group(1)
    assert f'const val EXTRA = "{extra}"' in activity, extra

    component = re.search(r'PROVISIONING_COMPONENT = "([^"]+)"', tool).group(1)
    package, klass = component.split("/")
    assert klass == ".provisioning.ProvisioningActivity"
    manifest = MANIFEST.read_text(encoding="utf-8")
    assert f'android:name="{klass}"' in manifest
    assert f'package="{package}"' in manifest or package == "com.dial.van"

    route = re.search(r'PROVISIONING_ROUTE = "([^"]+)"', tool).group(1)
    app_py = (ROOT / "backend/van_gateway/app.py").read_text(encoding="utf-8")
    assert f'@app.post("{route}")' in app_py, route


def test_the_provisioning_entry_point_is_reachable_only_by_name():
    """An exported activity with an intent filter is an activity anything can find.

    Exported is acceptable here because the entry point holds no authority — the signature
    is the guard. An intent filter would be different: it would advertise the component,
    and an app that advertises "provision me" invites exactly the attempts the signature
    then has to survive one at a time.
    """
    manifest = MANIFEST.read_text(encoding="utf-8")
    block = manifest[manifest.index(".provisioning.ProvisioningActivity"):]
    block = block[: block.index("/>") + 2]
    assert "intent-filter" not in block
    assert 'android:exported="true"' in block


def test_both_implementations_forbid_the_same_standing_credentials():
    """The payload may carry what is consumed once and nothing that outlives enrolment.

    Written twice, in two languages, so it is compared here. A field forbidden on one side
    and permitted on the other means the Gateway would happily sign something the device
    refuses — or worse, the reverse.
    """
    gateway = GATEWAY_PROVISIONING.read_text(encoding="utf-8")
    device = VERIFIER.read_text(encoding="utf-8")

    python_set = ast.literal_eval(
        "{" + re.search(
            r"FORBIDDEN_PAYLOAD_FIELDS = frozenset\(\{(.*?)\}\)", gateway, re.S
        ).group(1) + "}"
    )
    kotlin_block = re.search(
        r"val FORBIDDEN_FIELDS: Set<String> = setOf\((.*?)\)", device, re.S
    ).group(1)
    kotlin_set = set(re.findall(r'"([a-z_]+)"', kotlin_block))

    assert python_set == kotlin_set, {
        "gateway only": sorted(python_set - kotlin_set),
        "device only": sorted(kotlin_set - python_set),
    }
    # The two single-use tokens are deliberately absent from both.
    assert "pairing_token" not in python_set
    assert "bootstrap_token" not in python_set


def test_a_pairing_token_is_still_forbidden_in_a_connectivity_manifest():
    """The distinction that makes the previous test's absence defensible.

    A manifest is long-lived configuration the device caches and re-reads, so a token in
    one is a credential sitting in a file. A provisioning payload lives for minutes and is
    consumed once. Permitting the token in both would erase the difference.
    """
    config = (ROOT / "backend/van_gateway/connectivity/config.py").read_text(encoding="utf-8")
    manifest_fields = ast.literal_eval(
        "{" + re.search(
            r"FORBIDDEN_MANIFEST_FIELDS = frozenset\(\{(.*?)\}\)", config, re.S
        ).group(1) + "}"
    )
    assert "pairing_token" in manifest_fields


def test_a_dry_run_mints_nothing():
    """A dry run that requested a payload would burn a single-use token to print a line."""
    import subprocess
    result = subprocess.run(
        [
            "python3", str(TOOL), "--gateway", "https://van.invalid",
            "--internal-token", "x" * 40, "--dry-run",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "am start" in result.stdout
    assert "<payload>" in result.stdout


def test_the_tool_never_writes_the_credential_to_disk():
    """The payload is fetched, passed once and dropped.

    A file would outlive the ten-minute window the payload is valid for, and a short-lived
    secret in a forgotten file is worse than one in a log that rotates.
    """
    tool = TOOL.read_text(encoding="utf-8")
    tree = ast.parse(tool)
    writes = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "open"
    ]
    assert writes == [], "the installer opens a file"
    assert "write_text" not in tool and "NamedTemporaryFile" not in tool
