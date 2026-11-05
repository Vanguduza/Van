package com.dial.van.overlay

/** Main-thread local draft lease. This is NOT gateway acceptance or replay authority. */
class OverlaySubmissionGuard {
    enum class Result { EMPTY, BUSY, STALE, DUPLICATE, LOCALLY_RECORDED, NOT_RECORDED }
    private var value = ""
    private var revision = 0L
    private var consumed = -1L

    fun observe(draft: String): Long {
        if (draft != value) { value = draft; revision++; consumed = -1L }
        return revision
    }

    fun submit(draft: String, lease: Long, submitting: Boolean, record: (String) -> Boolean): Result {
        if (lease != revision || draft != value) return Result.STALE
        if (draft.isBlank()) return Result.EMPTY
        if (submitting) return Result.BUSY
        if (consumed == lease) return Result.DUPLICATE
        consumed = lease
        return try {
            if (record(draft.trim())) Result.LOCALLY_RECORDED
            else { if (consumed == lease) consumed = -1L; Result.NOT_RECORDED }
        } catch (failure: Exception) {
            if (consumed == lease) consumed = -1L
            throw failure
        }
    }
}
