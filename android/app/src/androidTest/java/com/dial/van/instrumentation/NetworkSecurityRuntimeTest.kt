package com.dial.van.instrumentation

import android.content.ComponentName
import android.security.NetworkSecurityPolicy
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.net.InetAddress
import java.net.ServerSocket
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import okhttp3.OkHttpClient
import okhttp3.Request
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Exercise the packaged Android policy and actual HTTP client without external services. */
@RunWith(AndroidJUnit4::class)
class NetworkSecurityRuntimeTest {
    @Test fun debugLoopbackHttpWorksButOtherCleartextIsRefused() {
        val policy = NetworkSecurityPolicy.getInstance()
        for (host in listOf("localhost", "127.0.0.1", "::1")) {
            assertTrue(host, policy.isCleartextTrafficPermitted(host))
        }
        assertFalse(policy.isCleartextTrafficPermitted())
        for (host in listOf("example.com", "192.0.2.1", "10.66.66.1", "van-trading-core",
            "localhost.evil.test", "127.0.0.1.evil.test", "127.0.0.2")) {
            assertFalse(host, policy.isCleartextTrafficPermitted(host))
        }
        val client = OkHttpClient.Builder().connectTimeout(2, TimeUnit.SECONDS)
            .readTimeout(2, TimeUnit.SECONDS).build()
        // No public network operation: the policy refuses this documentation-only IP
        // before a socket connection, while a private in-process server proves loopback.
        val failure = runCatching {
            client.newCall(Request.Builder().url("http://192.0.2.1:9/").build()).execute().use { }
        }.exceptionOrNull()
        assertTrue(failure.toString(), failure?.message?.contains("CLEARTEXT") == true)
        val executor = Executors.newSingleThreadExecutor()
        try {
            ServerSocket(0, 1, InetAddress.getByName("127.0.0.1")).use { server ->
                server.soTimeout = 5000
                val served = executor.submit {
                    server.accept().use { socket ->
                        socket.soTimeout = 5000
                        val input = socket.getInputStream().bufferedReader()
                        while (input.readLine()?.isNotEmpty() == true) { }
                        socket.getOutputStream().write(
                            "HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok".toByteArray(),
                        )
                        socket.getOutputStream().flush()
                    }
                }
                client.newCall(Request.Builder().url("http://127.0.0.1:${server.localPort}/").build())
                    .execute().use { assertEquals("ok", it.body?.string()) }
                served.get(5, TimeUnit.SECONDS)
            }
        } finally {
            executor.shutdownNow()
            client.connectionPool.evictAll()
            client.dispatcher.executorService.shutdown()
        }
    }

    @Test fun exportedDebugRigRequiresPrivilegedCaller() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val activity = context.packageManager.getActivityInfo(
            ComponentName(context, "com.dial.van.visual.RiveCandidateHostActivity"), 0,
        )
        assertTrue(activity.exported)
        assertEquals("android.permission.DUMP", activity.permission)
    }
}
