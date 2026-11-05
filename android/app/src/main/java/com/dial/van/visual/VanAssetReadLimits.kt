package com.dial.van.visual

import java.io.ByteArrayOutputStream
import java.io.InputStream

/** Bounded local asset read: do not allocate unbounded memory before deciding fallback. */
object VanAssetReadLimits {
    const val RIVE_BYTES = 8 * 1_024 * 1_024
    const val CONTEXT_BYTES = 16_384

    fun read(stream: InputStream, maximum: Int): ByteArray {
        require(maximum in 1..RIVE_BYTES)
        val output = ByteArrayOutputStream(minOf(maximum, 8_192))
        val buffer = ByteArray(minOf(maximum + 1, 8_192))
        var total = 0
        while (true) {
            val remaining = maximum - total
            val count = stream.read(buffer, 0, minOf(buffer.size, remaining + 1))
            if (count < 0) break
            if (count == 0) {
                val one = stream.read()
                if (one < 0) break
                require(total < maximum) { "Bundled character asset exceeds its safe memory bound" }
                output.write(one); total++
            } else {
                require(count <= remaining) { "Bundled character asset exceeds its safe memory bound" }
                output.write(buffer, 0, count); total += count
            }
        }
        return output.toByteArray()
    }
}
