package com.dial.van.preview

import com.dial.van.visual.VanEffectBudget
import java.io.File
import javax.imageio.ImageIO

/**
 * Writes the owner-facing preview sheets.
 *
 * Run with `./gradlew :visual-preview:renderVanPreviews` from `android/`.
 *
 * The output directory is rebuilt from scratch on every run. This prevents historical evidence
 * directories (for example Rev 2.1) from being uploaded beside current Rev 2.3 evidence and being
 * mistaken for part of the active visual authority.
 */
fun main(args: Array<String>) {
    val outputDir = args.firstOrNull()
        ?.let(::File)
        ?: File(AwtVanRenderer.repoRoot(), "artifacts/release/preview")
    if (outputDir.exists() && !outputDir.deleteRecursively()) {
        error("Unable to clean stale preview evidence at ${outputDir.absolutePath}")
    }
    check(outputDir.mkdirs()) { "Unable to create preview output directory ${outputDir.absolutePath}" }

    val sheets = listOf(
        "van_floating_overlay_preview.png" to VanPreviewSheets.floatingOverlaySheet(),
        "van_state_matrix.png" to VanPreviewSheets.stateSheet(),
        "van_flame_aura.png" to VanPreviewSheets.flameAuraSheet(),
        "van_trade_aura.png" to VanAuraMotion.tradeSheet(),
        "van_state_matrix_reduced_motion.png" to VanPreviewSheets.stateSheet(reducedMotion = true),
        "van_state_matrix_low.png" to VanPreviewSheets.stateSheet(budget = VanEffectBudget.LOW),
        "van_state_matrix_static.png" to VanPreviewSheets.stateSheet(budget = VanEffectBudget.STATIC),
        "van_action_board.png" to VanPreviewSheets.actionSheet(),
        "van_command_centre.png" to VanPreviewSheets.commandCentreSheet(),
        "van_glass_tokens.png" to VanPreviewSheets.glassTokenSheet(),
        "van_aura_topology.png" to VanPreviewSheets.auraTopologySheet(),
        "van_orthogonal_presence.png" to VanEvidenceMatrix.orthogonalPresenceBoard(),
    )

    println("owner-art bitmap rung retired — previews use the current Canvas/Rive visual pipeline")

    sheets.forEach { (name, image) ->
        val file = File(outputDir, name)
        ImageIO.write(image, "png", file)
        println("wrote ${file.absolutePath} (${image.width}x${image.height}, ${file.length()} bytes)")
    }
    // The matrix writes the truthful Command Centre boards itself now; the
    // overwrite-and-patch-the-manifest pass that used to follow is gone (P2-VIS-003).
    // Aura Rev 2 — 8-second motion clips (CI evidence; git-ignored).
    VanAuraMotion.writeMotionClips(outputDir)
    println("wrote aura motion clips under ${File(outputDir, "motion").absolutePath}")
    VanEvidenceMatrix.writeAll(outputDir)
    println(
        "wrote named Rev ${VanEvidenceMatrix.AUTHORITY_REVISION} evidence matrix under " +
            File(outputDir, VanEvidenceMatrix.EVIDENCE_DIR).absolutePath,
    )
}
