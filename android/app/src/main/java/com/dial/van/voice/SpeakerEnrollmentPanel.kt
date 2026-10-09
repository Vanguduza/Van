package com.dial.van.voice

import android.Manifest
import android.content.Context
import android.content.ContextWrapper
import android.content.pm.PackageManager
import android.util.Base64
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.dial.van.VanApplication
import com.dial.van.command.owner.ownerTime
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

/** Local profile consent is a separate one-use biometric ceremony, never a VAN action grant. */
@Composable
fun SpeakerEnrollmentPanel(app: VanApplication, ownerActivity: FragmentActivity? = null) {
    val manager = app.speakerEnrollment
    val state by manager.state.collectAsState()
    val context = LocalContext.current
    val activity = ownerActivity ?: context.ownerActivity()
    val lifecycleOwner = LocalLifecycleOwner.current
    val scope = rememberCoroutineScope()
    val active = remember(manager, activity) { AtomicBoolean(true) }
    val prompt = remember(manager, activity) { AtomicReference<BiometricPrompt?>(null) }
    var confirming by remember(manager) { mutableStateOf(false) }
    var removalReview by remember(manager) { mutableStateOf(false) }
    var message by remember(manager) { mutableStateOf<String?>(null) }
    fun hasMicrophone() = ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
    var microphoneGranted by remember { mutableStateOf(hasMicrophone()) }
    val microphonePermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        microphoneGranted = hasMicrophone()
        message = if (microphoneGranted) "Microphone permission is available. Enrollment still requires dedicated biometric consent."
            else "Microphone permission is required to capture an owner profile. No capture was started."
    }

    fun cancelConfirmation() {
        prompt.getAndSet(null)?.cancelAuthentication()
        manager.cancelCapture()
        confirming = false
    }

    DisposableEffect(manager, activity, lifecycleOwner) {
        active.set(true)
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                active.set(true)
                microphoneGranted = hasMicrophone()
            }
            if (event == Lifecycle.Event.ON_STOP) {
                active.set(false)
                cancelConfirmation()
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            active.set(false)
            lifecycleOwner.lifecycle.removeObserver(observer)
            prompt.getAndSet(null)?.cancelAuthentication()
            manager.cancelCapture()
        }
    }
    LaunchedEffect(manager) {
        try { manager.refresh() }
        catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { message = "Speaker readiness could not be read. No enrollment was started." }
    }

    fun beginConsent(operation: SpeakerEnrollmentOperation) {
        val host = activity ?: return
        if (confirming) return
        confirming = true; message = null
        scope.launch {
            try {
                check(BiometricManager.from(host).canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_STRONG) == BiometricManager.BIOMETRIC_SUCCESS)
                val consent = manager.prepareConsent(operation)
                if (!active.get()) { manager.cancelCapture(); confirming = false; return@launch }
                check(consent.challenge.isNotBlank() && System.currentTimeMillis() < consent.expiresAtMs)
                val nativePrompt = BiometricPrompt(host, ContextCompat.getMainExecutor(host), object : BiometricPrompt.AuthenticationCallback() {
                    override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                        prompt.set(null)
                        if (!active.get()) { manager.cancelCapture(); return }
                        try {
                            check(System.currentTimeMillis() < consent.expiresAtMs)
                            val signature = result.cryptoObject?.signature ?: error("speaker_crypto_signature_absent")
                            check(signature === consent.signature)
                            signature.update(consent.challenge.toByteArray(Charsets.UTF_8))
                            val proof = Base64.encodeToString(signature.sign(), Base64.NO_WRAP)
                            scope.launch {
                                try { manager.completeConsent(consent.id, proof) }
                                catch (cancelled: CancellationException) { manager.cancelCapture(); throw cancelled }
                                catch (_: Exception) { message = "Speaker confirmation could not be completed. Read profile readiness before another decision." }
                                finally { confirming = false }
                            }
                        } catch (_: Exception) {
                            manager.cancelCapture(); confirming = false
                            message = "The exact biometric signature was unavailable or expired. No new capture was authorized."
                        }
                    }
                    override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                        prompt.set(null); manager.cancelCapture()
                        if (active.get()) {
                            confirming = false
                            message = "Biometric confirmation was cancelled or unavailable. No local operation was authorized."
                        }
                    }
                    override fun onAuthenticationFailed() {
                        if (active.get()) message = "Biometrics did not match. The native prompt remains open; no operation is authorized."
                    }
                })
                prompt.set(nativePrompt)
                nativePrompt.authenticate(BiometricPrompt.PromptInfo.Builder()
                    .setTitle(if (operation == SpeakerEnrollmentOperation.REMOVE) "Erase VAN speaker profile" else "Enroll VAN owner voice")
                    .setSubtitle(if (operation == SpeakerEnrollmentOperation.REMOVE) "Confirm removal of this exact local profile" else "Confirm three local microphone clips on this paired device")
                    .setAllowedAuthenticators(BiometricManager.Authenticators.BIOMETRIC_STRONG)
                    .setNegativeButtonText("Cancel").build(), BiometricPrompt.CryptoObject(consent.signature))
            } catch (cancelled: CancellationException) { manager.cancelCapture(); confirming = false; throw cancelled }
            catch (_: Exception) {
                manager.cancelCapture(); confirming = false
                message = "Dedicated speaker consent is unavailable. Read the current owner binding, model and profile readiness before trying again."
            }
        }
    }

    val busy = confirming || state.phase in setOf(SpeakerEnrollmentPhase.PREPARING, SpeakerEnrollmentPhase.AWAITING_CONSENT, SpeakerEnrollmentPhase.CAPTURING)
    Column(modifier = Modifier.testTag("speaker-enrollment-panel"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Owner speaker profile")
        Text("Status: ${state.phase.name.lowercase().replace('_', ' ')}")
        Text(if (state.modelReady) "Generic speaker model: ready" else "Generic speaker model: unavailable")
        Text(if (state.profilePresent) "Encrypted local owner profile: retained" else "Encrypted local owner profile: absent")
        state.profileCreatedAtMs?.let { Text("Profile captured ${ownerTime(it)}") }
        Text(state.message)
        Text("Speaker similarity supplies evidence. Paired device identity and action biometrics still govern owner authority. Raw clips are kept only in memory.")
        message?.let { Text(it) }
        if (activity == null) Text("A native owner activity is required for biometric consent.")
        if (state.phase == SpeakerEnrollmentPhase.CAPTURING) {
            Text("Clip ${state.clipIndex} of ${state.clipCount}. Say the displayed phrase while this screen stays open.")
            LinearProgressIndicator(progress = state.progress.coerceIn(0f, 1f), modifier = Modifier.testTag("speaker-capture-progress"))
        }
        if (!microphoneGranted) OutlinedButton(enabled = !busy, modifier = Modifier.testTag("speaker-microphone-permission"),
            onClick = { microphonePermission.launch(Manifest.permission.RECORD_AUDIO) }) { Text("Allow microphone for enrollment") }
        Button(enabled = !busy && activity != null && microphoneGranted && state.modelReady,
            modifier = Modifier.testTag("speaker-enroll"), onClick = { beginConsent(SpeakerEnrollmentOperation.ENROLL) }) {
            Text(if (state.profilePresent) "Replace owner profile with fresh capture" else "Enroll owner voice with biometrics")
        }
        if (confirming || state.phase in setOf(SpeakerEnrollmentPhase.AWAITING_CONSENT, SpeakerEnrollmentPhase.CAPTURING)) {
            OutlinedButton(modifier = Modifier.testTag("speaker-cancel-capture"), onClick = {
                cancelConfirmation(); message = "Speaker capture and its pending consent were cancelled. Read profile readiness for the retained profile."
            }) { Text("Cancel speaker capture") }
        }
        OutlinedButton(enabled = !busy, modifier = Modifier.testTag("speaker-readiness"), onClick = {
            confirming = true; message = null
            scope.launch {
                try { manager.refresh() }
                catch (cancelled: CancellationException) { throw cancelled }
                catch (_: Exception) { message = "Speaker readiness could not be read." }
                finally { confirming = false }
            }
        }) { Text("Read profile readiness") }
        OutlinedButton(enabled = !busy && activity != null && state.profilePresent, modifier = Modifier.testTag("speaker-erase"),
            onClick = { removalReview = true }) { Text("Erase local speaker profile") }
    }
    if (removalReview) AlertDialog(onDismissRequest = { removalReview = false }, title = { Text("Erase local speaker profile") },
        text = { Text("Remove the encrypted profile and stop using it for speaker evidence. This requires a separate biometric signature; microphone and model readiness are not required.") },
        confirmButton = { TextButton(enabled = !busy, onClick = { removalReview = false; beginConsent(SpeakerEnrollmentOperation.REMOVE) }) { Text("Confirm erasure with biometrics") } },
        dismissButton = { TextButton(onClick = { removalReview = false }) { Text("Keep profile") } })
}

private fun Context.ownerActivity(): FragmentActivity? {
    var current: Context = this
    repeat(16) {
        if (current is FragmentActivity) return current as FragmentActivity
        val wrapper = current as? ContextWrapper ?: return null
        if (wrapper.baseContext === current) return null
        current = wrapper.baseContext
    }
    return null
}
