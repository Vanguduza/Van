package com.dial.van.overlay

import kotlin.random.Random
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** Independent tests against selected production draft/movement interfaces. */
class OverlayUsabilityIndependentReviewTest {
    @Test fun queuedOldCallbackCannotReplayAfterDraftClearedAndFastResponseFinished() {
        val g=OverlaySubmissionGuard();val old=g.observe("old command");var deliveries=0
        assertEquals(OverlaySubmissionGuard.Result.LOCALLY_RECORDED,g.submit("old command",old,false){deliveries++;true})
        g.observe("")
        assertEquals(OverlaySubmissionGuard.Result.STALE,g.submit("old command",old,false){deliveries++;true})
        assertEquals(1,deliveries)
    }
    @Test fun delayedOldSendCannotReplaceTheOwnersNewDraft() {
        val g=OverlaySubmissionGuard();val old=g.observe("first");val current=g.observe("second")
        assertEquals(OverlaySubmissionGuard.Result.STALE,g.submit("first",old,false){error("stale")})
        assertEquals(OverlaySubmissionGuard.Result.LOCALLY_RECORDED,g.submit("second",current,false){it=="second"})
    }
    @Test fun clearAndRetypeSameTextHasASeparateLease() {
        val g=OverlaySubmissionGuard();val a=g.observe("same");g.submit("same",a,false){true}
        g.observe("");val b=g.observe("same")
        assertTrue(b>a);assertEquals(OverlaySubmissionGuard.Result.STALE,g.submit("same",a,false){error("old lease")})
        assertEquals(OverlaySubmissionGuard.Result.LOCALLY_RECORDED,g.submit("same",b,false){true})
    }
    @Test fun editedDraftKeepsItsManualSubmissionAfterBusyClears() {
        val g=OverlaySubmissionGuard();val lease=g.observe("keep this")
        assertEquals(OverlaySubmissionGuard.Result.BUSY,g.submit("keep this",lease,true){error("busy")})
        assertEquals(OverlaySubmissionGuard.Result.LOCALLY_RECORDED,g.submit("keep this",lease,false){true})
    }
    @Test fun localRefusalDoesNotPretendRemoteAcceptanceOrAutoRetry() {
        val g=OverlaySubmissionGuard();val lease=g.observe("keep this");var calls=0
        assertEquals(OverlaySubmissionGuard.Result.NOT_RECORDED,g.submit("keep this",lease,false){calls++;false})
        assertEquals(1,calls)
        assertEquals(OverlaySubmissionGuard.Result.LOCALLY_RECORDED,g.submit("keep this",lease,false){calls++;true})
        assertEquals(2,calls)
    }
    @Test fun allAccessibleDirectionsRespectImeAndSafeInsets() {
        val bounds=OverlayScreen(1000,2000,10,24,990,1960)
        for(direction in OverlayMoveDirection.entries){
            val p=OverlayAccessibleMovement.target(OverlayPlacement(950,1500),OverlaySize(184,184),bounds,direction,48,1000)
            assertTrue(p.x in 10..806);assertTrue(p.y in 24..816)
        }
    }
    @Test fun extremeCoordinatesCannotOverflowMovementToTheWrongSide() {
        val p=OverlayAccessibleMovement.target(OverlayPlacement(Int.MAX_VALUE,Int.MAX_VALUE),OverlaySize(48,48),OverlayScreen(1000,2000),OverlayMoveDirection.RIGHT,Int.MAX_VALUE,null)
        assertEquals(OverlayPlacement(952,1952),p)
    }
    @Test fun tinyViewportKeepsLargePanelAtReachableSafeOrigin() {
        val p=OverlayAccessibleMovement.target(OverlayPlacement(-99,-99),OverlaySize(200,200),OverlayScreen(40,40,10,15,30,35),OverlayMoveDirection.LEFT,48,20)
        assertEquals(OverlayPlacement(10,15),p)
    }
    @Test fun fiveThousandAccessibleMovementsRemainInsideCurrentInsetsAndIme() {
        val random=Random(20261105)
        repeat(5000){
            val width=random.nextInt(80,2400);val height=random.nextInt(80,3000);val inset=random.nextInt(0,30)
            val screen=OverlayScreen(width,height,inset,inset,width-inset,height-inset)
            val w=random.nextInt(1,width);val h=random.nextInt(1,height);val ime=random.nextInt(inset,height)
            val p=OverlayAccessibleMovement.target(OverlayPlacement(random.nextInt(-200,2600),random.nextInt(-200,3200)),OverlaySize(w,h),screen,OverlayMoveDirection.entries[random.nextInt(4)],48,ime)
            assertTrue(p.x in screen.safeLeft..maxOf(screen.safeLeft,screen.safeRight-w))
            assertTrue(p.y in screen.safeTop..maxOf(screen.safeTop,minOf(screen.safeBottom,ime)-h))
        }
    }
    @Test fun keyboardBackIsNotBoardDismissalOrTaskCancellation() {
        assertEquals(OverlayDismissStep.HIDE_KEYBOARD,OverlayUsabilityPolicy.dismiss(true,true))
        assertEquals(OverlayDismissStep.RETURN_TO_CHARACTER,OverlayUsabilityPolicy.dismiss(true,false))
        assertEquals(OverlayDismissStep.NONE,OverlayUsabilityPolicy.dismiss(false,true))
    }
    @Test fun streamingSameMessageNeverStealsReadingPosition() {
        val p=ConversationFollowPolicy();p.content("last","old",false,false);p.ownerViewport(false,true)
        repeat(500){assertEquals(ConversationScrollIntent.NONE,p.content("last","revision-$it",false,false))}
        assertTrue(p.unread)
    }
    @Test fun readerExplicitlyChoosesWhenToResumeFollowing() {
        val p=ConversationFollowPolicy();p.content("first","text",false,false)
        assertEquals(ConversationScrollIntent.NONE,p.content("second","reply",false,true))
        assertEquals(ConversationScrollIntent.NONE,p.content("third","reply",false,false))
        assertEquals(ConversationScrollIntent.ANIMATE,p.latest());assertTrue(p.following)
    }
}
