package com.dial.van.preview

/**
 * Extracts shippable Van assets from the owner-supplied design boards.
 *
 * Run with `./gradlew :visual-preview:extractOwnerArt` from `android/`.
 */
fun main() {
    val repoRoot = AwtVanRenderer.repoRoot()
    val written = OwnerArtExtractor.run(repoRoot)
    written.forEach { file ->
        println("wrote ${file.relativeTo(repoRoot)} (${file.length()} bytes)")
    }
    println("${written.size} files written")
}
