package com.dial.van.instrumentation

import android.content.Intent
import android.os.SystemClock
import android.view.TextureView
import android.view.View
import android.view.ViewGroup
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.rive.runtime.kotlin.core.File as RiveFile
import app.rive.runtime.kotlin.core.SMINumber
import com.dial.van.visual.*
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.security.MessageDigest

/** Actual Android/JNI render checks prepared for the approved review APK.
 * Assembly is NOT execution. No task, microphone, vehicle or trading effect occurs.
 */
@RunWith(AndroidJUnit4::class)
class CharacterReviewNativeTest {
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val context get() = instrumentation.targetContext
    @Test fun exactReviewBytesImportThroughActualAndroidJni() {
        assumeTrue("Dedicated unaccepted review package required", VanCharacterAssets.reviewBuild)
        val loaded=VanCharacterAssets.load(context)
        val expected=InstrumentationRegistry.getArguments().getString("vanReviewSha256")
            ?: error("Explicit exact candidate hash is required for a review run")
        val digest=MessageDigest.getInstance("SHA-256").digest(loaded.bytes).joinToString(""){"%02x".format(it)}
        assertEquals(expected,digest)
        assertEquals((15..26).toSet(),VanRiveContextCapabilities.resolve(loaded.bytes,loaded.metadata))
        VanRiveRuntime.ensure(context)
        val file=RiveFile(loaded.bytes)
        try {
            val art=file.artboard(RiveBindingContract.ARTBOARD)
            val machine=art.stateMachine(RiveBindingContract.STATE_MACHINE)
            assertEquals(17,machine.inputs.size)
            assertEquals(26,VanRiveContextCapabilities.candidateActions((15..26).toSet()).last())
            assertTrue(machine.inputs.any {it.name=="action_code" && it is SMINumber})
        } finally {file.release()}
    }
    @Test fun floatingRendererSelectsReviewAndProducesActualTexturePixels() {
        assumeTrue("Dedicated unaccepted review package required",VanCharacterAssets.reviewBuild)
        val intent=Intent(context,RiveCandidateHostActivity::class.java)
            .putExtra(RiveCandidateHostActivity.EXTRA_PRODUCTION_PATH,true)
            .putExtra(RiveCandidateHostActivity.EXTRA_STATE,9)
            .putExtra(RiveCandidateHostActivity.EXTRA_SPEAKING,true)
            .putExtra(RiveCandidateHostActivity.EXTRA_MOUTH_OPEN,.7f)
        ActivityScenario.launch<RiveCandidateHostActivity>(intent).use {scenario->
            instrumentation.waitForIdleSync();SystemClock.sleep(2_000)
            assertEquals(VanRenderer.RIVE,RiveCandidateHostActivity.lastProductionDecision?.renderer)
            assertEquals((15..26).toSet(),RiveCandidateHostActivity.lastContextCodes)
            var pixelCount=0
            scenario.onActivity {activity->
                val texture=findTexture(activity.window.decorView) ?: error("Actual Rive TextureView absent")
                val bitmap=texture.bitmap ?: error("Native renderer did not deliver a texture")
                try {
                    val pixels=IntArray(bitmap.width*bitmap.height);bitmap.getPixels(pixels,0,bitmap.width,0,0,bitmap.width,bitmap.height)
                    pixelCount=pixels.count { (it ushr 24)>32 }
                } finally {bitmap.recycle()}
            }
            assertTrue("Native character texture is empty",pixelCount>100)
        }
    }
    private fun findTexture(view:View):TextureView? {
        if(view is TextureView)return view
        if(view is ViewGroup)for(i in 0 until view.childCount)findTexture(view.getChildAt(i))?.let{return it}
        return null
    }
}
