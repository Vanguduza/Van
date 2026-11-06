package com.dial.van.overlay

import android.app.KeyguardManager
import android.content.Context
import android.os.PowerManager

/** Own-window privacy only; no overlay exemptions or keyguard bypass. */
internal object OverlayPrivacyVisibility {
    fun interactiveAndUnlocked(context: Context): Boolean = runCatching {
        val screen = context.getSystemService(PowerManager::class.java)?.isInteractive == true
        val locked = context.getSystemService(KeyguardManager::class.java)?.isKeyguardLocked != false
        screen && !locked
    }.getOrDefault(false)
}
