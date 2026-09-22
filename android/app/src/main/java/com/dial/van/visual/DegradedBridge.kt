package com.dial.van.visual

/**
 * The one call site between `visual/` and the degraded/diagnostics store.
 *
 * `visual/` produces two facts the owner's Settings/diagnostics screen needs — raw gateway
 * health JSON, and which painter is actually drawing VAN (GAP-F-014) — and `degraded/` owns
 * how the owner reads subsystem health. `degraded/` is out of scope for this change, so
 * rather than call a `degradedModeStore.applyGatewayHealth(...)` method that may not exist
 * yet, every producer calls through this bridge, which starts as a no-op and does nothing
 * until something binds a sink.
 *
 * To finish the wiring: `degraded/`'s store implements [GatewayHealthSink] and
 * [RendererStatusSink] (or wraps a lambda in one), and `VanApplication.onCreate` binds them
 * once, e.g. `DegradedBridge.bindGatewayHealth(degradedModeStore::applyGatewayHealth)`. If
 * `degradedModeStore.applyGatewayHealth(healthJson: String)` already exists by the time this
 * lands, [VanApplication]'s call site here should be replaced by calling it directly and this
 * bridge's gateway-health half deleted — the renderer-status half stands on its own either
 * way, since nothing outside `visual/` computes a [VanRendererStatus].
 */
object DegradedBridge {

    fun interface GatewayHealthSink {
        fun applyGatewayHealth(healthJson: String)
    }

    fun interface RendererStatusSink {
        fun onRendererStatus(status: VanRendererStatus)
    }

    @Volatile private var gatewayHealthSink: GatewayHealthSink? = null
    @Volatile private var rendererStatusSink: RendererStatusSink? = null

    /** Last renderer status published, for a screen that resolves after the first publish. */
    @Volatile var lastRendererStatus: VanRendererStatus? = null
        private set

    fun bindGatewayHealth(sink: GatewayHealthSink?) {
        gatewayHealthSink = sink
    }

    fun bindRendererStatus(sink: RendererStatusSink?) {
        rendererStatusSink = sink
    }

    /** Called from `VanApplication.refreshGatewayHealth` with the raw `/health` body. */
    fun applyGatewayHealth(healthJson: String) {
        gatewayHealthSink?.applyGatewayHealth(healthJson)
    }

    /** Called from [VanRendererStatusPublisher] whenever the embodiment resolves a renderer. */
    fun rendererStatus(status: VanRendererStatus) {
        lastRendererStatus = status
        rendererStatusSink?.onRendererStatus(status)
    }
}
