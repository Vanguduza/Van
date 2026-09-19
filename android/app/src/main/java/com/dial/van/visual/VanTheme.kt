package com.dial.van.visual

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

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
    MaterialTheme(colorScheme = scheme.toMaterial(dark), content = content)
}
