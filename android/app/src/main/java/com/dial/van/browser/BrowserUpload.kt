package com.dial.van.browser

/**
 * Rev 1.5 §19 — a page asked for a file, and the owner's phone has it.
 *
 * The sentence that shapes this module is the last one in the section: **the file content
 * must not be logged or injected into Hermes unless the owner separately asks VAN to
 * analyse it.** Everything here exists to make that true by construction rather than by
 * everyone remembering — `UploadTicket` carries a name, a size and a type, and has no
 * field a byte could travel in.
 *
 * The second is the TTL. §19 step 8: the ephemeral copy expires unless the owner
 * explicitly retains it. A file the owner uploaded to one page, still sitting on a shared
 * host an hour later, is a copy they did not agree to leave there.
 *
 * Pure. The `ACTION_OPEN_DOCUMENT` call and the bytes are the Activity's; the decisions
 * about what may be offered, what expires and what is refused are here.
 */

/** §19's flow, as states rather than as a sequence of calls nobody can test. */
enum class UploadState {
    /** The page asked. VAN has not shown the owner anything yet. */
    REQUESTED,

    /** The Android document picker is open. */
    CHOOSING,

    /** The owner picked something and the bytes are on their way to the host. */
    TRANSFERRING,

    /** On the host, resolved to a path, attached to the chooser. */
    ATTACHED,

    /** The TTL passed, or the owner cancelled, or the page went away. */
    EXPIRED,

    /** The owner declined, or VAN refused the file. */
    REFUSED,

    ;

    val terminal: Boolean get() = this == EXPIRED || this == REFUSED
}

enum class UploadRefusal {
    /** The page asked for a type the owner did not pick, so it would be rejected anyway. */
    TYPE_NOT_ACCEPTED,
    TOO_LARGE,
    /** A name that is not a name: separators, traversal, control characters. */
    NAME_UNSAFE,
    /** The chooser belongs to a session that is no longer the one on screen. */
    SESSION_STALE,
    OWNER_CANCELLED,
}

/**
 * What VAN knows about the file, and deliberately all it knows.
 *
 * No bytes, no path, no content hash of the plaintext. A ticket can be logged whole
 * without logging the file, which is what §19's prohibition needs: the rule holds because
 * there is nothing here to violate it with.
 */
data class UploadTicket(
    val uploadId: String,
    val sessionId: String,
    val targetId: String,
    val displayName: String,
    val byteSize: Long,
    val declaredMime: String,
    val createdAtMs: Long,
    val state: UploadState = UploadState.REQUESTED,
    /** §19 step 8 — the owner asked for this copy to stay. */
    val ownerRetained: Boolean = false,
) {
    fun expiresAtMs(ttlMs: Long = BrowserUploadPolicy.DEFAULT_TTL_MS): Long? =
        if (ownerRetained) null else createdAtMs + ttlMs
}

/** What the page said it would accept, as the chooser was asked for it. */
data class FileChooserRequest(
    val sessionId: String,
    val targetId: String,
    val acceptTypes: List<String>,
    val multiple: Boolean,
)

object BrowserUploadPolicy {

    /**
     * §19 step 8 — how long an ephemeral copy lives on the host without the owner saying
     * to keep it.
     *
     * Fifteen minutes: long enough for a form the owner is filling in slowly, short enough
     * that a file uploaded and forgotten is gone before they have left the room. Not a day,
     * and not five minutes: the first leaves a copy overnight and the second expires under
     * an owner who went to find the document.
     */
    const val DEFAULT_TTL_MS = 15 * 60 * 1000L

    /**
     * The largest file VAN will move through the control plane.
     *
     * A bound rather than a guess at what pages want: without one, a page requesting a
     * file chooser can ask the owner for a video and VAN will spend the phone's battery
     * and the owner's data moving it.
     */
    const val MAX_BYTES = 64L * 1024 * 1024

    /** A name that is not a name. The same rule the download side applies, from the other direction. */
    private val UNSAFE_NAME = Regex("(^\\.\\.?$)|(\\.\\.[/\\\\])|([/\\\\])|(^\\s*$)|([\\x00-\\x1f])")

    /**
     * Whether the file the owner picked can be offered to the page that asked.
     *
     * The accept-type check is done here rather than left to the page because a page that
     * rejects the file after the upload has already moved the bytes: the owner paid for
     * the transfer and the page says no.
     */
    fun admit(
        request: FileChooserRequest,
        displayName: String,
        byteSize: Long,
        declaredMime: String,
        liveSessionId: String,
    ): UploadRefusal? {
        if (request.sessionId != liveSessionId) return UploadRefusal.SESSION_STALE
        if (UNSAFE_NAME.containsMatchIn(displayName)) return UploadRefusal.NAME_UNSAFE
        if (byteSize <= 0 || byteSize > MAX_BYTES) return UploadRefusal.TOO_LARGE
        if (!accepts(request.acceptTypes, displayName, declaredMime)) {
            return UploadRefusal.TYPE_NOT_ACCEPTED
        }
        return null
    }

    /**
     * Whether an `accept` list admits this file.
     *
     * An empty list means the page accepts anything, which is what an absent `accept`
     * attribute means in HTML. Treating empty as "nothing" would break every plain file
     * input on the web.
     */
    fun accepts(acceptTypes: List<String>, displayName: String, declaredMime: String): Boolean {
        if (acceptTypes.isEmpty()) return true
        val mime = declaredMime.substringBefore(';').trim().lowercase()
        val suffix = displayName.substringAfterLast('.', "").lowercase()
        return acceptTypes.any { raw ->
            val accept = raw.trim().lowercase()
            when {
                accept == "*/*" -> true
                accept.startsWith(".") -> suffix.isNotEmpty() && accept == ".$suffix"
                accept.endsWith("/*") -> mime.startsWith(accept.removeSuffix("*"))
                else -> accept == mime
            }
        }
    }

    /** §19 step 8 — has this copy outlived the owner's intent? */
    fun expired(ticket: UploadTicket, nowMs: Long, ttlMs: Long = DEFAULT_TTL_MS): Boolean {
        if (ticket.ownerRetained) return false
        if (ticket.state.terminal) return false
        return nowMs >= ticket.createdAtMs + ttlMs
    }

    /**
     * §19's prohibition, as a predicate rather than as a sentence in a review.
     *
     * Analysis is something the owner asks for separately. Uploading a file to a web page
     * is not that request, and a VAN that inferred it would read the owner's documents
     * because they attached one to a form.
     */
    fun mayAnalyse(ticket: UploadTicket, ownerAskedToAnalyse: Boolean): Boolean =
        ownerAskedToAnalyse && ticket.state == UploadState.ATTACHED

    /**
     * What goes in a log line about this upload.
     *
     * Returns the ticket's non-content fields, so the call site cannot accidentally
     * interpolate something that is not here. There is nothing here that is not already
     * metadata — which is the point of `UploadTicket` having no content field at all.
     */
    fun loggableFields(ticket: UploadTicket): Map<String, String> = mapOf(
        "upload_id" to ticket.uploadId,
        "session_id" to ticket.sessionId,
        "target_id" to ticket.targetId,
        "byte_size" to ticket.byteSize.toString(),
        "declared_mime" to ticket.declaredMime,
        "state" to ticket.state.name,
        // Deliberately not the display name: a filename is content. "P45 2019 — Jane
        // Okonkwo.pdf" in a log says who the owner is and what they were doing.
        "name_length" to ticket.displayName.length.toString(),
    )
}
