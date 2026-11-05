"""Wiring guardrails for the shipping overlay, not a handset UI-performance claim."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / 'android/app/src/main/java/com/dial/van/overlay'

def source(name): return (OVERLAY / name).read_text()

class FloatingUsabilityContracts(unittest.TestCase):
    def test_focusable_board_never_becomes_a_full_screen_touch_modal(self):
        s=source('OverlayWindowFlags.kt')
        self.assertIn('WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL',s)
        self.assertIn('WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE',s)
        self.assertNotIn('FLAG_NOT_TOUCHABLE',s)
    def test_non_gesture_assistant_actions_are_explicitly_available(self):
        s=source('OverlayAccessibleControls.kt')
        for label in ['Open chat','Start voice conversation','Stop voice; tasks continue','Minimize VAN','Dock VAN','Close floating assistant']:
            self.assertIn('CustomAccessibilityAction("'+label+'")',s)
        self.assertIn('role = Role.Button',s)
        self.assertIn('paneTitle = "VAN workboard"',s)
    def test_native_click_semantics_describe_actions_not_undiscoverable_gestures(self):
        s=source('OverlayNativeGestures.kt')
        self.assertIn('onClickLabel = "Open or close VAN workboard"',s)
        self.assertIn('onLongClickLabel = "Show assistant actions"',s)
    def test_escape_first_releases_the_keyboard_then_collapses_board(self):
        s=source('OverlayAccessibleControls.kt')
        self.assertIn('KeyEventType.KeyUp',s);self.assertIn('keyboard?.hide(); focus.clearFocus()',s)
        self.assertIn('OverlayUsabilityPolicy.dismiss',s)
        self.assertNotIn('stopSelf',s)
    def test_history_is_virtualized_but_not_arbitrarily_truncated(self):
        s=source('WorkboardConversation.kt')
        self.assertIn('LazyColumn(',s);self.assertIn('items(messages, key = { it.id })',s)
        self.assertNotIn('takeLast(',s);self.assertIn('Latest messages',s)
        self.assertIn('tailOverflow(',s)
    def test_layout_growth_is_separate_from_owner_scroll_intent(self):
        s=source('WorkboardConversation.kt')
        self.assertIn('if (!ownScroll)',s);self.assertIn('policy.ownerViewport',s)
        self.assertIn('if (intent == ConversationScrollIntent.IMMEDIATE || reduced)',s)
    def test_real_capture_speech_and_processing_statuses_are_not_invented_from_tab(self):
        s=source('WorkboardVoiceControls.kt')
        self.assertIn('app.voiceUi.state.collectAsState()',s)
        self.assertIn('app.voiceSession.ownerTurnActive.collectAsState()',s)
        self.assertIn('OverlayUsabilityPolicy.voiceStatus',s)
        self.assertIn('Stopping voice does not cancel submitted tasks.',s)
    def test_stop_voice_cancels_capture_and_output_but_not_dispatched_tasks(self):
        s=source('OverlaySurfaceController.kt');section=s[s.index('fun stopVoice()'):s.index('fun voice()')]
        for expected in ['invalidateVoiceContext()','cancelOwnerTurn()','onBargeInRequested()']:self.assertIn(expected,section)
        for forbidden in ['cancelTask','abortMission','dispatchCommand','delete']:self.assertNotIn(forbidden,section)
        self.assertIn('"Close" -> { stopVoice(); onClose() }',s)
    def test_voice_tab_does_not_start_the_microphone_without_start_action(self):
        s=source('VanOverlayWorkboards.kt')
        self.assertIn('selected = state.workboardMode == VanWorkboardMode.VOICE) { actions.onWorkboardMode(VanWorkboardMode.VOICE) }',s)
        self.assertIn('if (state.workboardMode == VanWorkboardMode.VOICE || voiceActive)',s)
    def test_duplicate_send_checks_current_controller_state_before_clearing_draft(self):
        s=source('VanOverlayPanels.kt');a=s.index('fun send()');b=s.index('Row(',a);part=s[a:b]
        self.assertIn('draftGate.submit(draft, draftLease, app.commandController.state.value.submitting)',part)
        self.assertIn('OverlaySubmissionGuard.Result.LOCALLY_RECORDED',part)
        self.assertIn('it.id !in previous && it.role == VanMessageRole.OWNER && it.text == text',part)
        self.assertLess(part.index('submitText('),part.index('onDraft("")'))
        self.assertIn('Your draft is still here.',part)
    def test_old_trading_view_is_not_displayed_beneath_new_selection(self):
        s=source('VanOverlayPanels.kt');p=s[s.index('LaunchedEffect(view, refresh)'):s.index('Column(modifier = Modifier.fillMaxWidth().weight(1f))')]
        self.assertLess(p.index('state = TradeBookState.Loading'),p.index('tradingTrades('))
        self.assertIn('failure is kotlinx.coroutines.CancellationException',p)
    def test_quick_actions_are_bounded_and_scrollable(self):
        s=source('VanOverlaySurface.kt')
        self.assertIn('OverlayUsabilityPolicy.quickControlsWidth',s);self.assertIn('OverlayUsabilityPolicy.quickControlsHeight',s)
        self.assertIn('items(OverlayTheme.QUICK_CONTROLS, key = { it })',s)
        self.assertNotIn('.offset(x = 176.dp',s)
        self.assertIn('Return to VAN',s)
    def test_transient_animation_is_read_in_its_own_restart_scope(self):
        s=source('VanOverlaySurface.kt')
        self.assertIn('derivedStateOf { OverlayPresentationFrame.chrome(VanLiveVisualState.frame) }',s)
        live=source('LiveOverlayEmbodiment.kt');self.assertIn('val live = VanLiveVisualState.frame',live)
        self.assertIn('OverlayPresentationFrame.character(state, live)',live)
        board=source('VanOverlayWorkboards.kt');self.assertIn('map { it.speaking }.distinctUntilChanged()',board)
        self.assertIn('map { it.listening }.distinctUntilChanged()',board)
    def test_character_identity_and_service_architecture_not_replaced(self):
        self.assertLess(len(source('FloatingOverlayService.kt').splitlines()),450)
        self.assertIn('VanEmbodiment(',source('LiveOverlayEmbodiment.kt'))
        self.assertIn('VanMinimizedAvatar(',source('VanOverlaySurface.kt'))
    def test_rejected_field_arc_operations_are_still_retired(self):
        renderer=(ROOT/'android/app/src/main/java/com/dial/van/visual/VanAura.kt').read_text()
        for retired in ['Polyline','Quad','Rim']:
            self.assertIn('is VanAuraOp.'+retired+' -> Unit',renderer)
        # The original dedicated aura-contract suite remains the source of exact renderer assertions.
        self.assertTrue((ROOT/'android/verification/src/test/kotlin/com/dial/van/visual/VanAuraNoFieldLinesTest.kt').is_file())

if __name__=='__main__':unittest.main(verbosity=2)
