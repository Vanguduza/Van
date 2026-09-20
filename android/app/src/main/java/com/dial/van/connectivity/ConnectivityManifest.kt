package com.dial.van.connectivity

import com.dial.van.security.VanCanonicalJson
import java.math.BigInteger
import java.security.KeyFactory
import java.security.Signature
import java.security.spec.X509EncodedKeySpec
import java.util.Base64
import org.json.JSONObject

/**
 * Rev 1.5 §0D.2 and ADR-RB-024/027 — where VAN connects, and why the owner is never asked.
 *
 * §0D.2 lists the fields the production build must not expose: gateway URL, Hermes URL,
 * stream host, TURN host, pairing token, device id, certificate pin. Every one of them is a
 * field a convincing phishing page would love someone to retype, and an assistant that
 * holds the owner's mail and money cannot have a "change server address" box.
 *
 * So endpoints arrive signed by a pinned authority key and are verified here before they are
 * believed. The verifier is deliberately strict in three ways that are easy to leave out:
 *
 *  - **an unknown `kid` is refused**, not tried against every key we hold;
 *  - **a manifest may not go backwards**, because an old one is perfectly signed and may
 *    point at an endpoint that has since changed hands;
 *  - **a manifest carrying a credential is refused**, because that is not configuration —
 *    it is a secret in a file that a copy of the app would inherit.
 *
 * This file has no Android imports on purpose: it is the part that can be executed in the
 * pure harness, which is the only compiler available in some environments (§4).
 */
data class ConnectivityManifest(
    val manifestVersion: Int,
    val gatewayUrl: String,
    val sessionWebsocketUrl: String,
    val browserStreamSignalUrl: String,
    val iceServerUrls: List<String>,
    val certificatePins: List<String>,
    val raw: String,
) {
    val hasBrowserStream: Boolean
        get() = browserStreamSignalUrl.isNotBlank()
}

sealed class ManifestVerdict {
    data class Accepted(val manifest: ConnectivityManifest) : ManifestVerdict()

    /** Refusals carry a reason so a diagnostics screen can say what happened. */
    data class Refused(val reason: String) : ManifestVerdict()
}

/**
 * The build-time trust anchor, parsed.
 *
 * Extracted because there are now two readers — the connectivity manifest and the
 * ADR-RB-026 provisioning payload — and the first version of the second one invented its
 * own format. It parsed the same string as JSON, found nothing, and reported the build as
 * having no trust anchor: provisioning would have been impossible on a correctly
 * configured release build, and the only symptom would have been a phone that sat waiting.
 *
 * Two parsers for one build-time string is the same class of defect as two copies of a
 * wire format, and it is harder to see because the string is injected rather than sent.
 */
object ConnectivityTrustedKeys {

    /**
     * `kid=PEM` pairs, newline-separated, injected at build time.
     *
     * A malformed entry is dropped rather than throwing: one bad line in a build
     * configuration must not make a shipped app unable to start, and the consequence of
     * dropping it — that anything signed by that key is refused as `unknown_kid` — is the
     * safe direction.
     */
    fun parse(raw: String): Map<String, String> =
        raw.split("\n")
            .mapNotNull { line ->
                val separator = line.indexOf('=')
                if (separator <= 0) return@mapNotNull null
                val kid = line.substring(0, separator).trim()
                val pem = line.substring(separator + 1).trim().replace("\\n", "\n")
                if (kid.isEmpty() || !pem.contains("BEGIN PUBLIC KEY")) null else kid to pem
            }
            .toMap()
}

object ConnectivityManifestVerifier {

    /**
     * §0D.2 — fields that would make this a credential rather than configuration.
     *
     * Mirrors `FORBIDDEN_MANIFEST_FIELDS` in the gateway. Both ends check: the gateway so a
     * mistake is caught at publication, the device so a gateway that has been replaced
     * cannot hand the phone a secret it will cache.
     */
    val FORBIDDEN_FIELDS: Set<String> = setOf(
        "pairing_token", "device_token", "device_id", "ingress_token", "hermes_token",
        "internal_control_token", "access_token", "refresh_token", "client_secret",
    )

    /**
     * Verify and parse. [trustedKeys] is the pinned authority set, by `kid`.
     *
     * [knownVersion] is what this device already trusts; a manifest at or below it is
     * refused as a rollback rather than quietly applied.
     */
    fun verify(
        manifestJson: String,
        signatureHex: String,
        kid: String,
        trustedKeys: Map<String, String>,
        knownVersion: Int,
    ): ManifestVerdict {
        val publicKeyPem = trustedKeys[kid]
            ?: return ManifestVerdict.Refused("connectivity_manifest_unknown_kid")

        val parsed = runCatching { JSONObject(manifestJson) }.getOrNull()
            ?: return ManifestVerdict.Refused("connectivity_manifest_malformed")

        val leaked = FORBIDDEN_FIELDS.filter { parsed.has(it) }
        if (leaked.isNotEmpty()) {
            return ManifestVerdict.Refused("connectivity_manifest_carries_credential:${leaked.first()}")
        }

        val version = parsed.optInt("manifest_version", 0)
        if (version <= 0) return ManifestVerdict.Refused("connectivity_manifest_unversioned")
        if (version <= knownVersion) {
            return ManifestVerdict.Refused("connectivity_manifest_rollback")
        }

        val ok = runCatching {
            verifySignature(canonical(parsed), signatureHex, publicKeyPem)
        }.getOrDefault(false)
        if (!ok) return ManifestVerdict.Refused("connectivity_manifest_signature_invalid")

        return ManifestVerdict.Accepted(
            ConnectivityManifest(
                manifestVersion = version,
                gatewayUrl = parsed.optString("gateway_url", ""),
                sessionWebsocketUrl = parsed.optString("session_websocket_url", ""),
                browserStreamSignalUrl = parsed.optString("browser_stream_signal_url", ""),
                iceServerUrls = (0 until (parsed.optJSONArray("ice_server_urls")?.length() ?: 0))
                    .map { parsed.getJSONArray("ice_server_urls").getString(it) },
                certificatePins = (0 until (parsed.optJSONArray("certificate_pins")?.length() ?: 0))
                    .map { parsed.getJSONArray("certificate_pins").getString(it) },
                raw = manifestJson,
            ),
        )
    }

    /**
     * The exact bytes the gateway signed: keys sorted, no whitespace, non-ASCII escaped.
     *
     * Rebuilt rather than reusing the transmitted string, because two JSON documents can
     * differ in whitespace and key order while meaning the same thing — and signing one
     * spelling while verifying another is a signature check that passes only by luck.
     *
     * The rule itself lives in [VanCanonicalJson] because the session envelope digests the
     * same way. This file had its own copy, and that copy did not escape non-ASCII: a
     * manifest naming a profile with an accent in it verified here and nowhere else.
     */
    internal fun canonical(json: JSONObject): ByteArray = VanCanonicalJson.bytes(json)

    /**
     * The same signature check, for a caller outside this object.
     *
     * `ProvisioningVerifier` uses it deliberately rather than keeping a copy: a second
     * P-256 verifier is a second place the DER conversion can be subtly wrong, and the
     * symptom of that is a signature that passes for the wrong reason.
     */
    internal fun verifySignatureFor(
        payload: ByteArray,
        signatureHex: String,
        publicKeyPem: String,
    ): Boolean = verifySignature(payload, signatureHex, publicKeyPem)

    private fun verifySignature(
        payload: ByteArray,
        signatureHex: String,
        publicKeyPem: String,
    ): Boolean {
        val raw = signatureHex.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
        if (raw.size != 64) return false
        val der = toDerSignature(raw)

        val body = publicKeyPem
            .replace("-----BEGIN PUBLIC KEY-----", "")
            .replace("-----END PUBLIC KEY-----", "")
            .replace(Regex("\\s"), "")
        val key = KeyFactory.getInstance("EC")
            .generatePublic(X509EncodedKeySpec(Base64.getDecoder().decode(body)))

        return Signature.getInstance("SHA256withECDSA").run {
            initVerify(key)
            update(payload)
            verify(der)
        }
    }

    /** P1363 (r||s) to DER, which is what `Signature` expects. */
    private fun toDerSignature(raw: ByteArray): ByteArray {
        val r = BigInteger(1, raw.copyOfRange(0, 32)).toByteArray()
        val s = BigInteger(1, raw.copyOfRange(32, 64)).toByteArray()
        val body = ByteArray(2 + r.size + 2 + s.size)
        var offset = 0
        body[offset++] = 0x02; body[offset++] = r.size.toByte()
        r.copyInto(body, offset); offset += r.size
        body[offset++] = 0x02; body[offset++] = s.size.toByte()
        s.copyInto(body, offset)
        return byteArrayOf(0x30, body.size.toByte()) + body
    }
}
