package com.dial.van.security

import java.security.KeyPairGenerator
import java.security.Signature
import java.security.spec.ECGenParameterSpec
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class DeviceProofQueryTargetTest {
    @Test fun `a signed owner DELETE cannot change its subject predicate or scope query`() {
        val key = KeyPairGenerator.getInstance("EC").apply { initialize(ECGenParameterSpec("secp256r1")) }.generateKeyPair()
        val target = "/v1/context/facts?subject=owner&predicate=preference&scope=global"
        fun input(path: String) = DeviceProofCanonical.signingInput("DELETE", path, "owner-device", 1_000,
            DeviceProofCanonical.sha256Hex(byteArrayOf()))
        val signature = Signature.getInstance("SHA256withECDSA").run {
            initSign(key.private); update(input(target)); sign()
        }
        fun verifies(path: String) = Signature.getInstance("SHA256withECDSA").run {
            initVerify(key.public); update(input(path)); verify(signature)
        }
        assertTrue(verifies(target))
        assertFalse(verifies(target.replace("subject=owner", "subject=another")))
        assertFalse(verifies(target.replace("predicate=preference", "predicate=identity")))
        assertFalse(verifies(target.replace("scope=global", "scope=project")))
        assertFalse(verifies(target.substringBefore('?')))
    }
}
