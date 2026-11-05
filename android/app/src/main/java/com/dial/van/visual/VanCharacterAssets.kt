package com.dial.van.visual

import android.content.Context
import com.dial.van.BuildConfig

/** One asset resolver used by the real floating renderer and the existing rig lab. */
object VanCharacterAssets {
    val reviewBuild: Boolean get() = VanCharacterReviewPolicy.enabled(BuildConfig.DEBUG,
        BuildConfig.VAN_CHARACTER_REVIEW, BuildConfig.BUILD_TYPE, BuildConfig.APPLICATION_ID)

    data class Loaded(val bytes: ByteArray, val metadata: String?)

    fun load(context: Context): Loaded {
        check(!BuildConfig.VAN_CHARACTER_REVIEW || reviewBuild) { "Review character is forbidden in this build" }
        val asset = if (reviewBuild) VanCharacterReviewPolicy.RIVE_FILE else RiveBindingContract.ASSET_FILE
        val bytes = context.assets.open(asset).use { VanAssetReadLimits.read(it, VanAssetReadLimits.RIVE_BYTES) }
        val sidecar = if (reviewBuild) VanCharacterReviewPolicy.CONTEXT_FILE else VanRiveContextCapabilities.ASSET_FILE
        val metadata = runCatching { context.assets.open(sidecar).use {
            VanAssetReadLimits.read(it, VanAssetReadLimits.CONTEXT_BYTES)
        } }.getOrNull()
        if (reviewBuild) {
            val marker = context.assets.open(VanCharacterReviewPolicy.MARKER_FILE).use {
                VanAssetReadLimits.read(it, 16_384).toString(Charsets.UTF_8)
            }
            require(metadata != null && VanCharacterReviewPolicy.validate(bytes, metadata, marker,
                BuildConfig.DEBUG, BuildConfig.VAN_CHARACTER_REVIEW, BuildConfig.BUILD_TYPE, BuildConfig.APPLICATION_ID,
                BuildConfig.VAN_CHARACTER_REVIEW_REQUEST_SHA, BuildConfig.VAN_CHARACTER_REVIEW_RIVE_SHA,
                BuildConfig.VAN_CHARACTER_REVIEW_CONTEXT_SHA, BuildConfig.VAN_SOURCE_SHA)) { "Review character identity mismatch" }
        }
        return Loaded(bytes, metadata?.toString(Charsets.UTF_8))
    }
}
