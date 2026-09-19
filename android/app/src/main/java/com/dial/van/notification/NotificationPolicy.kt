package com.dial.van.notification

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.util.concurrent.ConcurrentHashMap

enum class AppNotificationPolicy {
    NORMAL,
    PRIORITY,
    MUTE,
}

data class QuietHoursConfig(
    val enabled: Boolean = false,
    val startHour: Int = 22,
    val endHour: Int = 7,
)

class NotificationPolicyStore(context: Context) {
    private val masterKey = MasterKey.Builder(context)
        .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
        .build()

    private val prefs = EncryptedSharedPreferences.create(
        context,
        PREFS_NAME,
        masterKey,
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )

    private val recentHashes = ConcurrentHashMap<String, Long>()

    fun policyFor(packageName: String): AppNotificationPolicy {
        val raw = prefs.getString(keyPolicy(packageName), AppNotificationPolicy.NORMAL.name)
        return runCatching { AppNotificationPolicy.valueOf(raw!!) }.getOrDefault(AppNotificationPolicy.NORMAL)
    }

    fun setPolicy(packageName: String, policy: AppNotificationPolicy) {
        prefs.edit().putString(keyPolicy(packageName), policy.name).apply()
    }

    fun quietHours(): QuietHoursConfig = QuietHoursConfig(
        enabled = prefs.getBoolean(KEY_QUIET_ENABLED, false),
        startHour = prefs.getInt(KEY_QUIET_START, 22),
        endHour = prefs.getInt(KEY_QUIET_END, 7),
    )

    fun setQuietHours(config: QuietHoursConfig) {
        prefs.edit()
            .putBoolean(KEY_QUIET_ENABLED, config.enabled)
            .putInt(KEY_QUIET_START, config.startHour)
            .putInt(KEY_QUIET_END, config.endHour)
            .apply()
    }

    fun isQuietNow(hour: Int = java.util.Calendar.getInstance().get(java.util.Calendar.HOUR_OF_DAY)): Boolean {
        val q = quietHours()
        if (!q.enabled) return false
        return if (q.startHour <= q.endHour) {
            hour in q.startHour until q.endHour
        } else {
            hour >= q.startHour || hour < q.endHour
        }
    }

    /** Returns true when duplicate should be suppressed (same hash within window). */
    fun shouldSuppressDuplicate(contentHash: String, windowMs: Long = DUPLICATE_WINDOW_MS): Boolean {
        val now = System.currentTimeMillis()
        val last = recentHashes[contentHash]
        if (last != null && now - last < windowMs) return true
        recentHashes[contentHash] = now
        pruneOldDuplicates(now, windowMs)
        return false
    }

    private fun pruneOldDuplicates(now: Long, windowMs: Long) {
        recentHashes.entries.removeIf { now - it.value > windowMs * 2 }
    }

    /**
     * Every app the owner has already decided about.
     *
     * P2-AND-017 — the store could be written to and read per package, and could not say
     * what it held, so an owner control surface had nothing to list. Without this the
     * screen could only offer apps it happened to know about, which is the screen that
     * makes a setting look absent rather than unset.
     *
     * NORMAL is the default, so an entry recorded as NORMAL is still a decision the owner
     * made and is shown; only the never-touched are absent.
     */
    fun decidedPackages(): Map<String, AppNotificationPolicy> =
        prefs.all.keys
            .filter { it.startsWith(POLICY_PREFIX) }
            .associate { key ->
                val pkg = key.removePrefix(POLICY_PREFIX)
                pkg to policyFor(pkg)
            }

    private fun keyPolicy(pkg: String) = "$POLICY_PREFIX$pkg"

    companion object {
        private const val PREFS_NAME = "van_notification_policy"
        private const val POLICY_PREFIX = "policy_"
        private const val KEY_QUIET_ENABLED = "quiet_enabled"
        private const val KEY_QUIET_START = "quiet_start"
        private const val KEY_QUIET_END = "quiet_end"
        private const val DUPLICATE_WINDOW_MS = 60_000L
    }
}

object SecretRedactor {
    private val otpPattern = Regex("""\b(\d{4,8})\b(?=.*(?:code|otp|pin|verify|verification))""", RegexOption.IGNORE_CASE)
    private val otpStandalone = Regex("""\b\d{6}\b""")
    private val apiKeyPattern = Regex("""(?i)(api[_-]?key|token|secret|password|bearer)\s*[:=]\s*\S+""")
    private val privateKeyPattern = Regex("""-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]+?-----END [A-Z ]+ PRIVATE KEY-----""")

    fun redact(text: String): String {
        var out = text
        out = otpPattern.replace(out, "[REDACTED_OTP]")
        out = apiKeyPattern.replace(out, "[REDACTED_SECRET]")
        out = privateKeyPattern.replace(out, "[REDACTED_KEY]")
        // Conservative: redact 6-digit codes in short messages likely OTP
        if (out.length < 120 && otpStandalone.containsMatchIn(out)) {
            out = otpStandalone.replace(out, "[REDACTED_OTP]")
        }
        return out
    }
}
