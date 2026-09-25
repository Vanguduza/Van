package com.dial.van.visual

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

/**
 * A slot for drawing an owner-supplied test model in place of VAN, in debug builds only.
 *
 * Owner direction (2026-09-25): try a third-party VRM character "as is to test". The model
 * cannot ship: its licence forbids modification and redistribution, and it is not VAN. So the
 * renderer lives entirely in the `debug` source set and registers itself here at start-up;
 * in a release build nothing ever sets [renderer], and [VanAvatar] draws VAN as always.
 */
object VanTestModel {

    interface Renderer {
        /** Whether a test model has been imported on this device. */
        fun available(context: Context): Boolean

        @Composable
        fun Render(
            state: VanVisualState,
            presentation: VanPresentation,
            modifier: Modifier,
            onFailed: () -> Unit,
        )
    }

    @Volatile
    var renderer: Renderer? = null
}
