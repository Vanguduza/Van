package com.dial.van.security

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class OwnerAuthorityTokenTest {

    private val subject =
        "FX-TREND-PULLBACK-01:SHADOW:" + "a".repeat(64)

    @Test
    fun pythonWireVectorMatchesExactly() {
        val prepared = OwnerAuthorityToken.prepare(
            act = "capsule-promote",
            subject = subject,
            keyId = "device-0123456789abcdef01234567",
            issuedAtUnix = 1_770_000_000L,
            lifetimeSeconds = 300L,
            nonce = "nonce_-123",
        )

        assertEquals(
            "van-oa1|capsule-promote|" + subject +
                "|1770000000|1770000300|nonce_-123",
            prepared.canonical,
        )
        assertEquals(
            "{\"act\":\"capsule-promote\",\"exp\":1770000300,\"iat\":1770000000," +
                "\"kid\":\"device-0123456789abcdef01234567\",\"nonce\":\"nonce_-123\"," +
                "\"subject\":\"" + subject + "\"}",
            prepared.payloadJson,
        )
        assertEquals(
            "eyJhY3QiOiJjYXBzdWxlLXByb21vdGUiLCJleHAiOjE3NzAwMDAzMDAsImlhdCI6MTc3MDAwMDAwMCwia2lkIjoiZGV2aWNlLTAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2NyIsIm5vbmNlIjoibm9uY2VfLTEyMyIsInN1YmplY3QiOiJGWC1UUkVORC1QVUxMQkFDSy0wMTpTSEFET1c6YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYSJ9",
            prepared.payloadBase64Url,
        )
        assertEquals(
            "van-oa1.eyJhY3QiOiJjYXBzdWxlLXByb21vdGUiLCJleHAiOjE3NzAwMDAzMDAsImlhdCI6MTc3MDAwMDAwMCwia2lkIjoiZGV2aWNlLTAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2NyIsIm5vbmNlIjoibm9uY2VfLTEyMyIsInN1YmplY3QiOiJGWC1UUkVORC1QVUxMQkFDSy0wMTpTSEFET1c6YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYSJ9.AQIDBAUGBwgJCgsMDQ4PEA",
            prepared.assembleFromSignatureBase64("AQIDBAUGBwgJCgsMDQ4PEA=="),
        )
    }

    @Test
    fun jsonEscapingMatchesPythonEnsureAsciiContract() {
        val prepared = OwnerAuthorityToken.prepare(
            act = "capsule-promote",
            subject = "quoted:\" slash:\\ newline:\n snowman:☃",
            keyId = "device-test",
            issuedAtUnix = 10,
            lifetimeSeconds = 1,
            nonce = "n",
        )
        assertEquals(
            "{\"act\":\"capsule-promote\",\"exp\":11,\"iat\":10,\"kid\":\"device-test\"," +
                "\"nonce\":\"n\",\"subject\":\"quoted:\\\" slash:\\\\ newline:\\n snowman:\\u2603\"}",
            prepared.payloadJson,
        )
    }

    @Test
    fun actTokensCannotBecomeStandingAuthority() {
        assertFailsWith<IllegalArgumentException> {
            OwnerAuthorityToken.prepare(
                act = "capsule-promote",
                subject = "x",
                keyId = "device-test",
                issuedAtUnix = 10,
                lifetimeSeconds = 301,
                nonce = "n",
            )
        }
    }
}
