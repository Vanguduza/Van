package com.dial.van.visual

import com.dial.van.design.StatusSemantics
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Contrast coverage for the additive `com.dial.van.design.VanColorTokens` roles added to
 * [VanScheme] (`textTertiary`, `statusRoles`) — kept separate from [VanPaletteTest] so that
 * file's own tests, and the exact set of fields it exercises, are untouched by this addition.
 */
class VanDesignRolesTest {

    @Test
    fun `every design role clears AA body-text contrast against background and surface`() {
        for (scheme in listOf(VanPalette.DARK, VanPalette.LIGHT)) {
            for (pair in scheme.designRolePairs()) {
                val ratio = VanPalette.contrastRatio(pair.foreground, pair.background)
                assertTrue(
                    ratio >= VanPalette.AA_NORMAL,
                    "${scheme.name}.${pair.name} is %.2f:1, below %.1f".format(ratio, VanPalette.AA_NORMAL),
                )
            }
        }
    }

    @Test
    fun `statusRoles carries exactly the StatusSemantics role vocabulary`() {
        for (scheme in listOf(VanPalette.DARK, VanPalette.LIGHT)) {
            assertEquals(
                StatusSemantics.ALL_ROLES,
                scheme.statusRoles.keys,
                "${scheme.name}.statusRoles does not match StatusSemantics.ALL_ROLES",
            )
        }
    }

    @Test
    fun `the light scheme deepens every status role rather than reusing the dark one`() {
        // The mistake this whole palette file exists to prevent, restated for the new roles:
        // a status colour that is legible on navy and unreadable on white.
        for (role in StatusSemantics.ALL_ROLES) {
            val dark = VanPalette.DARK.statusRoles.getValue(role)
            val light = VanPalette.LIGHT.statusRoles.getValue(role)
            assertTrue(dark != light, "status.$role was not deepened for light mode")
            assertTrue(
                VanPalette.relativeLuminance(light) < VanPalette.relativeLuminance(dark),
                "status.$role's light variant is not darker than its dark-mode vivid colour",
            )
        }
    }

    @Test
    fun `textTertiary is distinct from onSurfaceVariant`() {
        // DNA §2 draws text.tertiary as one step past text.secondary (onSurfaceVariant); if
        // they collapsed to the same value there would be nothing for tertiary to add.
        for (scheme in listOf(VanPalette.DARK, VanPalette.LIGHT)) {
            assertTrue(scheme.textTertiary != scheme.onSurfaceVariant, "${scheme.name}.textTertiary == onSurfaceVariant")
        }
    }
}
