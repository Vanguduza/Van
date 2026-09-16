package com.dial.van.preview

import com.dial.van.visual.VanEffectBudget
import java.io.File
import javax.imageio.ImageIO

/**
 * Writes the owner-facing preview sheets.
 *
 * Run with `./gradlew :visual-preview:renderVanPreviews` from `android/`.
 */
fun main(args: Array<String>) {
    val outputDir = args.firstOrNull()
        ?.let(::File)
        ?: File(AwtVanRenderer.repoRoot(), "artifacts/release/preview")
    outputDir.mkdirs()

    val sheets = listOf(
        "van_floating_overlay_preview.png" to VanPreviewSheets.floatingOverlaySheet(),
        "van_state_matrix.png" to VanPreviewSheets.stateSheet(),
        "van_state_matrix_reduced_motion.png" to VanPreviewSheets.stateSheet(reducedMotion = true),
        "van_state_matrix_low.png" to VanPreviewSheets.stateSheet(budget = VanEffectBudget.LOW),
        "van_state_matrix_static.png" to VanPreviewSheets.stateSheet(budget = VanEffectBudget.STATIC),
        "van_action_board.png" to VanPreviewSheets.actionSheet(),
        "van_command_centre.png" to VanPreviewSheets.commandCentreSheet(),
        "van_glass_tokens.png" to VanPreviewSheets.glassTokenSheet(),
    )

    println(
        if (OwnerArt.available()) {
            "owner art pack: all ${com.dial.van.visual.VanArtPose.entries.size} poses packaged"
        } else {
            "owner art pack: incomplete — falling back to the VanScene Canvas character"
        },
    )

    sheets.forEach { (name, image) ->
        val file = File(outputDir, name)
        ImageIO.write(image, "png", file)
        println("wrote ${file.absolutePath} (${image.width}x${image.height}, ${file.length()} bytes)")
    }
    VanEvidenceMatrix.writeAll(outputDir)
    println("wrote named Rev 2.1 evidence matrix under ${File(outputDir, "rev21").absolutePath}")
}
