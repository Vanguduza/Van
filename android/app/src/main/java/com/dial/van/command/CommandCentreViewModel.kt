package com.dial.van.command

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import com.dial.van.command.nav.VanNavModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * The Command Centre's surviving state (P3-AND-007), now over the DNA §4 route graph.
 *
 * Held in a `ViewModel` with a `SavedStateHandle` rather than in `remember`, so it survives
 * both a configuration change and process death — the case that actually bites a resident
 * assistant is Android reclaiming the process overnight, not a rotation.
 *
 * The route the owner was on is a `String` (a `NavHost` route, concrete — arguments filled
 * in), never an enum ordinal: [VanNavModel.restore] is what decides a saved value is still a
 * destination this build knows about, and it is pure and executed in `android/verification`.
 * This class is the Android plumbing around it — [start] is called once per composition with
 * the Activity's freshly-computed launch destination and only acts on a genuinely new
 * instance (mirrors the old `CommandCentreViewModel.start`'s reasoning: a restored instance
 * already knows where the owner was, and replaying the launch intent's destination over that
 * would move them). `CommandCentreActivity`'s `NavHostController` then publishes every
 * further destination change here via `currentBackStackEntryFlow`.
 */
class CommandCentreViewModel(
    private val state: SavedStateHandle,
) : ViewModel() {

    private val _currentRoute = MutableStateFlow(VanNavModel.restore(state[KEY_ROUTE]))
    val currentRoute: StateFlow<String> = _currentRoute.asStateFlow()

    /** What the `NavHost` should start on. Stable across recomposition once [start] has run. */
    val startDestination: String get() = _currentRoute.value

    /** The owner's half-typed message on the Work command bar, so a rotation keeps it. */
    var draft: String
        get() = state[KEY_DRAFT] ?: ""
        set(value) {
            state[KEY_DRAFT] = value
        }

    /**
     * Only on a genuinely fresh instance: a restored one already has a route in
     * [SavedStateHandle] (even if that route is Home, because [onRouteChanged] wrote it),
     * and a launch intent replayed after process death would move the owner off the screen
     * Android just recreated them onto.
     */
    fun start(initial: String) {
        if (state.get<String>(KEY_ROUTE) == null) onRouteChanged(initial)
    }

    /** Called from the `NavHostController`'s back-stack flow on every navigation. */
    fun onRouteChanged(route: String) {
        _currentRoute.value = route
        state[KEY_ROUTE] = route
    }

    private companion object {
        const val KEY_ROUTE = "command_centre.route"
        const val KEY_DRAFT = "command_centre.draft"
    }
}
