package com.dial.van.visual

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.VanColorTokens
import com.dial.van.design.VanDensity
import com.dial.van.design.VanElevation
import com.dial.van.design.VanMotion
import com.dial.van.design.VanRadius
import com.dial.van.design.VanSpace
import com.dial.van.design.VanTokens
import com.dial.van.design.VanTypeTokens

/**
 * The one theme every VAN screen uses (P3-AND-008).
 *
 * Three activities each built their own `darkColorScheme(primary = ACCENT_CYAN)` inline, so
 * there was no theme to change: adding light mode meant editing three call sites and the
 * fourth would have been forgotten. The palette itself lives in [VanPalette], which is pure
 * and whose contrast is executed in `android/verification`.
 *
 * The system bars follow the scheme rather than the manifest's fixed `#111820`: a light app
 * under a dark status bar with dark icons is a status bar the owner cannot read.
 *
 * Since the design system (`com.dial.van.design`, `docs/design/VAN_PRODUCT_DESIGN_DNA.md`)
 * landed, this is also where [VanTokens] is assembled and published through
 * [com.dial.van.design.LocalVanTokens] — one theme call still wraps every screen, and now
 * also hands it the tokens it paints with, rather than each screen reaching into
 * `VanPalette`/`VanGlassTokens` directly.
 */
private fun VanScheme.toMaterial(dark: Boolean): ColorScheme {
    val base = if (dark) darkColorScheme() else lightColorScheme()
    return base.copy(
        primary = Color(primary),
        onPrimary = Color(onPrimary),
        background = Color(background),
        onBackground = Color(onBackground),
        surface = Color(surface),
        onSurface = Color(onSurface),
        surfaceVariant = Color(surfaceVariant),
        onSurfaceVariant = Color(onSurfaceVariant),
        outline = Color(outline),
        error = Color(error),
        onError = Color(onError),
    )
}

@Composable
fun VanTheme(
    dark: Boolean = isSystemInDarkTheme(),
    /**
     * Whether the caller is the floating overlay (DNA §1: "low" density, always [VanDensity.Compact])
     * rather than a full-screen destination. Defaults to `false`; the overlay's own composition
     * root passes `true`.
     */
    isOverlay: Boolean = false,
    /**
     * DNA §2: "Reduced motion: all durations 0, state changes still communicated by
     * colour/shape." The caller supplies this (from `Settings.Global` animator scale or an
     * accessibility signal, the same input `VanEffectConditions.reducedMotion` already reads
     * elsewhere) rather than `VanTheme` reading it itself, so the same policy input drives
     * both the aura's [VanEffectBudget] and every screen's [VanMotion].
     */
    reducedMotion: Boolean = false,
    content: @Composable () -> Unit,
) {
    val scheme = VanPalette.scheme(dark)
    val view = LocalView.current
    if (!view.isInEditMode) {
        val activity = LocalContext.current as? Activity
        SideEffect {
            val window = activity?.window ?: return@SideEffect
            window.statusBarColor = Color(scheme.background).toArgb()
            window.navigationBarColor = Color(scheme.background).toArgb()
            WindowCompat.getInsetsController(window, view).apply {
                isAppearanceLightStatusBars = !dark
                isAppearanceLightNavigationBars = !dark
            }
        }
    }
    val configuration = LocalConfiguration.current
    val tokens = VanTokens(
        color = VanColorTokens.from(scheme),
        type = VanTypeTokens.DEFAULT,
        space = VanSpace(),
        radius = VanRadius(),
        elevation = VanElevation(),
        motion = VanMotion.resolve(reducedMotion),
        density = VanDensity.from(configuration.screenWidthDp, isOverlay),
        dark = dark,
    )
    CompositionLocalProvider(LocalVanTokens provides tokens) {
        MaterialTheme(colorScheme = scheme.toMaterial(dark), content = content)
    }
}
