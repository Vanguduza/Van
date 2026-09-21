package com.dial.van.browser

/**
 * Rev 1.5 §17.1 — the tabs the owner sees, and where their truth comes from.
 *
 * "Chromium target state is authoritative." That sentence is the whole design: the phone
 * holds a *projection* of the targets the Browser Runtime reports, it never invents one,
 * and a tab it has no event for does not exist. The alternative — a phone that adds a tab
 * optimistically when the owner taps "New tab" — produces a list that disagrees with the
 * browser, and the disagreement shows up as a tab that cannot be switched to.
 *
 * So `BrowserTabs` is a reducer over the four events §17.1 names and nothing else. Pure,
 * which is why it runs in the harness: every ordering that a lossy channel can produce —
 * an update before its create, a close for the active tab, two activations — is a case
 * that can be executed here and not on a phone.
 */

/** §17.1's model, one entry per Chromium target. */
data class BrowserTab(
    val targetId: String,
    val title: String = "",
    val url: String = "",
    val urlDigest: String = "",
    val faviconRef: String? = null,
    val loading: Boolean = false,
    val canGoBack: Boolean = false,
    val canGoForward: Boolean = false,
    val securityState: SecurityState = SecurityState.UNKNOWN,
) {
    /**
     * What the owner is shown when the page has no title yet.
     *
     * Never the raw URL for an untitled page in a *secure-unknown* state: a page whose
     * security VAN cannot report is one whose address bar is the least reliable thing on
     * the screen.
     */
    val ownerReadableLabel: String
        get() = when {
            title.isNotBlank() -> title
            url.isNotBlank() -> url
            loading -> "Loading…"
            else -> "New tab"
        }
}

enum class SecurityState {
    /** No information yet. Shown as neither safe nor unsafe. */
    UNKNOWN,
    SECURE,
    INSECURE,
    /** A certificate problem the owner was asked about. */
    BROKEN,
}

/** §17.1's four events, and nothing that is not one of them. */
sealed interface TabEvent {
    val targetId: String

    data class Created(override val targetId: String, val openerTargetId: String? = null) : TabEvent

    data class Updated(
        override val targetId: String,
        val title: String? = null,
        val url: String? = null,
        val urlDigest: String? = null,
        val faviconRef: String? = null,
        val loading: Boolean? = null,
        val canGoBack: Boolean? = null,
        val canGoForward: Boolean? = null,
        val securityState: SecurityState? = null,
    ) : TabEvent

    data class Activated(override val targetId: String) : TabEvent

    data class Closed(override val targetId: String) : TabEvent
}

data class TabState(
    val tabs: List<BrowserTab> = emptyList(),
    val activeTargetId: String? = null,
) {
    val active: BrowserTab? get() = tabs.firstOrNull { it.targetId == activeTargetId }

    fun indexOf(targetId: String): Int = tabs.indexOfFirst { it.targetId == targetId }
}

object BrowserTabs {

    /**
     * Apply one event. The projection only ever moves towards what the host reported.
     *
     * An `Updated` for a target with no `Created` creates it. That is not sloppiness: the
     * events arrive over a channel that can drop, and a tab the host is telling us about
     * is a tab that exists. Discarding the update would leave the owner with a browser
     * showing a page that is not in their tab list.
     */
    fun reduce(state: TabState, event: TabEvent): TabState = when (event) {
        is TabEvent.Created -> created(state, event)
        is TabEvent.Updated -> updated(state, event)
        is TabEvent.Activated -> activated(state, event)
        is TabEvent.Closed -> closed(state, event)
    }

    fun reduceAll(state: TabState, events: List<TabEvent>): TabState =
        events.fold(state, ::reduce)

    private fun created(state: TabState, event: TabEvent.Created): TabState {
        if (state.indexOf(event.targetId) >= 0) return state
        val tab = BrowserTab(targetId = event.targetId)
        // A tab opened from another one goes next to it, which is where the owner looks
        // for it. Everything else goes at the end.
        val openerIndex = event.openerTargetId?.let(state::indexOf) ?: -1
        val tabs = state.tabs.toMutableList()
        if (openerIndex >= 0) tabs.add(openerIndex + 1, tab) else tabs.add(tab)
        // Creation does not activate. §17.1 has a separate event for that, and a target
        // Chromium opened in the background is a tab the owner has not been moved to.
        return state.copy(tabs = tabs)
    }

    private fun updated(state: TabState, event: TabEvent.Updated): TabState {
        val index = state.indexOf(event.targetId)
        val existing = state.tabs.getOrNull(index) ?: BrowserTab(targetId = event.targetId)
        val merged = existing.copy(
            title = event.title ?: existing.title,
            url = event.url ?: existing.url,
            urlDigest = event.urlDigest ?: existing.urlDigest,
            faviconRef = event.faviconRef ?: existing.faviconRef,
            loading = event.loading ?: existing.loading,
            canGoBack = event.canGoBack ?: existing.canGoBack,
            canGoForward = event.canGoForward ?: existing.canGoForward,
            securityState = event.securityState ?: existing.securityState,
        )
        val tabs = state.tabs.toMutableList()
        if (index >= 0) tabs[index] = merged else tabs.add(merged)
        return state.copy(tabs = tabs)
    }

    private fun activated(state: TabState, event: TabEvent.Activated): TabState {
        val known = state.indexOf(event.targetId) >= 0
        val tabs = if (known) state.tabs else state.tabs + BrowserTab(targetId = event.targetId)
        return state.copy(tabs = tabs, activeTargetId = event.targetId)
    }

    private fun closed(state: TabState, event: TabEvent.Closed): TabState {
        val index = state.indexOf(event.targetId)
        if (index < 0) return state
        val tabs = state.tabs.toMutableList()
        tabs.removeAt(index)
        if (state.activeTargetId != event.targetId) {
            return state.copy(tabs = tabs)
        }
        // The active tab went away. The owner is looking at it, so something has to take
        // its place, and it is the neighbour rather than the first tab: closing the fourth
        // of five and landing on the first is a browser nobody recognises.
        val next = tabs.getOrNull(index) ?: tabs.getOrNull(index - 1)
        return state.copy(tabs = tabs, activeTargetId = next?.targetId)
    }
}

/**
 * §17.6 — what the system Back gesture does, in order.
 *
 * The order is the specification and the last clause is the point: **Back must not close
 * the browser while the page has history.** An owner three pages into a site and one tap
 * from losing all of it is the behaviour this exists to forbid.
 */
enum class BackOutcome {
    /** A sheet, menu or dialog drawn over the page. */
    CLOSE_TRANSIENT_PANEL,

    /** The address bar is being edited; leave the edit, keep the page. */
    LEAVE_ADDRESS_EDIT,

    /** Chromium has history. Back goes to the page, not to Android. */
    BROWSER_BACK,

    /** Nothing left that belongs to the browser. Android's own back. */
    ACTIVITY_BACK,
}

object BrowserBackPolicy {

    fun decide(
        transientPanelOpen: Boolean,
        addressBarEditing: Boolean,
        canGoBack: Boolean,
    ): BackOutcome = when {
        transientPanelOpen -> BackOutcome.CLOSE_TRANSIENT_PANEL
        addressBarEditing -> BackOutcome.LEAVE_ADDRESS_EDIT
        canGoBack -> BackOutcome.BROWSER_BACK
        else -> BackOutcome.ACTIVITY_BACK
    }
}
