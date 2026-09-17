package com.dial.van.voice

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

data class VanVoiceUiState(
    val listening: Boolean = false,
    val partialTranscript: String = "",
    val finalTranscript: String? = null,
    val errorCode: Int? = null,
)

/** Process-local voice presentation state; credentials and audio are never persisted here. */
class VanVoiceUiStore {
    private val _state = MutableStateFlow(VanVoiceUiState())
    val state: StateFlow<VanVoiceUiState> = _state.asStateFlow()

    fun listening(value: Boolean) {
        _state.update { current ->
            current.copy(
                listening = value,
                errorCode = if (value) null else current.errorCode,
                partialTranscript = if (value && !current.listening) "" else current.partialTranscript,
            )
        }
    }

    fun partial(text: String) {
        _state.update { it.copy(partialTranscript = text, errorCode = null) }
    }

    fun final(text: String) {
        _state.update {
            it.copy(
                listening = false,
                partialTranscript = "",
                finalTranscript = text.ifBlank { null },
                errorCode = null,
            )
        }
    }

    fun error(code: Int) {
        _state.update { it.copy(listening = false, errorCode = code) }
    }
}
