"""Original-source integration checks for privacy/recovery/preferences and event boundaries.

These are code wiring assertions, not physical microphone, Keystore or frame evidence.
"""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2]
OVER=ROOT/'android/app/src/main/java/com/dial/van/overlay'
VIS=ROOT/'android/app/src/main/java/com/dial/van/visual'

class FloatingCodeHardening(unittest.TestCase):
    def test_snapshot_storage_is_encrypted_without_plaintext_fallback(self):
        s=(OVER/'OverlayStateStore.kt').read_text()
        self.assertIn('EncryptedSharedPreferences.create',s)
        self.assertIn('AES256_GCM',s)
        self.assertNotIn('getSharedPreferences(',s)
        self.assertIn('localOwnership.write(lease)',s)
    def test_disk_commit_uses_serial_background_writer_not_composition(self):
        s=(OVER/'OverlaySessionRuntime.kt').read_text()
        self.assertIn('newSingleThreadExecutor',s)
        self.assertIn('OverlaySessionWriter',s)
        self.assertIn('store.writeLocalSession(storeLease, encoded)',s)
        self.assertIn('executor.shutdown()',s)
        self.assertNotIn('shutdownNow',s)
        self.assertNotIn('Thread.sleep',s)
    def test_recovered_draft_is_not_immediately_put_into_composer_or_submitted(self):
        s=(OVER/'OverlaySessionRuntime.kt').read_text()
        self.assertIn('session = result.session.copy(draft = "")',s)
        self.assertIn('fun resumeDraft()',s)
        self.assertIn('fun discardDraft()',s)
        for method in ['submitText','beginOwnerTurn','executeCommand']:self.assertNotIn(method,s)
        p=(OVER/'OverlayPersonalControls.kt').read_text()
        self.assertIn('Resume draft',p);self.assertIn('Check conversation/task status',p)
    def test_owner_changes_invalidate_local_text_and_release_own_capture(self):
        s=(OVER/'OverlaySessionRuntime.kt').read_text()
        self.assertIn('removeOwnerListener?.invoke()',s)
        self.assertIn('if (!closed && !scopeCurrent()) invalidateOwner()',s)
        self.assertIn('ownerInvalidated()',s)
        self.assertIn('session = OverlayLocalSession("")',s)
        client=(ROOT/'android/app/src/main/java/com/dial/van/gateway/VanGatewayClient.kt').read_text()
        self.assertIn('observeLocalOwnerIdentity',client)
        self.assertIn('KEY_BASE, KEY_DEVICE, KEY_SECRET',client)
    def test_lock_screen_never_displays_recovered_workboard(self):
        s=(OVER/'FloatingOverlayService.kt').read_text()
        self.assertIn('interactiveAndUnlocked(this)',s)
        self.assertIn('android.view.View.GONE',s)
        self.assertIn('surfaceController.pauseOwnerCapture()',s)
        self.assertIn('OverlayRestartPresentation.safe(saved.presentation)',s)
    def test_service_cancels_only_the_uuid_it_started(self):
        s=(OVER/'OverlaySurfaceController.kt').read_text()
        self.assertIn('ownedVoiceTurn = app.voiceSession.beginOwnerTurn()',s)
        self.assertIn('voiceSession?.cancelOwnerTurnIf(turn)',s)
        voice=(ROOT/'android/app/src/main/java/com/dial/van/voice/VoiceInterfaces.kt').read_text()
        self.assertIn('turnLifecycle.cancelIf(expectedTurnId) ?: return@post',voice)
    def test_owner_preferences_do_not_override_system_motion_or_critical_semantics(self):
        self.assertIn('reducedMotion || LocalVanPresentationPreferences.current.reducedMotion',(VIS/'VanCanvasFallback.kt').read_text())
        self.assertIn('VanPersonalPresentation.project',(OVER/'LiveOverlayEmbodiment.kt').read_text())
        self.assertIn('state.resolvedSemanticState in CRITICAL',(VIS/'VanPresentationPreferences.kt').read_text())
        self.assertIn('state.resolvedSemanticState !in CRITICAL',(VIS/'VanPresentationPreferences.kt').read_text())
    def test_settings_are_actual_existing_workboard_controls_not_new_authority(self):
        s=(OVER/'OverlayPersonalControls.kt').read_text()
        for feature in ['Reduce motion','Resting visibility','Double tap','Keep an encrypted local draft','Discard local draft','Retry local save']:self.assertIn(feature,s)
        self.assertIn('contentDescription = label',s)
        self.assertIn('VanWorkboardMode.SETTINGS',(OVER/'VanOverlayWorkboards.kt').read_text())
        self.assertIn('CompositionLocalProvider(LocalVanPresentationPreferences',(OVER/'OverlaySurfaceController.kt').read_text())
    def test_context_is_from_own_resumed_navigation_not_external_screen_inspection(self):
        s=(VIS/'VanNativeScreenContext.kt').read_text()
        self.assertIn('Lifecycle.State.RESUMED',s)
        self.assertIn('lifecycle.removeObserver(observer)',s)
        self.assertIn('ObserveVanOwnedScreen(currentRoute)',(ROOT/'android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt').read_text())
        self.assertNotIn('AccessibilityNodeInfo',s)
    def test_contextual_decision_does_not_invent_a_compare_analysis_button(self):
        s=(ROOT/'android/app/src/main/java/com/dial/van/command/attention/OwnerDecisionCard.kt').read_text()
        self.assertIn('VanContextEventPolicy.decision',s)
        self.assertNotIn('Compare these choices',s)
        self.assertIn('value.expiresAtUnix',s)
    def test_native_asset_reads_are_bounded_before_decode(self):
        s=(VIS/'VanRiveAvatar.kt').read_text()
        self.assertIn('VanAssetReadLimits.read(it, VanAssetReadLimits.RIVE_BYTES)',s)
        self.assertIn('VanAssetReadLimits.read(it, VanAssetReadLimits.CONTEXT_BYTES)',s)
        self.assertNotIn('it.readBytes()',s)
    def test_still_pose_uses_render_thread_bounded_steps_and_no_handler_loop(self):
        s=(VIS/'VanBoundedRiveView.kt').read_text()
        self.assertIn('override fun advance(elapsed: Float)',s)
        self.assertIn('VanRiveUpdateGate.STATIC_SETTLE_STEPS',s)
        self.assertIn('completed == revision.get()',s)
        self.assertNotIn('postDelayed',s)
        self.assertIn('if (!visible) pause()',s)
        view=(VIS/'VanRiveAvatar.kt').read_text()
        self.assertIn('motionBinding.updates.next',view)
        self.assertNotIn('controller.advance(',view)
    def test_still_mode_visibility_is_not_erased_by_parent_motion_gate(self):
        s=(VIS/'VanCanvasFallback.kt').read_text()
        beginning=s[s.index('VanRenderer.RIVE -> VanRiveAvatar('):s.index('VanRenderer.CANDIDATE_B ->')]
        self.assertIn('animate = animate,',beginning)
        self.assertNotIn('animate = motionEnabled,',beginning)
        owner=s[s.index('        VanAvatar('):s.index('// Faint FILLED wisps')]
        self.assertIn('animate = animate,',owner)
        self.assertIn('if (total > VanAssetReadLimits.RIVE_BYTES) break',s)

    def test_drag_response_is_event_bound_and_disabled_for_precision_pointing(self):
        s=(OVER/'OverlayWindowInteraction.kt').read_text()
        self.assertIn('OverlayVisualCueBridge.dragSample',s)
        self.assertGreaterEqual(s.count('OverlayVisualCueBridge.restAfterInteraction()'),3)
        source=(VIS/'VanLiveInteractionResponse.kt').read_text()
        self.assertIn('VanInteractionResponsePolicy.compatible',source)
        self.assertNotIn('rememberInfiniteTransition',source)
    def test_guidance_mark_is_same_owned_lease_and_withdraws_on_replacement(self):
        s=(VIS/'VanGuidanceBindings.kt').read_text()
        self.assertIn('highlightedTarget == (id to lease)',s)
        self.assertIn('VAN is pointing to this control',s)
        self.assertIn('drawRoundRect',s)
        self.assertIn('VanLivePointing.actionChanged(actionGeneration)',(VIS/'VanLiveVisualState.kt').read_text())

if __name__=='__main__':unittest.main(verbosity=2)
