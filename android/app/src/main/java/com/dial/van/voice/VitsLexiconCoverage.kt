package com.dial.van.voice

/** Matches the admitted VITS English lexicon frontend and refuses words it would drop. */
class VitsLexiconCoverage private constructor(private val vocabulary: Set<String>) {
    fun canSpeak(text: String): Boolean {
        if (text.isBlank() || text.length > 32_768 || text.any { it.code > 127 }) return false
        val word = StringBuilder()
        var heardWord = false
        fun flush(): Boolean {
            if (word.isEmpty()) return true
            val found = word.toString().lowercase(java.util.Locale.ROOT) in vocabulary
            word.setLength(0)
            if (found) heardWord = true
            return found
        }
        for (character in text) {
            when {
                character.isLetterOrDigit() || character == '\'' -> word.append(character)
                character.isWhitespace() -> if (!flush()) return false
                else -> {
                    if (!flush()) return false
                    if (character !in ".;!?-:," && character.toString() !in vocabulary) return false
                }
            }
        }
        return flush() && heardWord
    }

    companion object {
        fun parse(tokens: Sequence<String>, lexicon: Sequence<String>): VitsLexiconCoverage {
            val symbols = tokens.mapNotNull { line ->
                val values = line.trim().split(Regex("\\s+"))
                when {
                    values.size == 1 && values[0].toIntOrNull() != null -> " "
                    values.size == 2 && values[1].toIntOrNull() != null -> values[0]
                    else -> null
                }
            }.toSet()
            val words = mutableSetOf<String>()
            lexicon.forEach { line ->
                val values = line.trim().split(Regex("\\s+"))
                if (values.size >= 2 && values.drop(1).all { it in symbols }) {
                    words.add(values[0].lowercase(java.util.Locale.ROOT))
                }
            }
            return VitsLexiconCoverage(words)
        }
    }
}
