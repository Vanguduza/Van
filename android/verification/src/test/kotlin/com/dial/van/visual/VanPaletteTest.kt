package com.dial.van.visual

import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

/**
 * P3-AND-008 — no light theme, no `values-night`, and a deprecated parent theme.
 *
 * "Is this readable" is an arithmetic question with a published answer, so it is answered
 * here rather than by looking at a screenshot. The specific failure being guarded is the
 * tempting one: shipping a light mode that is the dark palette with the background flipped,
 * which puts VAN's glow cyan on white at 1.8:1.
 */
class VanPaletteTest {

    private val res = File("../app/src/main/res")

    @Test
    fun `both schemes carry body text at AA`() {
        for (scheme in listOf(VanPalette.DARK, VanPalette.LIGHT)) {
            for (pair in scheme.textPairs()) {
                val ratio = VanPalette.contrastRatio(pair.foreground, pair.background)
                assertTrue(
                    ratio >= VanPalette.AA_NORMAL,
                    "${scheme.name}.${pair.name} is %.2f:1, below %.1f".format(ratio, VanPalette.AA_NORMAL),
                )
            }
        }
    }

    @Test
    fun `the outline is visible against its surface`() {
        for (scheme in listOf(VanPalette.DARK, VanPalette.LIGHT)) {
            val ratio = VanPalette.contrastRatio(scheme.outline, scheme.surface)
            assertTrue(
                ratio >= VanPalette.AA_LARGE,
                "${scheme.name}.outline is %.2f:1".format(ratio),
            )
        }
    }

    @Test
    fun `the glow cyan is not used as a light-mode primary`() {
        // This is the mistake the light scheme exists to avoid, stated as a number: white
        // label text on #00DAFF is unreadable, and a light mode that ships it is a light
        // mode everybody switches back out of.
        val naive = VanPalette.contrastRatio(0xFFFFFFFF.toInt(), VanGlassTokens.ACCENT_CYAN)
        assertTrue(naive < VanPalette.AA_NORMAL, "the premise of this test changed: %.2f".format(naive))
        assertNotEquals(VanGlassTokens.ACCENT_CYAN, VanPalette.LIGHT.primary)
    }

    @Test
    fun `the light scheme is not the dark one with the background flipped`() {
        assertTrue(
            VanPalette.relativeLuminance(VanPalette.LIGHT.background) > 0.7,
            "light mode is not light",
        )
        assertTrue(
            VanPalette.relativeLuminance(VanPalette.DARK.background) < 0.05,
            "dark mode is not dark",
        )
        assertNotEquals(VanPalette.DARK.onBackground, VanPalette.LIGHT.onBackground)
        assertNotEquals(VanPalette.DARK.surfaceVariant, VanPalette.LIGHT.surfaceVariant)
    }

    @Test
    fun `contrast arithmetic matches the published values`() {
        // Anchors from WCAG 2.1: black on white is 21:1 and a colour against itself is 1:1.
        assertEquals(21.0, VanPalette.contrastRatio(0xFF000000.toInt(), 0xFFFFFFFF.toInt()), 0.01)
        assertEquals(1.0, VanPalette.contrastRatio(0xFF3366CC.toInt(), 0xFF3366CC.toInt()), 1e-9)
        // #767676 on white is the canonical 4.54:1 boundary case.
        assertEquals(4.54, VanPalette.contrastRatio(0xFF767676.toInt(), 0xFFFFFFFF.toInt()), 0.01)
    }

    @Test
    fun `scheme selection follows the mode`() {
        assertEquals(VanPalette.DARK, VanPalette.scheme(dark = true))
        assertEquals(VanPalette.LIGHT, VanPalette.scheme(dark = false))
    }

    @Test
    fun `the window theme agrees with the palette`() {
        // The window theme is resolved by the platform before any Kotlin runs, so these two
        // colours are necessarily written twice. Drift between them is the navy flash on
        // every launch of a light-mode app, which is exactly the class of defect that gets
        // noticed by owners and never by a build.
        assertEquals(hex(VanPalette.LIGHT.background), windowBackground("values"))
        assertEquals(hex(VanPalette.DARK.background), windowBackground("values-night"))
    }

    @Test
    fun `the deprecated parent theme is gone and a night configuration exists`() {
        val light = File(res, "values/themes.xml").readText()
        val night = File(res, "values-night/themes.xml").readText()
        for (text in listOf(light, night)) {
            assertTrue(
                !text.contains("parent=\"android:Theme.Material"),
                "the deprecated Material parent is still declared",
            )
            assertTrue(text.contains("android:Theme.DeviceDefault"), "no DeviceDefault parent")
            // DayNight would not resolve on this app's minSdk, and a theme that silently
            // falls back is a theme nobody notices is missing.
            assertTrue(
                !text.contains("parent=\"android:Theme.DeviceDefault.DayNight"),
                "DayNight needs API 29; minSdk is 26",
            )
        }
        assertTrue(light.contains("Theme.Van.Transparent"), "the share intake has no theme")
        assertTrue(night.contains("Theme.Van.Transparent"), "the share intake has no night theme")
    }

    private fun windowBackground(dir: String): String =
        Regex("""<style name="Theme\.Van" .*?</style>""", RegexOption.DOT_MATCHES_ALL)
            .find(File(res, "$dir/themes.xml").readText())
            ?.value
            ?.let { Regex("""windowBackground">(#[0-9A-Fa-f]{6})<""").find(it)?.groupValues?.get(1) }
            ?.uppercase()
            ?: error("no Theme.Van windowBackground in $dir/themes.xml")

    private fun hex(argb: Int): String = "#%06X".format(argb and 0xFFFFFF)
}
