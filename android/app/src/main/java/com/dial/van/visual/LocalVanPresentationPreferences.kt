package com.dial.van.visual

import androidx.compose.runtime.staticCompositionLocalOf

/** Supplied only by the owner-controlled overlay. System accessibility still outranks it. */
val LocalVanPresentationPreferences = staticCompositionLocalOf { VanPresentationPreferences() }
