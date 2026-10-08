package com.dial.van.buildconfig;

import java.io.ByteArrayInputStream;
import java.net.InetAddress;
import java.net.URI;
import java.security.MessageDigest;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.time.Instant;
import java.util.Base64;
import java.util.Collection;
import java.util.Date;
import java.util.HexFormat;
import java.util.Properties;

/** Build-time trust selection. No credential discovery, DNS lookup, or remote admission. */
public final class VanProductionTarget {
    private VanProductionTarget() {}

    public static final class Connection {
        public final String baseUrl;
        public final String caPemB64;

        private Connection(String baseUrl, String caPemB64) {
            this.baseUrl = baseUrl;
            this.caPemB64 = caPemB64;
        }
    }

    /** The address and trust anchor must be selected together from one source. */
    public static Connection resolve(Properties historical, Properties profile,
            String urlOverride, String caOverride) {
        if (profile != null) {
            require(urlOverride == null && caOverride == null,
                    "deployment profile cannot be combined with individual gateway overrides");
            return connection(value(profile, "VAN_GATEWAY_BASE_URL"),
                    value(profile, "VAN_GATEWAY_CA_PEM_B64"));
        }
        require(caOverride == null || urlOverride != null,
                "a gateway CA override requires the matching gateway URL override");
        return connection(urlOverride == null ? value(historical, "VAN_GATEWAY_BASE_URL") : urlOverride,
                urlOverride == null ? value(historical, "VAN_GATEWAY_CA_PEM_B64")
                        : caOverride == null ? "" : caOverride);
    }

    private static Connection connection(String url, String ca) {
        url = url.trim();
        ca = ca.trim();
        if (!url.isEmpty()) validateGateway(url, false);
        require(ca.matches("[A-Za-z0-9+/=]*"), "gateway CA must be base64");
        require(ca.isEmpty() || url.startsWith("https://"),
                "gateway CA requires the matching HTTPS gateway");
        return new Connection(url, ca);
    }

    /** A release never inherits the historical dial-control debug endpoint. */
    public static void requireReleaseProfile(Properties profile, String url, String caPemB64) {
        requireReleaseProfile(profile, url, caPemB64, Instant.now());
    }

    public static void requireReleaseProfile(Properties profile, String url, String caPemB64,
            Instant now) {
        require(profile != null, "VAN_DEPLOYMENT_PROFILE_FILE is required for van-trading-core releases");
        require("1".equals(value(profile, "VAN_DEPLOYMENT_PROFILE_VERSION")),
                "deployment profile version must be 1");
        require(value(profile, "VAN_DEPLOYMENT_PROFILE_ID").matches("[A-Za-z0-9][A-Za-z0-9._-]{0,127}"),
                "deployment profile ID is missing or invalid");
        require("van-trading-core".equals(value(profile, "VAN_BACKEND_HOST")),
                "VAN backend must be van-trading-core");
        require("dial-control".equals(value(profile, "VAN_HERMES_HOST")),
                "Hermes host must remain dial-control");
        require("oracle-admin".equals(value(profile, "VAN_GATEWAY_INGRESS_HOST")),
                "VAN ingress must be the separately admitted oracle-admin VAN ingress");
        require(value(profile, "VAN_GATEWAY_INGRESS_CAPABILITY_RECEIPT")
                        .matches("[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}"),
                "VAN ingress capability receipt is missing or invalid");
        require(url.equals(value(profile, "VAN_GATEWAY_BASE_URL"))
                        && caPemB64.equals(value(profile, "VAN_GATEWAY_CA_PEM_B64")),
                "gateway URL or CA does not match the selected deployment profile");
        URI gateway = validateGateway(url, true);
        require(!"62.83.35.103".equals(gateway.getHost()),
                "historical dial-control public endpoint cannot be a van-trading-core release target");
        validateCa(caPemB64, value(profile, "VAN_GATEWAY_CA_SHA256"), now);
    }

    private static URI validateGateway(String raw, boolean production) {
        final URI uri;
        try {
            uri = new URI(raw);
        } catch (Exception invalid) {
            throw new IllegalArgumentException("gateway must be a valid HTTPS root URL");
        }
        String host = uri.getHost();
        require(host != null && !host.isEmpty() && uri.getRawUserInfo() == null
                        && uri.getRawQuery() == null && uri.getRawFragment() == null
                        && (uri.getRawPath() == null || uri.getRawPath().isEmpty()
                            || "/".equals(uri.getRawPath()))
                        && uri.getPort() != 0 && uri.getPort() <= 65535
                        && !uri.getRawAuthority().endsWith(":"),
                "gateway must have only a host, optional valid port, and root path");
        boolean https = "https".equals(uri.getScheme());
        require(https || (!production && "http".equals(uri.getScheme())
                        && ("localhost".equals(host) || "127.0.0.1".equals(host)
                            || "[::1]".equals(host))),
                "gateway must use HTTPS; debug HTTP is limited to exact loopback");
        if (production) {
            require(uri.getPort() >= 1024,
                    "dedicated VAN ingress requires an explicit unprivileged public port");
            require(isPublicHost(host), "release gateway must be a public phone-reachable host");
        }
        return uri;
    }

    private static boolean isPublicHost(String host) {
        String lower = host.toLowerCase(java.util.Locale.ROOT);
        if (lower.contains(":")) {
            if (lower.contains("%")) return false;
            try {
                InetAddress address = InetAddress.getByName(lower);
                if (address.isAnyLocalAddress() || address.isLoopbackAddress()
                        || address.isLinkLocalAddress() || address.isSiteLocalAddress()
                        || address.isMulticastAddress()) return false;
                byte[] bytes = address.getAddress();
                if (bytes.length == 4) return isPublicIpv4(bytes);
                return (bytes[0] & 0xfe) != 0xfc
                        && !(bytes[0] == 0x20 && bytes[1] == 0x01
                            && (bytes[2] & 0xff) == 0x0d && (bytes[3] & 0xff) == 0xb8);
            } catch (Exception invalid) {
                return false;
            }
        }
        if (lower.matches("[0-9.]+")) {
            String[] octets = lower.split("\\.", -1);
            if (octets.length != 4) return false;
            byte[] bytes = new byte[4];
            for (int i = 0; i < 4; i++) {
                if (!octets[i].matches("0|[1-9][0-9]{0,2}")) return false;
                int number = Integer.parseInt(octets[i]);
                if (number > 255) return false;
                bytes[i] = (byte) number;
            }
            return isPublicIpv4(bytes);
        }
        if (lower.length() > 253 || !lower.contains(".") || lower.endsWith(".")) return false;
        for (String suffix : new String[]{".localhost", ".local", ".internal", ".invalid", ".test", ".onion"}) {
            if (lower.endsWith(suffix)) return false;
        }
        for (String label : lower.split("\\.", -1)) {
            if (!label.matches("[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")) return false;
        }
        return true;
    }

    private static boolean isPublicIpv4(byte[] bytes) {
        int a = bytes[0] & 255, b = bytes[1] & 255, c = bytes[2] & 255;
        return a != 0 && a != 10 && a != 127 && a < 224
                && !(a == 100 && b >= 64 && b <= 127)
                && !(a == 169 && b == 254) && !(a == 172 && b >= 16 && b <= 31)
                && !(a == 192 && (b == 168 || (b == 0 && (c == 0 || c == 2))))
                && !(a == 198 && (b == 18 || b == 19 || (b == 51 && c == 100)))
                && !(a == 203 && b == 0 && c == 113);
    }

    private static void validateCa(String encoded, String fingerprint, Instant now) {
        require(!encoded.isEmpty() && encoded.length() <= 65536,
                "release gateway requires a bounded pinned CA certificate");
        String expected = fingerprint.replace(":", "").toLowerCase(java.util.Locale.ROOT);
        require(expected.matches("[0-9a-f]{64}"), "gateway CA SHA256 fingerprint is missing or invalid");
        try {
            byte[] pem = Base64.getDecoder().decode(encoded);
            require(new String(pem, java.nio.charset.StandardCharsets.US_ASCII).matches(
                            "(?s)\\s*-----BEGIN CERTIFICATE-----\\s+[A-Za-z0-9+/=\\r\\n]+-----END CERTIFICATE-----\\s*"),
                    "gateway CA must contain only one PEM certificate");
            Collection<? extends java.security.cert.Certificate> certificates = CertificateFactory
                    .getInstance("X.509").generateCertificates(new ByteArrayInputStream(pem));
            require(certificates.size() == 1, "gateway CA must contain exactly one certificate");
            X509Certificate ca = (X509Certificate) certificates.iterator().next();
            require(ca.getBasicConstraints() >= 0, "gateway trust anchor must be a CA certificate");
            boolean[] usage = ca.getKeyUsage();
            require(usage == null || (usage.length > 5 && usage[5]),
                    "gateway CA does not permit certificate signing");
            ca.checkValidity(Date.from(now));
            String actual = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(ca.getEncoded()));
            require(actual.equals(expected), "gateway CA fingerprint does not match deployment profile");
        } catch (IllegalArgumentException invalid) {
            throw invalid;
        } catch (Exception invalid) {
            throw new IllegalArgumentException("gateway CA is malformed, not yet valid, or expired");
        }
    }

    private static String value(Properties source, String key) {
        return source.getProperty(key, "").trim();
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new IllegalArgumentException(message);
    }
}
