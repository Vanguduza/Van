package com.dial.van.command

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * The Command Centre's surviving state (P3-AND-007).
 *
 * Held in a `ViewModel` with a `SavedStateHandle` rather than in `remember`, so it survives
 * both a configuration change (rotation, font scale, day/night) and process death. The
 * distinction matters: a `rememberSaveable` alone covers rotation, and the case that
 * actually bites a resident assistant is Android reclaiming the process overnight.
 *
 * The navigation rules themselves are in [CommandNav], which is pure and executed in
 * `android/verification`. This class is the Android plumbing around them and nothing else.
 */
class CommandCentreViewModel(
    private val state: SavedStateHandle,
) : ViewModel() {

    private val _selected = MutableStateFlow(CommandNav.restore(state[KEY_MODULE]))
    val selected: StateFlow<CommandModule> = _selected.asStateFlow()

    /** The owner's half-typed message, so a rotation does not discard it. */
    var draft: String
        get() = state[KEY_DRAFT] ?: ""
        set(value) {
            state[KEY_DRAFT] = value
        }

    fun start(initial: CommandModule) {
        // Only on a genuinely fresh instance: a restored one already knows where the owner
        // was, and an intent extra replayed after process death would move them.
        if (state.get<String>(KEY_MODULE) == null) navigate(initial)
    }

    fun navigate(module: CommandModule) {
        _selected.value = module
        state[KEY_MODULE] = CommandNav.save(module)
    }

    /** True when back was handled here; false when the Activity should handle it. */
    fun back(): Boolean {
        val target = CommandNav.back(_selected.value) ?: return false
        navigate(target)
        return true
    }

    private companion object {
        const val KEY_MODULE = "command_centre.module"
        const val KEY_DRAFT = "command_centre.draft"
    }
}
