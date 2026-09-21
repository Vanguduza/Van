package com.dial.van.security

import java.security.MessageDigest
import org.json.JSONArray
import org.json.JSONObject

/**
 * One spelling of a JSON document, so that a signature or a digest means the same thing on
 * both sides of the wire.
 *
 * The gateway writes `json.dumps(value, sort_keys=True, separators=(",", ":"))`. Anything
 * on this side that hashes or verifies a document the gateway also hashes has to produce
 * those exact bytes — keys sorted, no whitespace, no trailing separators. There were two
 * copies of this rule in the app already (the connectivity manifest verifier and the
 * session envelope), which is one copy too many: the failure mode of a second
 * canonicalizer is a signature that verifies in the tests written beside it and nowhere
 * else.
 *
 * `tests/contracts/test_cross_language_vectors.py` compares the bytes this produces with
 * what Python produces for the same documents.
 */
object VanCanonicalJson {

    /** The bytes the gateway signs or digests for [json]. */
    fun bytes(json: JSONObject): ByteArray = render(json).toByteArray(Charsets.UTF_8)

    /** Lowercase hex SHA-256 over [bytes]. */
    fun sha256Hex(json: JSONObject): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(bytes(json))
        return digest.joinToString("") { "%02x".format(it) }
    }

    fun render(json: JSONObject): String = StringBuilder().also { append(json, it) }.toString()

    private fun append(value: Any?, out: StringBuilder) {
        when (value) {
            is JSONObject -> {
                out.append('{')
                value.keys().asSequence().sorted().forEachIndexed { index, key ->
                    if (index > 0) out.append(',')
                    out.append(quote(key)).append(':')
                    append(value.get(key), out)
                }
                out.append('}')
            }
            is JSONArray -> {
                out.append('[')
                for (index in 0 until value.length()) {
                    if (index > 0) out.append(',')
                    append(value.get(index), out)
                }
                out.append(']')
            }
            is String -> out.append(quote(value))
            is Boolean -> out.append(if (value) "true" else "false")
            null, JSONObject.NULL -> out.append("null")
            // Python renders an integral float as `1.0` and an int as `1`; JSONObject keeps
            // the two apart the same way, so `toString()` agrees for both. Only the Double
            // case needs care, and it is handled by whoever puts the value in.
            else -> out.append(value.toString())
        }
    }

    /**
     * Python's `json.dumps` escapes exactly these and leaves everything else, including
     * non-ASCII, as literal UTF-8 when `ensure_ascii=False`. The gateway calls `dumps`
     * with its default `ensure_ascii=True`, which escapes non-ASCII as `\uXXXX` — so this
     * does too, or a profile alias with an accent in it would digest differently on the
     * two sides and the owner's command would be refused as a duplicate of nothing.
     */
    private fun quote(text: String): String {
        val out = StringBuilder("\"")
        for (ch in text) {
            when {
                ch == '"' -> out.append("\\\"")
                ch == '\\' -> out.append("\\\\")
                ch == '\n' -> out.append("\\n")
                ch == '\r' -> out.append("\\r")
                ch == '\t' -> out.append("\\t")
                ch == '\b' -> out.append("\\b")
                ch == '\u000C' -> out.append("\\f")
                ch < ' ' || ch.code > 0x7E -> out.append(String.format("\\u%04x", ch.code))
                else -> out.append(ch)
            }
        }
        return out.append('"').toString()
    }
}
