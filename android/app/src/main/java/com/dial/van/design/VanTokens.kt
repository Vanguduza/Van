package com.dial.van.design

import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.Easing
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dial.van.visual.VanScheme

/**
 * The Compose-facing half of `docs/design/VAN_PRODUCT_DESIGN_DNA.md` §2.
 *
 * Everything a screen needs to paint with lives here as one `VanTokens` value, reached
 * through [LocalVanTokens] — never a raw `Color(0x...)` or a bare `N.sp` in a screen, which
 * is the rule `tools/audit/android_design_lint.py` enforces mechanically. The numbers
 * themselves — durations, easings, density breakpoints, the domain→role mapping — live in
 * plain-Kotlin siblings ([VanMotionSpec], [DensityTier], [StatusSemantics]) that
 * `android/verification` executes; this file is the thin Compose skin over them, and is not
 * itself tested there because it cannot compile without the Android Gradle Plugin.
 */

// ---- Colour ---------------------------------------------------------------------------

/**
 * DNA §2 colour roles, as [Color]. Built once per [com.dial.van.visual.VanTheme] recomposition
 * from a [VanScheme] — the canon numbers stay in `VanPalette`, this is mostly the `Int` →
 * `Color` conversion, plus [surfaceAcrylic] (a flat colour derived from `surfaceVariant`'s
 * alpha, DNA §2) and [atmosphereBrush] (`bg.atmosphere`, a drawing recipe rather than a flat
 * colour — a radial gradient has no single `Color` to hold).
 */
@Immutable
data class VanColorTokens(
    val bgCanvas: Color,
    val surface0: Color,
    val surface1: Color,
    val surface2: Color,
    /** `surface.1 @ 92% + hairline` (DNA §2) — the flat colour half of the acrylic panel. */
    val surfaceAcrylic: Color,
    val lineHair: Color,
    val textPrimary: Color,
    val textSecondary: Color,
    val textTertiary: Color,
    val textInverse: Color,
    val accentCyan: Color,
    val accentCyanSoft: Color,
    val accentBlueWhite: Color,
    val statusMonitor: Color,
    val statusEngaged: Color,
    val statusCognition: Color,
    val statusHypothesis: Color,
    val statusEventRisk: Color,
    val statusFavourable: Color,
    val statusDeteriorating: Color,
    val statusCritical: Color,
    val statusDisabled: Color,
) {
    /**
     * [StatusSemantics] role name → this scheme's paintable colour. An unmapped role name —
     * one that is not in [StatusSemantics.ALL_ROLES] — reads as [statusDisabled] rather than
     * throwing: a colour lookup is not where a screen should learn that a new role was added
     * upstream and this table was not.
     */
    fun forStatusRole(role: String): Color = when (role) {
        StatusSemantics.ROLE_MONITOR -> statusMonitor
        StatusSemantics.ROLE_ENGAGED -> statusEngaged
        StatusSemantics.ROLE_COGNITION -> statusCognition
        StatusSemantics.ROLE_HYPOTHESIS -> statusHypothesis
        StatusSemantics.ROLE_EVENT_RISK -> statusEventRisk
        StatusSemantics.ROLE_FAVOURABLE -> statusFavourable
        StatusSemantics.ROLE_DETERIORATING -> statusDeteriorating
        StatusSemantics.ROLE_CRITICAL -> statusCritical
        StatusSemantics.ROLE_DISABLED -> statusDisabled
        else -> statusDisabled
    }

    /** DNA §2 `bg.atmosphere`: "radial cyan 6% over canvas." Sized to whatever it is drawn on. */
    fun atmosphereBrush(): Brush = Brush.radialGradient(listOf(accentCyan.copy(alpha = 0.06f), Color.Transparent))

    companion object {
        fun from(scheme: VanScheme): VanColorTokens {
            fun c(argb: Int) = Color(argb)
            fun role(name: String) = Color(scheme.statusRoles.getValue(name))
            return VanColorTokens(
                bgCanvas = c(scheme.background),
                surface0 = c(scheme.surface),
                surface1 = c(scheme.surfaceVariant),
                // DNA lists three surface tiers; the palette carries two (surface, surfaceVariant).
                // surface.2 is one further step, derived rather than a third canon field, so
                // adding it stays additive to VanPalette instead of a new raw field to keep in
                // sync by hand.
                surface2 = c(scheme.surfaceVariant).let { blend(it, c(scheme.onSurface), 0.06f) },
                surfaceAcrylic = c(scheme.surfaceVariant).copy(alpha = 0.92f),
                lineHair = c(scheme.onSurface).copy(alpha = 0.08f),
                textPrimary = c(scheme.onBackground),
                textSecondary = c(scheme.onSurfaceVariant),
                textTertiary = c(scheme.textTertiary),
                // DNA §2 gives `text.inverse` one literal value (#0B1116), not a per-scheme
                // one: it is the ink used on a *bright filled* surface (a filled status chip,
                // a filled button) which is bright in both the light and the dark scheme, so
                // the ink that reads on it does not change with the scheme either.
                textInverse = Color(0xFF0B1116),
                accentCyan = role("engaged"),
                accentCyanSoft = role("monitor"),
                accentBlueWhite = role("cognition"),
                statusMonitor = role("monitor"),
                statusEngaged = role("engaged"),
                statusCognition = role("cognition"),
                statusHypothesis = role("hypothesis"),
                statusEventRisk = role("eventRisk"),
                statusFavourable = role("favourable"),
                statusDeteriorating = role("deteriorating"),
                statusCritical = role("critical"),
                statusDisabled = role("disabled"),
            )
        }

        private fun blend(a: Color, b: Color, t: Float): Color = Color(
            red = a.red + (b.red - a.red) * t,
            green = a.green + (b.green - a.green) * t,
            blue = a.blue + (b.blue - a.blue) * t,
            alpha = a.alpha,
        )
    }
}

// ---- Typography -------------------------------------------------------------------------

/**
 * DNA §2 typography. Sizes only — colour is deliberately left to the caller (`VanColorTokens`
 * is scheme-dependent, a `TextStyle` here is not), so the same token works on any surface.
 * `data`/`dataLarge` carry tabular numerals (`fontFeatureSettings = "tnum"`, DNA §2: "tabular
 * numerals for data") so a ticking price does not visibly reflow its neighbours' digits.
 */
@Immutable
data class VanTypeTokens(
    val display: TextStyle,
    val title: TextStyle,
    val headline: TextStyle,
    val body: TextStyle,
    val label: TextStyle,
    val data: TextStyle,
    val dataLarge: TextStyle,
) {
    companion object {
        private const val TABULAR_NUMS = "tnum"

        /** Built once; a `TextStyle` is an immutable value, not per-theme state. */
        val DEFAULT: VanTypeTokens = VanTypeTokens(
            display = TextStyle(fontSize = 28.sp, lineHeight = 34.sp, fontWeight = FontWeight.SemiBold),
            title = TextStyle(fontSize = 20.sp, lineHeight = 26.sp, fontWeight = FontWeight.SemiBold),
            headline = TextStyle(fontSize = 16.sp, lineHeight = 22.sp, fontWeight = FontWeight.SemiBold),
            body = TextStyle(fontSize = 14.sp, lineHeight = 20.sp, fontWeight = FontWeight.Normal),
            // DNA §2: "Minimum text size 12sp anywhere." `label` sits exactly at that floor —
            // never make a caption smaller than this token.
            label = TextStyle(fontSize = 12.sp, lineHeight = 16.sp, fontWeight = FontWeight.Medium),
            data = TextStyle(
                fontSize = 13.sp,
                lineHeight = 16.sp,
                fontWeight = FontWeight.Medium,
                fontFeatureSettings = TABULAR_NUMS,
            ),
            dataLarge = TextStyle(
                fontSize = 22.sp,
                lineHeight = 26.sp,
                fontWeight = FontWeight.SemiBold,
                fontFeatureSettings = TABULAR_NUMS,
            ),
        )
    }
}

// ---- Spacing / radius / elevation --------------------------------------------------------

/** DNA §2: 4-pt grid. */
@Immutable
data class VanSpace(
    val space1: Dp = 4.dp,
    val space2: Dp = 8.dp,
    val space3: Dp = 12.dp,
    val space4: Dp = 16.dp,
    val space5: Dp = 24.dp,
    val space6: Dp = 32.dp,
    val pageGutter: Dp = 16.dp,
    val panelPadding: Dp = 16.dp,
    /** DNA §2: "Dense (trading) panel padding 12." */
    val densePanelPadding: Dp = 12.dp,
) {
    /** [panelPadding] on [VanDensity.Regular]/[VanDensity.Compact], [densePanelPadding] on Trading's very-high density callers. */
    fun panelPaddingFor(dense: Boolean): Dp = if (dense) densePanelPadding else panelPadding
}

/** DNA §2: `radius.s`=8 (chips) · `radius.m`=14 (panels) · `radius.l`=22 (shell, sheets). */
@Immutable
data class VanRadius(
    val s: Dp = 8.dp,
    val m: Dp = 14.dp,
    val l: Dp = 22.dp,
    val hairline: Dp = 1.dp,
)

/** DNA §2: `elevation.flat` 0 · `elevation.panel` 2 · `elevation.sheet` 8 · `elevation.overlay` 16. */
@Immutable
data class VanElevation(
    val flat: Dp = 0.dp,
    val panel: Dp = 2.dp,
    val sheet: Dp = 8.dp,
    val overlay: Dp = 16.dp,
)

// ---- Motion -------------------------------------------------------------------------------

/**
 * [VanMotionSpec]'s numbers as Compose types. `reducedMotion` collapses every duration to
 * zero here too — a screen that reads `tokens.motion.durations.quickMs` gets the same zero a
 * JVM test asserted on [VanMotionSpec.resolve] directly, because this is that same function.
 */
@Immutable
data class VanMotion(
    val durations: VanMotionDurations,
    val standardEasing: Easing,
    val enterEasing: Easing,
    val exitEasing: Easing,
    val pressScale: Float,
    val reducedMotion: Boolean,
) {
    companion object {
        private fun toEasing(cubic: VanCubicEasing): Easing =
            CubicBezierEasing(cubic.x1, cubic.y1, cubic.x2, cubic.y2)

        fun resolve(reducedMotion: Boolean): VanMotion = VanMotion(
            durations = VanMotionSpec.resolve(reducedMotion),
            standardEasing = toEasing(VanMotionSpec.EASING_STANDARD),
            enterEasing = toEasing(VanMotionSpec.EASING_ENTER),
            exitEasing = toEasing(VanMotionSpec.EASING_EXIT),
            // A press-scale animation is itself motion: at reduced motion there is nothing to
            // scale toward, so the "pressed" size is the resting size.
            pressScale = if (reducedMotion) 1f else VanMotionSpec.PRESS_SCALE,
            reducedMotion = reducedMotion,
        )
    }
}

// ---- The aggregate + CompositionLocal -----------------------------------------------------

/** Everything a screen paints with, reached through [LocalVanTokens]. */
@Immutable
data class VanTokens(
    val color: VanColorTokens,
    val type: VanTypeTokens,
    val space: VanSpace,
    val radius: VanRadius,
    val elevation: VanElevation,
    val motion: VanMotion,
    val density: VanDensity,
    val dark: Boolean,
)

/**
 * No default value: a component that reads this outside `VanTheme { }` should fail loudly in
 * development rather than silently paint with a guessed palette, which is exactly the bug
 * `VanTheme`'s own doc comment describes three activities having shipped independently.
 */
val LocalVanTokens = staticCompositionLocalOf<VanTokens> {
    error("VanTokens requested outside VanTheme { } — every VAN screen must be wrapped in VanTheme.")
}
