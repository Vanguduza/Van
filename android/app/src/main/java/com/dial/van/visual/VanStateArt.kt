package com.dial.van.visual

import android.content.Context
import com.dial.van.R

/** Resolves [VanArtPose] to the packaged owner drawable, if it is actually present. */
object VanStateArt {

    private val drawables: Map<VanArtPose, Int> = mapOf(
        VanArtPose.IDLE to R.drawable.van_state_idle,
        VanArtPose.LISTENING to R.drawable.van_state_listening,
        VanArtPose.THINKING to R.drawable.van_state_thinking,
        VanArtPose.WORKING to R.drawable.van_state_working,
        VanArtPose.SEARCHING to R.drawable.van_state_searching,
        VanArtPose.NOTIFICATIONS to R.drawable.van_state_notifications,
        VanArtPose.SUCCESS to R.drawable.van_state_success,
        VanArtPose.WARNING to R.drawable.van_state_warning,
    )

    fun drawableFor(state: VanDurableState): Int? = drawables[VanArtPoses.forState(state)]

    /**
     * Owner art is only trusted when every pose is packaged. A partially stripped resource set
     * (for example an aggressive shrinker configuration) falls back to the Canvas character
     * rather than showing Van for some states and nothing for others.
     */
    fun artAvailable(context: Context): Boolean = drawables.values.all { resId ->
        runCatching { context.resources.getResourceName(resId) != null }.getOrDefault(false)
    }
}
