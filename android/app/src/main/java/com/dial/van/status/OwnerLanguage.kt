package com.dial.van.status

import org.json.JSONObject

/**
 * VAN's internal vocabulary, translated into the owner's.
 *
 * P2-UX-001. The Command Centre showed the owner `A4`, `BIOMETRIC_STRONG`, `HMAC`,
 * `reason_code`, raw scope JSON, `truth_sha` and raw payload strings. Those are correct
 * names for what they are and none of them is a thing a person reads. An owner looking at
 * "This action is A4" learns nothing except that VAN was not written for them.
 *
 * The rule this file follows: an internal name is either translated or not shown. There is
 * no third option where it is shown with a tooltip, because the tooltip is also not read.
 * Where a technical value genuinely matters — a truth digest the owner may need to quote to
 * somebody — it is shown as a short, labelled reference rather than as a raw field name and
 * a 64-character hash.
 *
 * Pure Kotlin, so what the owner reads is executed in `android/verification`.
 */
object OwnerLanguage {

    /**
     * Action classes, in terms of what they cost the owner if wrong.
     *
     * Not "A3" with an explanation. The owner never needs the letter; they need to know
     * whether VAN is about to read something or change something.
     */
    fun actionClass(actionClass: String?): String = when (actionClass?.trim()?.uppercase()) {
        "A1" -> "Reads something"
        "A2" -> "Drafts something for you"
        "A3" -> "Changes something outside VAN"
        "A4" -> "Changes something you cannot easily undo"
        "A5" -> "Not something VAN will do"
        null, "" -> "Unknown"
        else -> "Unknown"
    }

    /**
     * A command's status, as a short label a person reads.
     *
     * The Command Centre printed `status.name` under every message, so the owner read
     * `PARTIALLY_SUCCEEDED` and `COULD_NOT_VERIFY` off their own phone. Exhaustive on
     * purpose: adding a status makes this stop compiling rather than silently fall through
     * to a neighbour, which is the defect P0-EXEC-003 found one layer down.
     */
    fun commandStatus(status: VanCommandStatus): String = when (status) {
        VanCommandStatus.LOCAL_DRAFT -> "Not sent yet"
        VanCommandStatus.SUBMITTING -> "Sending"
        VanCommandStatus.APPROVAL_REQUIRED -> "Waiting for you"
        VanCommandStatus.ACCEPTED -> "VAN has it"
        VanCommandStatus.IN_FLIGHT -> "Working on it"
        VanCommandStatus.SUCCEEDED -> "Done"
        VanCommandStatus.PARTIALLY_SUCCEEDED -> "Partly done"
        VanCommandStatus.COULD_NOT_VERIFY -> "Done, but not confirmed"
        VanCommandStatus.FAILED -> "Did not work"
        VanCommandStatus.REFUSED -> "VAN would not do this"
        VanCommandStatus.QUEUED -> "Saved for when you're online"
        VanCommandStatus.CANCELLED -> "Stopped"
        VanCommandStatus.EXPIRED -> "Never came back"
        VanCommandStatus.UNKNOWN -> "VAN is not sure"
    }

    /** Whether this class needs the owner's approval, said as a sentence. */
    fun approvalSentence(actionClass: String?): String? =
        if (actionClass?.trim()?.uppercase() == "A4") {
            "VAN needs your fingerprint or face before doing this, because you cannot easily undo it."
        } else {
            null
        }

    /**
     * Authenticator names.
     *
     * `BIOMETRIC_STRONG` is Android's constant. The owner's word for it is their finger.
     */
    fun authenticator(name: String?): String = when (name?.trim()?.uppercase()) {
        "BIOMETRIC_STRONG" -> "your fingerprint or face"
        "BIOMETRIC_WEAK" -> "a screen unlock VAN does not consider strong enough"
        "DEVICE_CREDENTIAL" -> "your PIN or pattern"
        else -> "your device unlock"
    }

    /**
     * Credential names.
     *
     * The owner does not need to know that command signing uses an HMAC. They need to know
     * that this phone can prove it is theirs.
     */
    fun credential(name: String?): String = when (name?.trim()?.uppercase()) {
        "HMAC", "COMMAND_HMAC" -> "this phone's signing key"
        "INGRESS", "INGRESS_TOKEN" -> "the key that lets this phone reach your gateway"
        "DEVICE_ACCESS", "DEVICE_ACCESS_TOKEN" -> "this phone's access to your gateway"
        else -> "a credential"
    }

    /**
     * Refusal reason codes.
     *
     * A closed map, and an unknown code becomes de-snaked English rather than being shown
     * raw. A new reason appearing on screen should read as slightly awkward, never as
     * `browser_mutation_domain_not_admitted`.
     */
    val REASONS: Map<String, String> = mapOf(
        "scope_violation" to "It tried to go somewhere you had not allowed.",
        "action_class_violation" to "It tried to do more than you allowed.",
        "payment_refused" to "It reached a payment, and VAN does not pay for things.",
        "injection_refused" to "The page tried to give VAN instructions, so VAN stopped.",
        "goal_drift" to "It started doing something other than what you asked.",
        "budget_exhausted" to "It ran out of the steps you allowed it.",
        "no_progress" to "The page stopped changing, so VAN stopped.",
        "deadline_exceeded" to "It took longer than you allowed.",
        "device_or_grant_revoked" to "This phone is no longer allowed to do that.",
        "command_authority_expired" to "You asked for this a while ago, so VAN asked again rather than acting on it.",
        "typed_parameter_mismatch" to "What VAN was about to do did not match what you asked for.",
        "unsealed_parameter" to "Something tried to add a detail you never approved.",
        "unsealed_required_parameter" to "VAN could not tell which one you meant.",
        "stale_intent" to "That request was too old to act on.",
        "nonce_replay" to "VAN had already seen that exact request.",
    )

    fun reason(code: String?): String {
        val key = code?.trim()?.lowercase()?.substringBefore(':').orEmpty()
        if (key.isEmpty()) return "VAN did not say why."
        REASONS[key]?.let { return it }
        return key.replace('_', ' ').replaceFirstChar { it.uppercase() } + "."
    }

    /**
     * A digest the owner might have to quote, shortened and labelled.
     *
     * `truth_sha` beside 64 hex characters is a field name and a wall. "Project state a1b2c3d4"
     * is something a person can read out.
     */
    fun digestReference(label: String, digest: String?): String? {
        val trimmed = digest?.trim().orEmpty()
        if (trimmed.length < 8) return null
        return "$label ${trimmed.take(8)}"
    }

    /**
     * A browser or capability scope, as a sentence instead of JSON.
     *
     * The Command Centre rendered the scope object directly. An owner reading
     * `{"domains":["mail.google.com"],"action_class_ceiling":"A2"}` is reading a debugger.
     */
    fun scopeSentence(domains: List<String>, actionClass: String?): String {
        val where = when {
            domains.isEmpty() -> "nowhere in particular"
            domains.size == 1 -> domains.first()
            domains.size == 2 -> "${domains[0]} and ${domains[1]}"
            else -> "${domains[0]}, ${domains[1]} and ${domains.size - 2} more"
        }
        return "On $where. ${actionClass(actionClass)}."
    }

    /**
     * A scope object, as it actually arrives: a JSON string in a gateway field.
     *
     * The Command Centre rendered `current_scope_json` and `requested_scope_delta_json`
     * with `.take(300)`, so the owner was asked to approve a browser boundary extension by
     * reading 300 characters of truncated JSON. Whether they approve is the most
     * consequential decision on that screen.
     */
    fun scopeSentenceFromJson(json: String?): String {
        val text = json?.trim().orEmpty()
        if (text.isEmpty()) return "Nothing more than it already has."
        val parsed = runCatching { JSONObject(text) }.getOrNull()
            ?: return "Something VAN could not read back to you."
        val domains = parsed.optJSONArray("domains") ?: parsed.optJSONArray("allowed_domains")
        val list = buildList {
            for (i in 0 until (domains?.length() ?: 0)) {
                domains?.optString(i)?.takeIf { it.isNotBlank() }?.let(::add)
            }
        }
        val ceiling = parsed.optString("action_class_ceiling")
            .takeIf { it.isNotBlank() }
            ?: parsed.optString("action_class").takeIf { it.isNotBlank() }
        return scopeSentence(list, ceiling)
    }

    /**
     * Whether a string is safe to put in front of the owner at all.
     *
     * Used by the screens as a last guard: anything that looks like JSON, an all-caps
     * constant or a long hex string is an internal value that escaped, and showing a plain
     * "VAN did not explain this one" is better than showing it.
     */
    fun isInternalLooking(text: String?): Boolean {
        val value = text?.trim().orEmpty()
        if (value.isEmpty()) return false
        if (value.startsWith("{") || value.startsWith("[")) return true
        if (value.length >= 32 && value.all { it.isDigit() || it in 'a'..'f' || it in 'A'..'F' }) return true
        if (value.length in 3..40 && value.all { it.isUpperCase() || it == '_' || it.isDigit() }) return true
        return false
    }

    /** The safe rendering of a value that may be internal. */
    fun ownerSafe(text: String?, fallback: String = "VAN did not explain this one."): String =
        if (text.isNullOrBlank() || isInternalLooking(text)) fallback else text
}
