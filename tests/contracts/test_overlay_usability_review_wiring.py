"""Independent source wiring checks. Not actual Android accessibility/device execution."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
OVERLAY=ROOT/'android/app/src/main/java/com/dial/van/overlay'

class OverlayUsabilityReviewWiring(unittest.TestCase):
    def test_draft_edit_invalidates_old_lease_before_parent_callback(self):
        source=(OVERLAY/'VanOverlayPanels.kt').read_text()
        self.assertIn('onValueChange = { draftGate.observe(it); sendError = null; onDraft(it) }',source)
    def test_locally_recorded_draft_invalidates_replayed_callback_before_clear(self):
        source=(OVERLAY/'VanOverlayPanels.kt').read_text()
        self.assertIn('Result.LOCALLY_RECORDED) { draftGate.observe(""); sendError = null; onDraft("") }',source)
    def test_selected_trade_view_owns_its_loading_state_before_effect_runs(self):
        source=(OVERLAY/'VanOverlayPanels.kt').read_text()
        self.assertIn('remember(view, refresh) { mutableStateOf(TradeBookState.Loading) }',source)
        self.assertIn('if (failure is kotlinx.coroutines.CancellationException) throw failure',source)
    def test_transient_lip_samples_do_not_directly_subscribe_the_whole_workboard(self):
        source=(OVERLAY/'VanOverlaySurface.kt').read_text()
        self.assertIn('derivedStateOf',source)
        self.assertIn('OverlayPresentationFrame.chrome',source)
        self.assertIn('VanLiveVisualState.frame',(OVERLAY/'LiveOverlayEmbodiment.kt').read_text())
    def test_stop_voice_does_not_claim_or_call_provider_task_cancel(self):
        source=(OVERLAY/'OverlaySurfaceController.kt').read_text()
        start=source.index('fun stopVoice()');end=source.index('fun voice()',start)
        stop=source[start:end]
        self.assertIn('invalidateVoiceContext()',stop)
        self.assertIn('cancelOwnerTurn()',stop)
        self.assertIn('onBargeInRequested()',stop)
        self.assertNotIn('gateway',stop.lower())
        self.assertIn('Stopping voice does not cancel submitted tasks.',(OVERLAY/'WorkboardVoiceControls.kt').read_text())
    def test_underlying_app_remains_touchable_outside_own_workboard(self):
        source=(OVERLAY/'OverlayWindowFlags.kt').read_text()
        self.assertIn('FLAG_NOT_TOUCH_MODAL',source)
        self.assertIn('FLAG_NOT_FOCUSABLE',source)
    def test_accessibility_has_named_actions_not_only_gesture_hints(self):
        source=(OVERLAY/'OverlayAccessibleControls.kt').read_text()
        for label in ['Move left','Move right','Move up','Move down','Open chat','Stop voice; tasks continue']:
            self.assertIn('CustomAccessibilityAction("'+label+'"',source)
    def test_complete_virtualized_history_and_explicit_latest_are_retained(self):
        source=(OVERLAY/'WorkboardConversation.kt').read_text()
        self.assertIn('items(messages, key = { it.id })',source)
        self.assertIn('Latest messages',source)
        self.assertNotIn('takeLast(',source)
        self.assertIn('rememberReducedMotion()',source)

if __name__=='__main__':unittest.main(verbosity=2)
