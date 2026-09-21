package com.dial.van.browser

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import com.dial.van.VanApplication

/**
 * Rev 1.5 §17.5 and ADR-RB-023 — the two ways into VAN Browser from outside it.
 *
 * Both are the same shape on purpose: a tiny Activity with no UI that decides, in pure
 * code it delegates to, what the request is allowed to become, and then either starts
 * [BrowserActivity] or says why not. Neither holds a session, neither can navigate, and
 * neither carries authority.
 *
 * They are separate from [BrowserActivity] because they are a different trust position.
 * An exported activity is one any app on the phone can start with any extras it likes;
 * the activity that already holds the owner's browser session must not be that activity.
 */

/**
 * §17.5 — an http/https VIEW intent from another app.
 *
 * Rev 1.5 as issued sends this through a "§9.14" the document does not contain, so the
 * rule is stated in [BrowserExternalLink]: untrusted navigation input, not an owner
 * command. It opens in the public profile, and the owner sees it happen.
 */
class BrowserExternalLinkActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // `intent.dataString`, not an extra: an extra is whatever the caller put there,
        // and the VIEW contract is about the data URI.
        when (val outcome = BrowserExternalLink.accept(intent?.dataString)) {
            is BrowserExternalLink.Outcome.OpenUntrusted -> {
                startActivity(
                    Intent(this, BrowserActivity::class.java).apply {
                        putExtra(BrowserActivity.EXTRA_PROFILE_ALIAS, outcome.profileAlias)
                        putExtra(BrowserActivity.EXTRA_EXTERNAL_URL, outcome.url)
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    },
                )
            }
            is BrowserExternalLink.Outcome.Refused -> {
                // Said out loud rather than dropped. A link that silently does nothing
                // reads as VAN being broken, and the owner tries it again.
                Toast.makeText(this, refusalText(outcome.reason), Toast.LENGTH_SHORT).show()
            }
        }
        finish()
    }

    private fun refusalText(reason: BrowserExternalLink.Refusal): String = when (reason) {
        BrowserExternalLink.Refusal.SCHEME_NOT_ACCEPTED ->
            "VAN opens web links only. That one is for another app."
        BrowserExternalLink.Refusal.NESTED_SCHEME ->
            "That link redirects somewhere VAN will not follow."
        BrowserExternalLink.Refusal.MALFORMED ->
            "That link is not a web address."
    }
}

/**
 * ADR-RB-023 — a pinned home-screen shortcut.
 *
 * The shortcut contains a `shortcut_id` and presentation, and this resolves it through
 * VAN's own registry. §5.8: missing, revoked, or a device that is not bound, and it does
 * not navigate.
 */
class BrowserShortcutActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val app = application as VanApplication
        val shortcutId = intent?.getStringExtra(EXTRA_SHORTCUT_ID)

        val resolution = shortcutId?.let {
            app.browserShortcuts.resolve(
                shortcutId = it,
                deviceBound = app.deviceIsBound(),
                availableProfiles = app.availableBrowserProfiles(),
            )
        } ?: ShortcutResolution.Refused(ShortcutRefusal.UNKNOWN_SHORTCUT)

        when (resolution) {
            is ShortcutResolution.Open -> {
                app.browserShortcuts.markOpened(
                    resolution.record.shortcutId, System.currentTimeMillis(),
                )
                startActivity(
                    Intent(this, BrowserActivity::class.java).apply {
                        putExtra(
                            BrowserActivity.EXTRA_PROFILE_ALIAS, resolution.record.profileAlias,
                        )
                        putExtra(
                            BrowserActivity.EXTRA_EXTERNAL_URL, resolution.record.canonicalUrl,
                        )
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    },
                )
            }
            is ShortcutResolution.Refused -> {
                Toast.makeText(this, refusalText(resolution.reason), Toast.LENGTH_LONG).show()
            }
        }
        finish()
    }

    private fun refusalText(reason: ShortcutRefusal): String = when (reason) {
        // Each is a different thing to tell the owner, and the second is the one worth
        // reading twice: the shortcut is on a home screen someone else may be holding.
        ShortcutRefusal.UNKNOWN_SHORTCUT -> "VAN does not have that saved page any more."
        ShortcutRefusal.REVOKED -> "You removed that shortcut. It no longer opens."
        ShortcutRefusal.DEVICE_NOT_BOUND -> "This phone is not set up as your VAN device."
        ShortcutRefusal.PROFILE_UNAVAILABLE -> "The browser profile for that page is gone."
    }

    companion object {
        /** ADR-RB-023 — the only extra a shortcut carries. */
        const val EXTRA_SHORTCUT_ID = "com.dial.van.browser.SHORTCUT_ID"
    }
}
