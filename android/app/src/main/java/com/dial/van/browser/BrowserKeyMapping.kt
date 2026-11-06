package com.dial.van.browser

/** Android key identities and meta-state are not CDP virtual keys/modifier bits. */
object BrowserKeyMapping {
    data class Key(val virtualKey: Int, val modifiers: Int, val text: String)
    fun key(androidCode: Int, unicode: Int, metaState: Int, down: Boolean): Key? {
        val virtual = when (androidCode) {
            in 29..54 -> androidCode - 29 + 65 // A..Z
            in 7..16 -> androidCode - 7 + 48 // 0..9
            in 144..153 -> androidCode - 144 + 96 // numpad 0..9
            in 131..142 -> androidCode - 131 + 112 // F1..F12
            66, 160 -> 13
            67 -> 8
            112 -> 46
            61 -> 9
            111 -> 27
            62 -> 32
            19 -> 38
            20 -> 40
            21 -> 37
            22 -> 39
            122 -> 36
            123 -> 35
            92 -> 33
            93 -> 34
            59, 60 -> 16
            113, 114 -> 17
            57, 58 -> 18
            117 -> 91
            118 -> 92
            115 -> 20
            143 -> 144
            116 -> 145
            55 -> 188
            56 -> 190
            68 -> 192
            69 -> 189
            70 -> 187
            71 -> 219
            72 -> 221
            73 -> 220
            74 -> 186
            75 -> 222
            76 -> 191
            154 -> 111
            155 -> 106
            156 -> 109
            157 -> 107
            158 -> 110
            else -> 0
        }
        val modifiers = (if (metaState and 0x32 != 0) 1 else 0) or // Alt aggregate/left/right
            (if (metaState and 0x7000 != 0) 2 else 0) or // Control
            (if (metaState and 0x70000 != 0) 4 else 0) or // Meta
            (if (metaState and 0xc1 != 0) 8 else 0) // Shift
        val printable = unicode in 1..0x10ffff && unicode !in 0xd800..0xdfff
        val text = if (!down || modifiers and 6 != 0) "" else when {
            virtual == 13 -> "\r"
            printable -> String(Character.toChars(unicode))
            else -> ""
        }
        if (virtual == 0 && !printable) return null
        return Key(virtual, modifiers, text)
    }
}
