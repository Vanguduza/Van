package com.dial.van.visual

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class VanPresentationPreferencesTest {
    private val quiet=VanPresentationPreferences(VanExpressionLevel.QUIET,idleOpacityPercent=60)
    @Test fun quietNeverSuppressesCriticalStatusOrGuidance() {
        for (s in listOf(VanDurableState.URGENT,VanDurableState.ERROR,VanDurableState.WARNING,VanDurableState.WAITING_FOR_OWNER,VanDurableState.OFFLINE)) {
            val state=VanVisualState(durableState=s,actionCode=VanFiniteAction.CAUTION.code)
            assertEquals(state,VanPersonalPresentation.project(state,quiet));assertEquals(1f,VanPersonalPresentation.opacity(state,quiet,true))
        }
        val point=VanVisualState(actionCode=VanFiniteAction.POINT_TARGET.code)
        assertEquals(point,VanPersonalPresentation.project(point,quiet))
    }
    @Test fun quietSuppressesDecorativeMovementButKeepsSpeechAndSemantics() {
        val state=VanVisualState(durableState=VanDurableState.SPEAKING,speaking=true,mouthOpen=.8f,viseme=3,actionCode=2,contextCode=15)
        val result=VanPersonalPresentation.project(state,quiet)
        assertEquals(state.copy(actionCode=0,contextCode=0),result);assertTrue(VanPersonalPresentation.motionAllowed(result,quiet,true))
    }
    @Test fun idleDimNeverDimsTheWorkboardOrAnActiveTurn() {
        val idle=VanVisualState(durableState=VanDurableState.IDLE)
        assertEquals(.6f,VanPersonalPresentation.opacity(idle,quiet,true));assertEquals(1f,VanPersonalPresentation.opacity(idle,quiet,false))
        assertEquals(1f,VanPersonalPresentation.opacity(idle.copy(listening=true),quiet,true))
        assertEquals(1f,VanPersonalPresentation.opacity(idle.copy(speaking=true),quiet,true))
    }
    @Test fun quietPausesIdleButRestoresAnimationForActualActivity() {
        assertFalse(VanPersonalPresentation.motionAllowed(VanVisualState(),quiet,true))
        assertTrue(VanPersonalPresentation.motionAllowed(VanVisualState(durableState=VanDurableState.WORKING),quiet,true))
    }
    @Test fun reducedMotionAndHiddenViewAlwaysWin() {
        val active=VanVisualState(durableState=VanDurableState.URGENT)
        assertFalse(VanPersonalPresentation.motionAllowed(active,quiet.copy(reducedMotion=true),true))
        assertFalse(VanPersonalPresentation.motionAllowed(active,VanPresentationPreferences(),false))
    }
    @Test fun defaultPreferencesPreserveExistingExpressiveBehavior() {
        val state=VanVisualState(durableState=VanDurableState.SUCCESS,actionCode=8)
        assertEquals(state,VanPersonalPresentation.project(state,VanPresentationPreferences()))
    }
    @Test fun quietDoesNotAlterWarningSemanticFieldOnIdlePose() {
        val state=VanVisualState(durableState=VanDurableState.IDLE,semanticState=VanDurableState.WARNING,actionCode=9)
        assertEquals(state,VanPersonalPresentation.project(state,quiet));assertEquals(1f,VanPersonalPresentation.opacity(state,quiet,true))
    }
    @Test fun preferencesCannotMakeCharacterInvisible() {
        assertEquals(55,quiet.copy(idleOpacityPercent=-999).normalized().idleOpacityPercent)
        assertEquals(100,quiet.copy(idleOpacityPercent=Int.MAX_VALUE).normalized().idleOpacityPercent)
    }
}
