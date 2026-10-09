package com.dial.van.security

/** Reads the fifth KeyDescription field without interpreting or trusting the attestation. */
object AttestationChallenge {
    fun read(sequence: ByteArray): ByteArray? = runCatching {
        fun field(at: Int): Triple<Int, Int, Int> {
            require(at >= 0 && at + 2 <= sequence.size)
            val tag = sequence[at].toInt() and 0xff
            var start = at + 2
            val first = sequence[at + 1].toInt() and 0xff
            val length = if (first < 128) first else {
                val count = first and 0x7f
                require(count in 1..4 && start + count <= sequence.size)
                var size = 0L
                repeat(count) { size = (size shl 8) or (sequence[start++].toLong() and 0xff) }
                require(size <= Int.MAX_VALUE)
                size.toInt()
            }
            require(length <= sequence.size - start)
            return Triple(tag, start, start + length)
        }
        val outer = field(0)
        require(outer.first == 0x30 && outer.third == sequence.size)
        var cursor = outer.second
        listOf(0x02, 0x0a, 0x02, 0x0a).forEach { expected ->
            val value = field(cursor)
            require(value.first == expected && value.third <= outer.third)
            cursor = value.third
        }
        val challenge = field(cursor)
        require(challenge.first == 0x04 && challenge.third <= outer.third)
        sequence.copyOfRange(challenge.second, challenge.third)
    }.getOrNull()
}
