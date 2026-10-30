package com.dial.van.control

import java.util.UUID

/** Local permission to finish one current voice turn, not authority to execute work. */
data class SpokenCommandResult(
    val commandId: String?,
    val resultRef: String?,
    val text: String,
    val contextId: String,
    val askedAtEpochMs: Long,
    val playbackRequestId: String = UUID.randomUUID().toString(),
)
