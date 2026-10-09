package com.dial.van.security

import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertNull

class AttestationChallengeTest {
    private fun length(size: Int) = if (size < 128) byteArrayOf(size.toByte()) else byteArrayOf(0x81.toByte(), size.toByte())
    private fun sequence(challenge: ByteArray): ByteArray {
        val fields = byteArrayOf(2, 1, 3, 10, 1, 2, 2, 1, 4, 10, 1, 2) + byteArrayOf(4) + length(challenge.size) + challenge +
            byteArrayOf(4, 0, 0x30, 0, 0x30, 0)
        return byteArrayOf(0x30) + length(fields.size) + fields
    }
    @Test fun `reads the challenge in the Android KeyDescription fifth field`() {
        assertContentEquals("challenge".toByteArray(), AttestationChallenge.read(sequence("challenge".toByteArray())))
    }
    @Test fun `long form DER length preserves every challenge byte`() {
        val challenge = ByteArray(130) { it.toByte() }
        assertContentEquals(challenge, AttestationChallenge.read(sequence(challenge)))
    }
    @Test fun `truncated or malformed DER cannot match a challenge`() {
        val correct = sequence("challenge".toByteArray())
        assertNull(AttestationChallenge.read(correct.copyOf(correct.size - 1)))
        assertNull(AttestationChallenge.read(byteArrayOf(0x30, 0x80.toByte(), 0, 0)))
        assertNull(AttestationChallenge.read(correct.apply { this[14] = 2 }))
    }
}
