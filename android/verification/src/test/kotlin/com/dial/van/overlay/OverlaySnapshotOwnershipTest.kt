package com.dial.van.overlay

import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class OverlaySnapshotOwnershipTest {
    @Test fun oldServiceQueuedWriteCannotOverwriteReplacementSession() {
        val state=OverlaySnapshotOwnership();val old=state.acquire();var text="initial"
        val new=state.acquire();assertTrue(state.write(new){text="new owner";true})
        assertFalse(state.write(old){text="old draft";true});assertEquals("new owner",state.read(new){text})
    }
    @Test fun obsoleteServiceCannotReadAnotherSessionsSnapshot() {
        val state=OverlaySnapshotOwnership();val old=state.acquire();state.acquire()
        assertNull(state.read(old){error("must not read stale owner")})
    }
    @Test fun acquiringReplacementNeverBlocksOnTheOldDiskCommit() {
        val state=OverlaySnapshotOwnership();val old=state.acquire();val entered=CountDownLatch(1);val release=CountDownLatch(1)
        val result=AtomicReference<Throwable?>();val thread=Thread {
            try { state.write(old){entered.countDown();check(release.await(3,TimeUnit.SECONDS));true} } catch(t:Throwable){result.set(t)}
        }
        thread.start();assertTrue(entered.await(3,TimeUnit.SECONDS))
        try { val next=state.acquire();assertTrue(next>old);assertTrue(state.current(next));assertFalse(state.current(old)) }
        finally { release.countDown();thread.join(3_000) }
        assertFalse(thread.isAlive);assertNull(result.get())
    }
    @Test fun replacementReadSeesWholeOldInflightCommitThenOwnNewWrite() {
        val state=OverlaySnapshotOwnership();val old=state.acquire();val entered=CountDownLatch(1);val release=CountDownLatch(1)
        var persisted="before";val writerError=AtomicReference<Throwable?>()
        val first=Thread { try {state.write(old){entered.countDown();check(release.await(3,TimeUnit.SECONDS));persisted="complete old";true}}catch(t:Throwable){writerError.set(t)} }
        first.start();assertTrue(entered.await(3,TimeUnit.SECONDS));val next=state.acquire();val read=AtomicReference<String?>();val readerStarted=CountDownLatch(1)
        val second=Thread {readerStarted.countDown();read.set(state.read(next){persisted})};second.start();assertTrue(readerStarted.await(3,TimeUnit.SECONDS))
        release.countDown();first.join(3_000);second.join(3_000)
        assertFalse(first.isAlive);assertFalse(second.isAlive);assertNull(writerError.get());assertEquals("complete old",read.get())
        state.write(next){persisted="replacement";true};assertFalse(state.write(old){persisted="late old";true});assertEquals("replacement",persisted)
    }
    @Test fun failingOldBackendDoesNotLeaveTheDiskLockHeld() {
        val state=OverlaySnapshotOwnership();val old=state.acquire()
        runCatching {state.write(old){error("disk failure")}}
        val next=state.acquire();assertTrue(state.write(next){true})
    }
}
