package com.dial.van.visual

import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow

/**
 * VAN's two colour schemes, and the contrast arithmetic that decides whether they are
 * readable.
 *
 * P3-AND-008. Three activities each called `darkColorScheme(primary = ACCENT_CYAN)` and
 * nothing else: no light scheme, no `values-night`, and a window theme inheriting from
 * `android:Theme.Material.NoActionBar`, which has been deprecated since API 21's successor
 * and pins the app to a look Android stopped shipping. An owner whose phone is in light mode
 * got a dark app; an owner who needs light mode for legibility got one they could not read.
 *
 * The dark scheme is canon and is unchanged. The light scheme is not the dark one with the
 * background flipped — that is the failure this file exists to prevent. VAN's cyan is a
 * *glow* colour: `#00DAFF` on white is a contrast ratio of 1.8, which is invisible. Light
 * mode therefore uses a deepened cyan for anything carrying text, and keeps the glow cyan
 * only for the aura, which is drawn over its own dark field in both modes.
 *
 * Pure Kotlin so [contrastRatio] runs in `android/verification`: "is this readable" is an
 * arithmetic question with a published answer, and answering it by looking at a screenshot
 * is how a light mode ships unreadable.
 */
data class VanColorRole(val name: String, val foreground: Int, val background: Int)

data class VanScheme(
    val name: String,
    val primary: Int,
    val onPrimary: Int,
    val background: Int,
    val onBackground: Int,
    val surface: Int,
    val onSurface: Int,
    val surfaceVariant: Int,
    val onSurfaceVariant: Int,
    val outline: Int,
    val error: Int,
    val onError: Int,
    // --- Additive: com.dial.van.design.VanColorTokens (docs/design/VAN_PRODUCT_DESIGN_DNA.md
    // §2). These extend the palette for the design-system layer without touching a single
    // field above — every existing construction site and every existing test is untouched.
    /**
     * DNA §2 `text.tertiary` — de-emphasised text, one step past [onSurfaceVariant]. Verified
     * at AA_NORMAL against both [background] and [surface] in `VanDesignRolesTest`, same as
     * every other text role: DNA's "minimum text size 12sp anywhere" does not buy tertiary
     * text a lower contrast floor.
     */
    val textTertiary: Int,
    /**
     * DNA §2 status roles, keyed by [com.dial.van.design.StatusSemantics] role name
     * (`monitor`, `engaged`, `cognition`, `hypothesis`, `eventRisk`, `favourable`,
     * `deteriorating`, `critical`, `disabled`). `accent.cyan`/`accent.cyanSoft`/
     * `accent.blueWhite` are `engaged`/`monitor`/`cognition` respectively — DNA names them
     * twice (once as a VAN accent, once as a status colour) because they *are* the same
     * colour used two ways, not two colours that happen to match.
     *
     * The dark scheme keeps DNA's literal vivid hex values (a dark field is forgiving of
     * saturated colour). The light scheme deepens every one of them, the same move
     * [LIGHT]'s own doc comment describes for `primary`: a vivid accent that is legible on
     * navy is frequently under 2:1 on white.
     */
    val statusRoles: Map<String, Int>,
) {
    /** Every foreground/background pair a screen will actually put text on. */
    fun textPairs(): List<VanColorRole> = listOf(
        VanColorRole("onBackground", onBackground, background),
        VanColorRole("onSurface", onSurface, surface),
        VanColorRole("onSurfaceVariant", onSurfaceVariant, surfaceVariant),
        VanColorRole("onPrimary", onPrimary, primary),
        VanColorRole("onError", onError, error),
    )

    /**
     * [textTertiary] and every [statusRoles] colour, each checked against both [background]
     * and [surface] — the two fields every screen actually paints text or a status chip on.
     */
    fun designRolePairs(): List<VanColorRole> = buildList {
        add(VanColorRole("textTertiary/background", textTertiary, background))
        add(VanColorRole("textTertiary/surface", textTertiary, surface))
        for ((role, color) in statusRoles) {
            add(VanColorRole("status.$role/background", color, background))
            add(VanColorRole("status.$role/surface", color, surface))
        }
    }
}

object VanPalette {

    /** WCAG AA for body text. Below this, text is decoration. */
    const val AA_NORMAL = 4.5

    /** WCAG AA for large text and for non-text boundaries like the outline. */
    const val AA_LARGE = 3.0

    /**
     * Canon. The deep navy field the aura is drawn over, unchanged from what shipped.
     */
    val DARK = VanScheme(
        name = "dark",
        primary = VanGlassTokens.ACCENT_CYAN,
        onPrimary = 0xFF041016.toInt(),
        background = 0xFF0A1219.toInt(),
        onBackground = 0xFFE6F6FB.toInt(),
        surface = 0xFF111C25.toInt(),
        onSurface = 0xFFE6F6FB.toInt(),
        surfaceVariant = 0xFF18262F.toInt(),
        onSurfaceVariant = 0xFFB4CDD8.toInt(),
        // Raised from the navy-adjacent #4A6874, which came out at 2.9:1 against the
        // surface: a card boundary the owner can only see if they already know it is there.
        outline = 0xFF587B8A.toInt(),
        error = VanGlassTokens.ACCENT_RED,
        onError = 0xFF2A0707.toInt(),
        textTertiary = 0xFF7F97A2.toInt(),
        statusRoles = mapOf(
            "monitor" to 0xFF4DD0E1.toInt(),
            "engaged" to 0xFF00E5FF.toInt(),
            "cognition" to 0xFFCFEFFF.toInt(),
            "hypothesis" to 0xFFB388FF.toInt(),
            "eventRisk" to 0xFFFFB300.toInt(),
            "favourable" to 0xFF64FFDA.toInt(),
            "deteriorating" to 0xFFFF6E40.toInt(),
            // DNA's literal #FF1744 clears AA against `background` (4.94:1) but not quite
            // `surface` (4.49:1, just under 4.5). Lightened by 2% toward white to clear both
            // — a shift no eye will notice and the one this whole file exists to catch.
            "critical" to 0xFFFF1B47.toInt(),
            "disabled" to 0xFF78909C.toInt(),
        ),
    )

    /**
     * Light mode, with the glow colour deepened wherever it carries text.
     *
     * `#00DAFF` on white is 1.8:1. Using it as `primary` in a light scheme would put white
     * label text on a cyan button that nobody can read, which is how a light mode gets
     * added and then quietly avoided by everyone who tries it.
     */
    val LIGHT = VanScheme(
        name = "light",
        primary = 0xFF00646F.toInt(),
        onPrimary = 0xFFFFFFFF.toInt(),
        background = 0xFFF4F8FA.toInt(),
        onBackground = 0xFF111C23.toInt(),
        surface = 0xFFFFFFFF.toInt(),
        onSurface = 0xFF111C23.toInt(),
        surfaceVariant = 0xFFE2EBF0.toInt(),
        onSurfaceVariant = 0xFF39505C.toInt(),
        outline = 0xFF5C7682.toInt(),
        error = 0xFFB3261E.toInt(),
        onError = 0xFFFFFFFF.toInt(),
        textTertiary = 0xFF4A6874.toInt(),
        statusRoles = mapOf(
            "monitor" to 0xFF2E7C87.toInt(),
            "engaged" to 0xFF007B89.toInt(),
            "cognition" to 0xFF63727A.toInt(),
            "hypothesis" to 0xFF8061B7.toInt(),
            "eventRisk" to 0xFF936700.toInt(),
            "favourable" to 0xFF307A68.toInt(),
            "deteriorating" to 0xFFBC512F.toInt(),
            "critical" to 0xFFE0143B.toInt(),
            "disabled" to 0xFF60737C.toInt(),
        ),
    )

    fun scheme(dark: Boolean): VanScheme = if (dark) DARK else LIGHT

    /** Relative luminance, WCAG 2.1 definition. Alpha is ignored: these are opaque roles. */
    fun relativeLuminance(argb: Int): Double {
        fun channel(shift: Int): Double {
            val srgb = ((argb shr shift) and 0xFF) / 255.0
            return if (srgb <= 0.03928) srgb / 12.92 else ((srgb + 0.055) / 1.055).pow(2.4)
        }
        return 0.2126 * channel(16) + 0.7152 * channel(8) + 0.0722 * channel(0)
    }

    fun contrastRatio(foreground: Int, background: Int): Double {
        val a = relativeLuminance(foreground)
        val b = relativeLuminance(background)
        return (max(a, b) + 0.05) / (min(a, b) + 0.05)
    }
}
