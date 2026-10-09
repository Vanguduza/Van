package com.dial.van.connectivity

import com.dial.van.browser.BrowserIceServer
import com.dial.van.browser.BrowserStreamGrant
import java.net.URI

object SignedBrowserRouting {
    fun admitUrl(route: SignedConnectivityRouting, url: String): String {
        val signal = URI(route.browserSignalUrl ?: error("connectivity_browser_unconfigured"))
        val supplied = URI(url)
        fun port(uri: URI) = if (uri.port == -1) 443 else uri.port
        val prefix = signal.path.trimEnd('/')
        require(supplied.scheme == "https" && supplied.host == signal.host && port(supplied) == port(signal) &&
            supplied.rawUserInfo == null && supplied.rawFragment == null && supplied.rawQuery == null && supplied.normalize().path == supplied.path &&
            supplied.path.split('/').none { it == "." || it == ".." } &&
            (supplied.path == prefix || supplied.path.startsWith("$prefix/"))) { "browser_stream_signal_not_admitted" }
        return url
    }
    fun apply(route: SignedConnectivityRouting, grant: BrowserStreamGrant): BrowserStreamGrant {
        admitUrl(route, grant.signalUrl)
        require(grant.iceServers.flatMap { it.urls }.all { it in route.iceUrls }) { "browser_ice_server_not_admitted" }
        val suppliedUrls = grant.iceServers.flatMap { it.urls }.toSet()
        val additionalStun = route.iceUrls.filter { it !in suppliedUrls && it.startsWith("stun") }
        return grant.copy(iceServers = grant.iceServers + additionalStun.map { BrowserIceServer(listOf(it), null, null) })
    }
}
