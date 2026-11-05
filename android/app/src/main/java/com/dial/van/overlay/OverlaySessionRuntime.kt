package com.dial.van.overlay

import android.os.Handler
import android.os.Looper
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.dial.van.visual.VanPresentationPreferences
import java.util.concurrent.Executors

/** One encrypted local snapshot writer. Disk I/O never runs in the composition/frame loop. */
internal class OverlaySessionRuntime(
    private val store: OverlayStateStore,
    private val ownerScope: () -> String?,
    private val nowMs: () -> Long = System::currentTimeMillis,
    listenOwner: ((() -> Unit) -> (() -> Unit))? = null,
    private val ownerInvalidated: () -> Unit = {},
) {
    private val main = Handler(Looper.getMainLooper())
    private val executor = Executors.newSingleThreadExecutor { r -> Thread(r, "van-overlay-local-state").apply { isDaemon = true } }
    val boundScope = ownerScope()
    private val storeLease = store.acquireLocalSession()
    @Volatile private var closed = false
    var ready by mutableStateOf(false); private set
    var session by mutableStateOf(OverlayLocalSession(boundScope.orEmpty())); private set
    var recoveredDraft by mutableStateOf<String?>(null); private set
    var storageMessage by mutableStateOf("Loading local preferences…"); private set
    private var revision = 0L
    private val removeOwnerListener = listenOwner?.invoke {
        main.post { if (!closed && !scopeCurrent()) invalidateOwner() }
    }
    private val writer = OverlaySessionWriter(execute = { task -> executor.execute(task) },
        persist = { encoded -> ownerScope() == boundScope && store.writeLocalSession(storeLease, encoded) },
        completed = { token, saved -> main.post {
            if (!closed && token == revision) storageMessage = when {
                !saved -> "Not saved on this device. Your current text is still here."
                !session.preferences.rememberDraft -> "Draft recovery is off."
                session.draft.isBlank() -> "Local preferences saved."
                else -> "Draft saved securely on this device."
            }
        } })

    init {
        executor.execute {
            val scope = boundScope
            val result = if (scope == null) null else runCatching {
                OverlayLocalSessionCodec.decode(store.readLocalSession(storeLease), scope, nowMs())
            }.getOrNull()
            main.post {
                if (closed) return@post
                if (!scopeCurrent()) { invalidateOwner(); return@post }
                if (result != null) {
                    revision = result.session.revision
                    recoveredDraft = result.session.draft.takeIf { it.isNotBlank() }
                    session = result.session.copy(draft = "")
                    storageMessage = when (result.status) {
                        OverlayRecoveryStatus.AVAILABLE -> "A saved draft is available. Review it before sending."
                        OverlayRecoveryStatus.EXPIRED -> "An old draft expired; preferences were restored."
                        OverlayRecoveryStatus.INVALID, OverlayRecoveryStatus.FUTURE_VERSION -> "Saved local state could not be read; safe defaults are active."
                        OverlayRecoveryStatus.WRONG_OWNER -> "No draft was restored for this owner."
                        OverlayRecoveryStatus.EMPTY -> if (store.localStorageAvailable) "Local preferences ready." else "Secure storage unavailable; this session is not saved."
                    }
                } else storageMessage = if (scope == null) "Draft recovery needs an enrolled device; this session is not saved." else "Secure storage unavailable; this session is not saved."
                ready = true
            }
        }
    }

    fun scopeCurrent(): Boolean = store.currentLocalSession(storeLease) && ownerScope() == boundScope

    fun updateDraft(value: String) {
        if (!usable()) return
        recoveredDraft = null
        session = session.copy(draft = value, savedAtMs = nowMs())
        save()
    }

    fun selectMode(mode: String) {
        if (!usable()) return
        session = session.copy(mode = mode); save()
    }

    fun preferences(value: VanPresentationPreferences) {
        if (!usable()) return
        val normalized = value.normalized()
        if (!normalized.rememberDraft) recoveredDraft = null
        session = session.copy(preferences = normalized)
        save()
    }

    fun resumeDraft() {
        if (!usable()) return
        val draft = recoveredDraft ?: return
        recoveredDraft = null
        session = session.copy(draft = draft, mode = "CHAT", savedAtMs = nowMs()); save()
    }

    fun discardDraft() {
        if (!usable()) return
        recoveredDraft = null; session = session.copy(draft = "", savedAtMs = nowMs()); save()
    }

    fun retrySave() { if (usable()) save() }

    private fun usable(): Boolean {
        if (closed || !ready) return false
        if (!scopeCurrent()) { invalidateOwner(); return false }
        return true
    }

    private fun invalidateOwner() {
        ownerInvalidated()
        recoveredDraft = null; session = OverlayLocalSession(""); ready = false
        storageMessage = "The owner or local session changed. Reopen VAN to load its current state."
    }

    private fun save() {
        val scope = boundScope
        if (scope == null || !store.localStorageAvailable) {
            storageMessage = "This session is not saved on the device."; return
        }
        // Preserve a not-yet-resumed recovery candidate when only settings/tab changes.
        val draft = if (session.preferences.rememberDraft) recoveredDraft ?: session.draft else ""
        if (draft.length > OverlayLocalSessionCodec.MAX_DRAFT_CHARS) {
            storageMessage = "Draft is too large to save locally; shorten it below 16,384 characters."
            return
        }
        revision++
        val snapshot = session.copy(scope = scope, revision = revision, draft = draft)
        val encoded = runCatching { OverlayLocalSessionCodec.encode(snapshot) }.getOrNull()
        if (encoded == null || !writer.offer(revision, encoded)) {
            storageMessage = "Local save unavailable; your current text is still here."
        } else storageMessage = "Saving locally…"
    }

    fun close() {
        if (closed) return
        closed = true
        removeOwnerListener?.invoke()
        writer.close()
        // Finish already-requested encrypted writes, without blocking the UI or
        // retaining a Service/ComposeView. No restart/resubmission work is scheduled.
        executor.shutdown()
    }
}
