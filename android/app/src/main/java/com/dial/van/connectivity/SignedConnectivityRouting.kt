package com.dial.van.connectivity

import java.net.URI
import java.util.Base64

/** Usable routes from an already signature-verified manifest, never owner input. */
data class SignedConnectivityRouting(
    val version: Int,
    val gatewayUrl: String,
    val sessionUrl: String,
    val browserSignalUrl: String?,
    val iceUrls: List<String>,
    val pins: Set<String>,
) {
    fun permitsTls(url: String): Boolean = authority(url) in listOfNotNull(
        authority(gatewayUrl), authority(sessionUrl), browserSignalUrl?.let(::authority),
    )

    companion object {
        fun from(manifest: ConnectivityManifest): SignedConnectivityRouting {
            fun endpoint(value: String, scheme: String): URI {
                val uri = URI(value)
                require(uri.scheme == scheme && !uri.host.isNullOrBlank() && uri.rawUserInfo == null &&
                    uri.rawQuery == null && uri.rawFragment == null) { "connectivity_endpoint_invalid" }
                return uri
            }
            endpoint(manifest.gatewayUrl, "https")
            require(GatewayBaseUrl.accepts(manifest.gatewayUrl)) { "connectivity_gateway_path_invalid" }
            val session = endpoint(manifest.sessionWebsocketUrl, "wss")
            require(session.path == "/v1/session/ws") { "connectivity_session_path_invalid" }
            val signal = manifest.browserStreamSignalUrl.takeIf { it.isNotBlank() }
            signal?.let { endpoint(it, "https") }
            val pins = manifest.certificatePins.toSet()
            require(pins.isNotEmpty() && pins.all { pin ->
                pin.startsWith("sha256/") && runCatching {
                    Base64.getDecoder().decode(pin.removePrefix("sha256/")).size == 32
                }.getOrDefault(false)
            }) { "connectivity_certificate_pins_invalid" }
            require(manifest.iceServerUrls.all { url ->
                val uri = URI(url)
                uri.scheme in setOf("stun", "stuns", "turn", "turns") &&
                    !uri.rawSchemeSpecificPart.isNullOrBlank() && !uri.rawSchemeSpecificPart.contains('@') &&
                    uri.rawFragment == null
            }) { "connectivity_ice_url_invalid" }
            return SignedConnectivityRouting(manifest.manifestVersion, manifest.gatewayUrl.trimEnd('/'),
                manifest.sessionWebsocketUrl, signal, manifest.iceServerUrls, pins)
        }

        private fun authority(value: String): String? = runCatching {
            val uri = URI(value)
            if (uri.scheme !in setOf("https", "wss") || uri.host == null) null
            else "${uri.host.lowercase()}:${if (uri.port == -1) 443 else uri.port}"
        }.getOrNull()
    }
}
