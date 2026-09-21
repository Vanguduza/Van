"""Rev 1.5 §13 — what can be checked about a deployment package with no host to deploy to.

Not much, and that is the point of being explicit about which. Three things here are real
properties of the files rather than of a running machine, and each of them is a wrong
default that would look like it worked:

  * the Chromium unit pins the debugger to `127.0.0.1`. Chromium's behaviour when given a
    port with no address has differed between versions and has been "all interfaces"; the
    flag is not redundant;
  * the control agent refuses to bind to a wildcard or a public address;
  * `qualify.sh` never reports GREEN for a check it could not run.

Everything else about this package — that the units start, that the volume is encrypted,
that the agent rejects a foreign certificate — is a fact about a host and is RB-010/RB-117.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from services.browser_control_agent.cdp import CdpUnavailable, LoopbackCdp
from services.browser_control_agent.server import BindRefused, require_private_bind

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "deploy" / "van-browser-stream"
CHROMIUM_UNIT = PACKAGE / "systemd" / "van-browser-chromium.service"
AGENT_UNIT = PACKAGE / "systemd" / "van-browser-control-agent.service"
QUALIFY = PACKAGE / "qualify.sh"
BOOTSTRAP = PACKAGE / "bootstrap.sh"


class TestTheDebuggerIsFenced:

    def test_the_chromium_unit_pins_the_debugging_address(self):
        """RB-117's repository half. The runtime half needs a host."""
        unit = CHROMIUM_UNIT.read_text()
        assert "--remote-debugging-address=127.0.0.1" in unit
        port_flag = re.search(r"--remote-debugging-port=(\S+)", unit)
        assert port_flag, "the unit does not open a debugging port at all"

    def test_the_chromium_unit_does_not_bind_the_debugger_anywhere_else(self):
        unit = CHROMIUM_UNIT.read_text()
        for wrong in ("--remote-debugging-address=0.0.0.0", "--remote-debugging-address=::"):
            assert wrong not in unit

    def test_the_browser_user_is_not_root_and_has_no_docker(self):
        unit = CHROMIUM_UNIT.read_text()
        assert "User=van-browser" in unit
        assert "NoNewPrivileges=true" in unit
        # Comments are stripped: the unit explains in prose why the docker socket is
        # absent, and a substring search over the whole file would find that explanation
        # and call it a grant.
        directives = "\n".join(
            line for line in unit.splitlines() if not line.lstrip().startswith("#")
        )
        assert "docker" not in directives

    def test_the_agent_cannot_read_the_profile_volume(self):
        """It talks to Chromium, not to Chromium's files. A bridge that could read the
        profile directory could exfiltrate the owner's cookies without touching a page."""
        assert "InaccessiblePaths=-/var/lib/van-browser-profiles" in AGENT_UNIT.read_text()

    def test_the_agent_dies_with_the_browser(self):
        """An agent that is up while the browser is down accepts calls it cannot serve, and
        the caller reads that as its task failing rather than the host being unavailable."""
        assert "BindsTo=van-browser-chromium.service" in AGENT_UNIT.read_text()


class TestTheCdpClientIsLoopbackOnly:

    def test_a_loopback_literal_is_accepted(self):
        LoopbackCdp("ws://127.0.0.1:9222/devtools/browser/abc")

    @pytest.mark.parametrize(
        "url",
        [
            "ws://0.0.0.0:9222/x",
            "ws://10.0.1.233:9222/x",
            "ws://8.8.8.8:9222/x",
        ],
    )
    def test_a_non_loopback_endpoint_is_refused(self, url):
        with pytest.raises(CdpUnavailable):
            LoopbackCdp(url)

    def test_a_hostname_is_refused_even_when_it_would_resolve_to_loopback(self):
        """`localhost` resolves at connect time, on a machine this process does not control.
        Only a literal is a guarantee."""
        with pytest.raises(CdpUnavailable):
            LoopbackCdp("ws://localhost:9222/x")


class TestTheControlAgentBind:

    @pytest.mark.parametrize(
        "address,reason",
        [
            ("0.0.0.0", "wildcard"),
            ("::", "wildcard"),
            ("", "wildcard"),
            ("127.0.0.1", "loopback"),
            ("8.8.8.8", "not_private"),
            ("van-stream-host", "ip_literal"),
        ],
    )
    def test_a_wrong_bind_is_refused_with_its_reason(self, address, reason):
        with pytest.raises(BindRefused) as caught:
            require_private_bind(address)
        assert reason in str(caught.value)

    def test_a_private_address_is_accepted(self):
        assert require_private_bind("10.0.1.240") == "10.0.1.240"

    def test_the_public_address_is_refused_even_though_it_is_specific(self):
        """The check that a naive "not a wildcard" rule would miss."""
        with pytest.raises(BindRefused):
            require_private_bind("10.0.1.240", public_addresses=frozenset({"10.0.1.240"}))


class TestQualifyIsHonest:

    def test_it_reports_unknown_rather_than_green_for_what_it_could_not_test(self):
        """The property that makes a qualification script worth running.

        A script that reports success for a check it skipped is worse than no script,
        because it produces evidence for a claim nobody tested.
        """
        script = QUALIFY.read_text()
        assert 'record "cdp_not_public" "UNKNOWN"' in script
        assert 'record "agent_refuses_foreign_ca" "UNKNOWN"' in script
        assert 'if [ "$2" != "GREEN" ]; then overall=1; fi' in script, (
            "UNKNOWN must fail the script, or it is a pass with a different name"
        )

    def test_it_checks_the_debugger_is_listening_at_all(self):
        """Otherwise the "not public" check passes on a host where nothing is running,
        which is the easiest way to get a green report for a broken machine."""
        assert 'record "cdp_on_loopback"' in QUALIFY.read_text()

    def test_every_recorded_check_can_fail(self):
        """A check with no RED branch is a decoration."""
        script = QUALIFY.read_text()
        names = set(re.findall(r'record "(\w+)"', script))
        assert names, "qualify.sh records nothing"
        for name in names:
            statuses = set(re.findall(rf'record "{name}" "(\w+)"', script))
            assert "RED" in statuses or "UNKNOWN" in statuses, (
                f"{name} can only ever report GREEN"
            )

    def test_the_exit_code_is_the_verdict(self):
        assert 'exit "$overall"' in QUALIFY.read_text()


class TestBootstrapRefusesRatherThanGuesses:

    @pytest.mark.parametrize(
        "variable",
        [
            "VAN_BROWSER_CONTROL_BIND",
            "VAN_BROWSER_PROFILE_DEVICE",
            "VAN_BROWSER_STREAM_TLS_CERT",
            "VAN_BROWSER_GRANT_PUBLIC_KEY",
        ],
    )
    def test_each_thing_with_a_dangerous_default_must_be_supplied(self, variable):
        """Every one of these has a default that would look like it worked: 0.0.0.0, a
        plain directory, a self-signed certificate, no grant verification at all."""
        assert f"require_env {variable}" in BOOTSTRAP.read_text()

    def test_it_refuses_a_wildcard_control_bind_explicitly(self):
        """`require_env` only proves the variable is set. `0.0.0.0` is set."""
        script = BOOTSTRAP.read_text()
        assert "0.0.0.0|::" in script

    def test_it_does_not_install_a_browser(self):
        """The Chromium version that runs here is a provisioning decision with a digest,
        not something a shell script picks up from a package index."""
        script = BOOTSTRAP.read_text()
        assert "apt-get install" not in script
        assert "refused: no chromium on PATH" in script

    def test_it_says_that_qualify_is_the_gate(self):
        assert "qualify.sh is the gate" in BOOTSTRAP.read_text()


class TestThePackageDoesNotOverstate:

    def test_the_readme_says_nothing_here_has_been_run(self):
        readme = (PACKAGE / "README.md").read_text()
        assert "Nothing in this directory has ever been run" in readme

    def test_the_server_entry_point_does_not_pretend_to_serve(self):
        """A process that binds a socket to prove it can is the "integrated because it
        starts" claim §42.5 forbids."""
        server = (ROOT / "services" / "browser_control_agent" / "server.py").read_text()
        assert "no HTTP server is wired in this repository" in server

    def test_the_cdp_client_says_it_cannot_send(self):
        cdp = LoopbackCdp("ws://127.0.0.1:9222/x")
        import asyncio

        with pytest.raises(CdpUnavailable):
            asyncio.run(cdp.send("t", "Page.navigate", {}))


class TestTheServerContextRefusesAnAnonymousCaller:
    """§13.3 — mTLS means the *server* demands a certificate, not that one may be offered.

    This builds the real `SSLContext` from real key material rather than reading the source
    for `CERT_REQUIRED`, because the question is what the context does, and a context whose
    verify mode was relaxed would still contain the constant somewhere.
    """

    @staticmethod
    def _pki(tmp_path):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID
        import datetime

        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "van-browser-control-agent")])
        now = datetime.datetime.now(datetime.timezone.utc)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=30))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256())
        )
        cert_file = tmp_path / "agent.crt"
        key_file = tmp_path / "agent.key"
        cert_file.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        key_file.write_bytes(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        return cert_file, key_file

    def test_the_context_demands_a_client_certificate(self, tmp_path):
        import ssl

        from services.browser_control_agent.server import build_ssl_context

        cert_file, key_file = self._pki(tmp_path)
        context = build_ssl_context(
            ca_file=str(cert_file), cert_file=str(cert_file), key_file=str(key_file)
        )
        assert context.verify_mode is ssl.CERT_REQUIRED, (
            "a handshake without a client certificate would succeed, and the agent would "
            "then authorise an empty common name"
        )

    def test_the_context_trusts_only_the_private_control_ca(self, tmp_path):
        """The failure this prevents is subtle: with the system store loaded, any publicly
        issued certificate authenticates a caller, and `qualify.sh`'s foreign-certificate
        check would pass for the wrong reason because that certificate is self-signed."""
        from services.browser_control_agent.server import build_ssl_context

        cert_file, key_file = self._pki(tmp_path)
        context = build_ssl_context(
            ca_file=str(cert_file), cert_file=str(cert_file), key_file=str(key_file)
        )
        trusted = context.get_ca_certs()
        assert len(trusted) == 1, f"the context trusts {len(trusted)} CAs, not just ours"
        assert trusted[0]["subject"][0][0][1] == "van-browser-control-agent"

    def test_the_context_refuses_anything_below_tls_1_3(self, tmp_path):
        import ssl

        from services.browser_control_agent.server import build_ssl_context

        cert_file, key_file = self._pki(tmp_path)
        context = build_ssl_context(
            ca_file=str(cert_file), cert_file=str(cert_file), key_file=str(key_file)
        )
        assert context.minimum_version is ssl.TLSVersion.TLSv1_3
