from pathlib import Path


def test_android_never_contains_private_artemis_console_credential_or_private_endpoint():
    android = Path("android/app/src/main/java/com/dial/van").read_text() if Path("android/app/src/main/java/com/dial/van").is_file() else ""
    # Walk Kotlin sources because the protected token is server-side only.
    text = "\n".join(
        p.read_text(encoding="utf-8")
        for p in Path("android/app/src/main/java/com/dial/van").rglob("*.kt")
    )
    assert "artemis-console.token" not in text
    assert "9135" not in text
    assert "DIAL_ARTEMIS_CONSOLE" not in text


def test_console_session_is_hardware_device_proofed_and_proxy_is_read_only():
    app = Path("backend/van_gateway/app.py").read_text(encoding="utf-8")
    console = Path("backend/van_gateway/artemis/console.py").read_text(encoding="utf-8")
    assert 'or path == "/v1/artemis/console/session"' in app
    assert 'request.method not in {"GET", "HEAD", "OPTIONS"}' in console
    assert 'headers["Authorization"] = f"Bearer {token}"' in console
    assert "X-Van-Ingress-Token" not in console
    assert "X-Van-Device-Token" not in console
