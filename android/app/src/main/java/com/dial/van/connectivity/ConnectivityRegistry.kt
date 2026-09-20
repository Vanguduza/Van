package com.dial.van.connectivity

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.dial.van.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject

/**
 * Rev 1.5 §0D.2 / ADR-RB-024, ADR-RB-027 — where VAN connects, and why nobody types it in.
 *
 * The owner build has no settings field for a server address. §0D.2's reasoning is that a
 * field like that is a phishing surface with the owner's whole assistant behind it: anyone
 * who can get a URL in front of them owns every command from then on. So endpoints arrive
 * as a signed manifest, are verified against keys compiled into the build, and are stored
 * only after they verify.
 *
 * This class is the storage and the fetch. The decision — whether a manifest may be applied
 * — is [ConnectivityManifestVerifier], which is pure and executed in the harness, because
 * every case worth testing is a manifest that almost works.
 *
 * Two properties are worth stating because they are easy to lose:
 *
 *  * **Nothing is stored before it verifies.** A fetch that returns a bad manifest leaves
 *    the previous one in place. The failure mode of the other order is a device that has
 *    cached an endpoint it will not accept and cannot replace.
 *  * **The version only moves forward.** A manifest older than the stored one is refused
 *    even with a perfect signature, because a correctly-signed old manifest is exactly what
 *    an attacker who has recorded one would replay.
 */
class ConnectivityRegistry(context: Context) {

    private val prefs = EncryptedSharedPreferences.create(
        context.applicationContext,
        "van_connectivity",
        MasterKey.Builder(context.applicationContext)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )

    /**
     * The keys this build will accept a manifest from, by `kid`.
     *
     * Compiled in rather than fetched, which is the whole point: a trust anchor that can be
     * delivered over the network is not a trust anchor. An empty map means this build was
     * not given one, and then no manifest is ever applied — the device keeps whatever it
     * was provisioned with and says so, rather than accepting the first one it is handed.
     */
    private val trustedKeys: Map<String, String> by lazy { parseTrustedKeys() }

    val configured: Boolean get() = trustedKeys.isNotEmpty()

    val knownVersion: Int get() = prefs.getInt(KEY_VERSION, 0)

    fun current(): ConnectivityManifest? {
        val raw = prefs.getString(KEY_MANIFEST, null) ?: return null
        // `knownVersion - 1`, because the stored manifest *is* `knownVersion` and the
        // verifier refuses anything at or below what it is given. Re-verifying on every
        // read rather than trusting the store: bytes are not trusted for being ours.
        return when (val verdict = verify(raw, prefs.getString(KEY_SIGNATURE, "") ?: "",
                                          prefs.getString(KEY_KID, "") ?: "", knownVersion - 1)) {
            is ManifestVerdict.Accepted -> verdict.manifest
            // A stored manifest that no longer verifies is not usable, and pretending
            // otherwise would mean trusting bytes because they are ours. This happens for
            // real when a build rotates its compiled-in keys.
            is ManifestVerdict.Refused -> null
        }
    }

    /**
     * Ask the gateway for a newer manifest and apply it if there is one.
     *
     * @return the verdict, so the caller can tell "already current" from "refused" — the
     *   two look identical from the outside and mean opposite things.
     */
    suspend fun refresh(fetch: suspend (Int) -> JSONObject): ManifestVerdict? =
        withContext(Dispatchers.IO) {
            if (!configured) return@withContext null
            val response = fetch(knownVersion)
            if (response.optBoolean("current", false)) return@withContext null
            val manifestJson = response.optJSONObject("manifest")?.toString()
                ?: return@withContext ManifestVerdict.Refused("connectivity_manifest_absent")
            val verdict = verify(
                manifestJson,
                response.optString("signature", ""),
                response.optString("kid", ""),
                knownVersion,
            )
            if (verdict is ManifestVerdict.Accepted) {
                prefs.edit()
                    .putString(KEY_MANIFEST, manifestJson)
                    .putString(KEY_SIGNATURE, response.optString("signature", ""))
                    .putString(KEY_KID, response.optString("kid", ""))
                    .putInt(KEY_VERSION, verdict.manifest.manifestVersion)
                    .apply()
            }
            verdict
        }

    private fun verify(
        manifestJson: String,
        signatureHex: String,
        kid: String,
        against: Int,
    ): ManifestVerdict = ConnectivityManifestVerifier.verify(
        manifestJson = manifestJson,
        signatureHex = signatureHex,
        kid = kid,
        trustedKeys = trustedKeys,
        knownVersion = against,
    )

    /** One parser, shared with the provisioning intake. See [ConnectivityTrustedKeys]. */
    private fun parseTrustedKeys(): Map<String, String> =
        ConnectivityTrustedKeys.parse(BuildConfig.VAN_CONNECTIVITY_TRUSTED_KEYS)

    private companion object {
        const val KEY_MANIFEST = "manifest_json"
        const val KEY_SIGNATURE = "manifest_signature"
        const val KEY_KID = "manifest_kid"
        const val KEY_VERSION = "manifest_version"
    }
}
