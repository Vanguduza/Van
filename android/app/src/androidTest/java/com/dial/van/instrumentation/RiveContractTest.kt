package com.dial.van.instrumentation

import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.os.ParcelFileDescriptor
import android.os.SystemClock
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.rive.runtime.kotlin.core.File as RiveFile
import app.rive.runtime.kotlin.core.SMIBoolean
import app.rive.runtime.kotlin.core.SMINumber
import app.rive.runtime.kotlin.core.SMITrigger
import com.dial.van.visual.RiveCandidateHostActivity
import com.dial.van.visual.RiveBindingContract
import com.dial.van.visual.VanCanvasReason
import com.dial.van.visual.VanRenderer
import com.dial.van.visual.VanRiveRuntime
import com.dial.van.visual.VanVisualRuntime
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.io.FileOutputStream
import kotlin.math.abs
import kotlin.math.min

@RunWith(AndroidJUnit4::class)
class RiveContractTest {
    private companion object {
        /** Floor for "visibly different" mean RGB distance (0-1) when measured noise is lower. */
        const val MIN_DISTINCT_RGB = 0.004
        /** ~300 ms into a 600-1800 ms action once the host's 250 ms input delay has elapsed. */
        const val ACTION_PEAK_MS = 550L
    }

    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val testContext get() = instrumentation.context
    private val targetContext get() = instrumentation.targetContext

    private enum class Mode { CORE, FULL, PRODUCTION }
    private data class Rig(val mode: Mode, val bytes: ByteArray)

    private fun rigOrSkip(): Rig {
        val candidate = runCatching { testContext.assets.open("van_candidate.riv").use { it.readBytes() } }.getOrNull()
        if (candidate != null) {
            val modeText = runCatching { testContext.assets.open("forge_mode.txt").bufferedReader().use { it.readText().trim() } }.getOrDefault("core")
            return Rig(if (modeText == "full") Mode.FULL else Mode.CORE, candidate)
        }
        val production = runCatching { targetContext.assets.open(RiveBindingContract.ASSET_FILE).use { it.readBytes() } }.getOrNull()
        assumeTrue("NO_RIVE_ASSET", production != null)
        return Rig(Mode.PRODUCTION, requireNotNull(production))
    }

    private fun contract(): JSONObject =
        JSONObject(testContext.assets.open("rive_contract.json").bufferedReader().use { it.readText() })

    private fun withMachine(block: (Rig, app.rive.runtime.kotlin.core.Artboard, app.rive.runtime.kotlin.core.StateMachineInstance) -> Unit) {
        val rig = rigOrSkip()
        VanRiveRuntime.ensure(targetContext)
        val file = RiveFile(rig.bytes)
        try {
            val artboard = file.artboard(RiveBindingContract.ARTBOARD)
            val machine = artboard.stateMachine(RiveBindingContract.STATE_MACHINE)
            block(rig, artboard, machine)
        } finally {
            file.release()
        }
    }

    @Test
    fun contractSurfaceMatches() = withMachine { _, _, machine ->
        val spec = contract()
        val expected = linkedMapOf<String, String>()
        val inputs = spec.getJSONArray("inputs")
        for (i in 0 until inputs.length()) {
            val row = inputs.getJSONObject(i)
            expected[row.getString("name")] = row.getString("type")
        }
        val triggers = spec.getJSONArray("triggers")
        for (i in 0 until triggers.length()) expected[triggers.getString(i)] = "trigger"
        val actual = machine.inputs.associate { input ->
            input.name to when (input) {
                is SMINumber -> "number"
                is SMIBoolean -> "boolean"
                is SMITrigger -> "trigger"
                else -> "unknown"
            }
        }
        assertEquals(expected, actual)
        val rig = rigOrSkip()
        if (rig.mode == Mode.PRODUCTION) {
            val decision = VanVisualRuntime.decide(
                assetBytes = rig.bytes.size.toLong(),
                riveRuntimeAvailable = true,
                ownerArtAvailable = true,
            )
            assertEquals("production asset must select the Rive renderer", VanRenderer.RIVE, decision.renderer)
        }
    }

    /**
     * The shipped asset must load and bind through the composable production renders
     * (`VanAvatar` -> `VanRiveAvatar`), not only through the debug frame host: a load or bind
     * failure there flips the decision to OWNER_ART/CANVAS with LOAD_FAILED.
     */
    @Test
    fun productionAvatarPathKeepsRive() {
        val rig = rigOrSkip()
        assumeTrue("PRODUCTION_ONLY", rig.mode == Mode.PRODUCTION)
        RiveCandidateHostActivity.lastProductionDecision = null
        val intent = Intent(targetContext, RiveCandidateHostActivity::class.java)
            .putExtra(RiveCandidateHostActivity.EXTRA_PRODUCTION_PATH, true)
            .putExtra(RiveCandidateHostActivity.EXTRA_STATE, 9)
            .putExtra(RiveCandidateHostActivity.EXTRA_SPEAKING, true)
            .putExtra(RiveCandidateHostActivity.EXTRA_MOUTH_OPEN, 0.7f)
            .putExtra(RiveCandidateHostActivity.EXTRA_ACTION, 1)
        ActivityScenario.launch<RiveCandidateHostActivity>(intent).use {
            instrumentation.waitForIdleSync()
            SystemClock.sleep(2_000L)
            val decision = RiveCandidateHostActivity.lastProductionDecision
            assertTrue("VanAvatar never reported a renderer decision", decision != null)
            assertEquals("production VanAvatar fell back: ${decision?.reason}", VanRenderer.RIVE, decision?.renderer)
        }
    }

    @Test
    fun coreInputsDriveTheRig() {
        val rig = rigOrSkip()
        val gazeA = capture(rig, "gaze-neg", state = 4, attentionX = -1f, attentionY = -1f)
        val gazeB = capture(rig, "gaze-pos", state = 4, attentionX = 1f, attentionY = 1f)
        assertTrue("gaze extremes are pixel-identical", meanAbsRgb(gazeA, gazeB) > 0.001)
        val mouth0 = capture(rig, "mouth-0", state = 9, speaking = true, mouthOpen = 0f, viseme = 2)
        val mouth1 = capture(rig, "mouth-1", state = 9, speaking = true, mouthOpen = 1f, viseme = 2)
        assertTrue("mouth_open 0 and 1 are pixel-identical", meanAbsRgb(mouth0, mouth1) > 0.001)

        for (state in listOf(2, 4, 5, 9)) capture(rig, "core-state-$state", state = state)
        for ((action, trigger) in listOf(1 to "wave", 2 to "ack", 7 to "point")) {
            capture(rig, "core-action-$action", state = 2, action = action, trigger = trigger)
        }
        for ((x, y) in listOf(-1f to -1f, 1f to -1f, -1f to 1f, 1f to 1f, 0f to 0f)) {
            capture(rig, "attention-${x.toInt()}-${y.toInt()}", state = 4, attentionX = x, attentionY = y)
        }
        val threshold = distinctThreshold(rig)
        for ((action, trigger) in listOf(1 to "wave", 2 to "ack", 7 to "point")) {
            val idle = capture(rig, "core-idle-peak-$action", state = 2, settleMs = ACTION_PEAK_MS)
            val peak = capture(rig, "core-action-peak-$action", state = 2, action = action, trigger = trigger, settleMs = ACTION_PEAK_MS)
            val diff = meanAbsRgb(idle, peak)
            assertTrue("core action $action is indistinguishable from IDLE ($diff <= $threshold)", diff > threshold)
        }
        // Overlay (96 dp) and minimized (48 dp) sizes: evidence for readability review, never blank.
        for (sizeDp in listOf(96, 48)) {
            for ((name, state) in listOf("idle" to 2, "listening" to 4, "thinking" to 5, "speaking" to 9)) {
                val frame = capture(rig, "size-$sizeDp-$name", state = state, speaking = state == 9, mouthOpen = if (state == 9) 0.7f else 0f, sizeDp = sizeDp)
                assertFalse("$name at $sizeDp dp is blank", looksBlank(frame))
            }
        }
        for (viseme in 0..4) capture(rig, "viseme-$viseme", state = 9, speaking = true, mouthOpen = 0.7f, viseme = viseme)
        capture(rig, "listening-on", state = 4, listening = true)
        capture(rig, "listening-off", state = 4, listening = false)
        capture(rig, "speaking-on", state = 9, speaking = true)
        capture(rig, "speaking-off", state = 9, speaking = false)
        if (rig.mode != Mode.CORE) assertCoreBaselines(rig)
    }

    @Test
    fun everyStateAndActionRenders() {
        val rig = rigOrSkip()
        assumeTrue("FULL_OR_PRODUCTION_ONLY", rig.mode != Mode.CORE)
        val threshold = distinctThreshold(rig)
        val idle = capture(rig, "state-2", state = 2)
        for (state in 0..17) {
            val frame = if (state == 2) idle else capture(rig, "state-$state", state = state)
            assertFalse("state $state produced a transparent/blank frame", looksBlank(frame))
            if (state != 2) {
                val diff = meanAbsRgb(idle, frame)
                assertTrue("state $state is indistinguishable from IDLE ($diff <= $threshold)", diff > threshold)
            }
        }
        // Production drives actions through `action_code` only (VanRiveAvatar fires no trigger),
        // so each action must read without its trigger.
        val idlePeak = capture(rig, "action-idle-peak", state = 2, settleMs = ACTION_PEAK_MS)
        for (action in 1..14) {
            val frame = capture(rig, "action-$action", state = 2, action = action, settleMs = ACTION_PEAK_MS)
            assertFalse("action $action produced a transparent/blank frame", looksBlank(frame))
            val diff = meanAbsRgb(idlePeak, frame)
            assertTrue("action $action via action_code is indistinguishable from IDLE ($diff <= $threshold)", diff > threshold)
        }
    }

    @Test
    fun mandatoryCombinations() {
        val rig = rigOrSkip()
        assumeTrue("FULL_OR_PRODUCTION_ONLY", rig.mode != Mode.CORE)
        val cases = listOf(
            Case("working-speaking", 7, speaking = true),
            Case("thinking-speaking", 5, speaking = true),
            Case("waiting-owner-speaking", 11, speaking = true),
            Case("urgent-speaking", 16, speaking = true, urgency = 1f),
            Case("listening-attention", 4, listening = true, attentionX = 1f),
            Case("working-point", 7, action = 7, trigger = "point"),
            Case("waiting-present", 11, action = 12, trigger = "present"),
            Case("success-celebrate", 15, action = 8, trigger = "celebrate"),
            Case("warning-caution", 13, action = 9, trigger = "warning"),
            Case("degraded-listening", 12, listening = true),
        )
        for (case in cases) {
            val frame = capture(rig, case.name, state=case.state, speaking=case.speaking, listening=case.listening, attentionX=case.attentionX, urgency=case.urgency, action=case.action, trigger=case.trigger)
            assertFalse(case.name, looksBlank(frame))
        }
    }

    @Test
    fun invalidInputsDegradeSafely() {
        val rig = rigOrSkip()
        val cases = listOf(
            Case("bad-state--1", -1), Case("bad-state-18", 18), Case("bad-state-999", 999),
            Case("bad-action--1", 2, action=-1), Case("bad-action-15", 2, action=15), Case("bad-action-999", 2, action=999),
            Case("bad-attention", 2, attentionX=2f), Case("bad-attention-neg", 2, attentionX=-2f),
            Case("bad-mouth-neg", 9, mouthOpen=-1f), Case("bad-mouth-pos", 9, mouthOpen=2f),
            Case("bad-urgency-neg", 16, urgency=-1f), Case("bad-urgency-pos", 16, urgency=2f),
            Case("bad-viseme", 9, speaking=true, viseme=99),
        )
        for (case in cases) {
            val frame = capture(rig, case.name, state=case.state, speaking=case.speaking, attentionX=case.attentionX, mouthOpen=case.mouthOpen, urgency=case.urgency, viseme=case.viseme, action=case.action)
            assertFalse(case.name, looksBlank(frame))
        }
    }

    @Test
    fun artboardIsTransparentOnThreeBackgrounds() {
        val rig = rigOrSkip()
        val lightBg = Color.rgb(244, 246, 248)
        val darkBg = Color.rgb(11, 15, 20)
        val light = capture(rig, "transparent-light", background = "light", state = 2)
        val dark = capture(rig, "transparent-dark", background = "dark", state = 2)
        assertCornersNear(light, lightBg)
        assertCornersNear(dark, darkBg)
        // Opaque pixels look the same on both backgrounds; empty pixels equal their background.
        // A pixel that differs from both backgrounds AND between them is translucent. Only the
        // visor lens and orb glow may be; a full-artboard glow is the Android aura's job.
        var translucent = 0
        var sampled = 0
        for (y in 0 until min(light.height, dark.height) step 2) for (x in 0 until min(light.width, dark.width) step 2) {
            val l = light.getPixel(x, y)
            val d = dark.getPixel(x, y)
            if (channelDistance(l, lightBg) > 24 && channelDistance(d, darkBg) > 24 && channelDistance(l, d) > 24) translucent++
            sampled++
        }
        val fraction = translucent.toDouble() / sampled.coerceAtLeast(1)
        outputDir(rig).resolve("translucency.txt").apply { parentFile?.mkdirs() }.writeText("translucent_fraction=$fraction\n")
        val limit = threshold("max_translucent_fraction", 0.08)
        assertTrue("translucent coverage $fraction > $limit: a halo/aura is baked into the artboard", fraction <= limit)
        val busy = capture(rig, "transparent-busy", background = "busy", state = 2)
        assertFalse("busy background frame is blank", looksBlank(busy))
        assertBusyCornersUnaffected(busy)
    }

    @Test
    fun identityColourFamilies() {
        val rig = rigOrSkip()
        val frame = capture(rig, "identity", background = "dark", state = 2)
        var silver = 0; var cyan = 0; var samples = 0
        for (y in 0 until frame.height step 3) for (x in 0 until frame.width step 3) {
            val c = frame.getPixel(x, y)
            val r = Color.red(c); val g = Color.green(c); val b = Color.blue(c)
            val max = maxOf(r, g, b); val min = minOf(r, g, b)
            if (y < frame.height / 2 && max > 150 && max - min < 55) silver++
            if (g > 90 && b > 100 && b >= r * 1.2 && g >= r * 1.2) cyan++
            samples++
        }
        assertTrue("silver/white hair family not detected", silver > samples / 250)
        assertTrue("cyan family not detected", cyan > samples / 400)
    }

    @Test
    fun idleSoakFrameStats() {
        val rig = rigOrSkip()
        assumeTrue("FULL_OR_PRODUCTION_ONLY", rig.mode != Mode.CORE)
        launchScenario(rig, state = 2).use {
            // Count only the soak: gfxinfo is cumulative since process start (launch frames).
            // It measures HWUI frames; Rive's own render thread is profiled on the S24 (Perfetto).
            SystemClock.sleep(2_000L)
            shell("dumpsys gfxinfo ${targetContext.packageName} reset")
            SystemClock.sleep(300_000L)
            val text = shell("dumpsys gfxinfo ${targetContext.packageName}")
            val out = outputDir(rig).resolve("gfxinfo.txt")
            out.parentFile?.mkdirs()
            out.writeText(text)
            val percent = Regex("""Janky frames:\s+\d+\s+\(([0-9.]+)%\)""").find(text)?.groupValues?.get(1)?.toDouble()
            assertTrue("could not parse Janky frames percentage", percent != null)
            val threshold = runCatching {
                JSONObject(testContext.assets.open("forge_thresholds.json").bufferedReader().use { r -> r.readText() }).getDouble("max_janky_percent")
            }.getOrDefault(5.0)
            assertTrue("janky frames $percent% > $threshold%", requireNotNull(percent) <= threshold)
        }
    }

    @Test
    fun brokenAssetFallsBack() {
        val unusable = VanVisualRuntime.decide(assetBytes = 512L, riveRuntimeAvailable = true, ownerArtAvailable = true)
        assertEquals(VanRenderer.CANVAS, unusable.renderer)
        assertEquals(VanCanvasReason.ASSET_UNUSABLE, unusable.reason)
        val failed = VanVisualRuntime.decide(assetBytes = 4096L, riveRuntimeAvailable = true, ownerArtAvailable = true, loadFailed = true)
        assertEquals(VanRenderer.CANVAS, failed.renderer)
        assertEquals(VanCanvasReason.LOAD_FAILED, failed.reason)
    }


    private fun assertCoreBaselines(rig: Rig) {
        data class BaselineCase(
            val name: String,
            val state: Int = 2,
            val speaking: Boolean = false,
            val listening: Boolean = false,
            val attentionX: Float = 0f,
            val attentionY: Float = 0f,
            val mouthOpen: Float = 0f,
            val viseme: Int = 0,
            val action: Int = 0,
            val trigger: String? = null,
        )
        val cases = listOf(
            BaselineCase("gaze-neg", state=4, attentionX=-1f, attentionY=-1f),
            BaselineCase("gaze-pos", state=4, attentionX=1f, attentionY=1f),
            BaselineCase("mouth-0", state=9, speaking=true, mouthOpen=0f, viseme=2),
            BaselineCase("mouth-1", state=9, speaking=true, mouthOpen=1f, viseme=2),
            BaselineCase("core-state-2", state=2),
            BaselineCase("core-state-4", state=4),
            BaselineCase("core-state-5", state=5),
            BaselineCase("core-state-9", state=9),
            BaselineCase("core-action-1", state=2, action=1, trigger="wave"),
            BaselineCase("core-action-2", state=2, action=2, trigger="ack"),
            BaselineCase("core-action-7", state=2, action=7, trigger="point"),
        )
        for (item in cases) {
            val baseline = runCatching {
                testContext.assets.open("core_baseline/${item.name}.png").use(BitmapFactory::decodeStream)
            }.getOrNull()
            assertTrue("missing M2 core baseline ${item.name}", baseline != null)
            val current = capture(
                rig, "regression-${item.name}", state=item.state, speaking=item.speaking,
                listening=item.listening, attentionX=item.attentionX, attentionY=item.attentionY,
                mouthOpen=item.mouthOpen, viseme=item.viseme, action=item.action, trigger=item.trigger,
            )
            val diff = meanAbsRgb(requireNotNull(baseline), current)
            assertTrue("core regression ${item.name}: mean RGB difference $diff > 0.06", diff <= 0.06)
        }
    }

    private data class Case(
        val name:String, val state:Int, val speaking:Boolean=false, val listening:Boolean=false,
        val attentionX:Float=0f, val mouthOpen:Float=0f, val urgency:Float=0f, val viseme:Int=0,
        val action:Int=0, val trigger:String?=null,
    )

    private fun launchScenario(
        rig: Rig, background: String = "dark", state: Int = 2, speaking: Boolean = false,
        listening: Boolean = false, attentionX: Float = 0f, attentionY: Float = 0f,
        mouthOpen: Float = 0f, urgency: Float = 0f, viseme: Int = 0, action: Int = 0,
        trigger: String? = null, sizeDp: Int = 320,
    ): ActivityScenario<RiveCandidateHostActivity> {
        val intent = Intent(targetContext, RiveCandidateHostActivity::class.java)
            .putExtra(RiveCandidateHostActivity.EXTRA_TEST_MODE, true)
            .putExtra(RiveCandidateHostActivity.EXTRA_PRODUCTION, rig.mode == Mode.PRODUCTION)
            .putExtra(RiveCandidateHostActivity.EXTRA_BACKGROUND, background)
            .putExtra(RiveCandidateHostActivity.EXTRA_SIZE_DP, sizeDp)
            .putExtra(RiveCandidateHostActivity.EXTRA_STATE, state)
            .putExtra(RiveCandidateHostActivity.EXTRA_SPEAKING, speaking)
            .putExtra(RiveCandidateHostActivity.EXTRA_LISTENING, listening)
            .putExtra(RiveCandidateHostActivity.EXTRA_ATTENTION_X, attentionX)
            .putExtra(RiveCandidateHostActivity.EXTRA_ATTENTION_Y, attentionY)
            .putExtra(RiveCandidateHostActivity.EXTRA_MOUTH_OPEN, mouthOpen)
            .putExtra(RiveCandidateHostActivity.EXTRA_URGENCY, urgency)
            .putExtra(RiveCandidateHostActivity.EXTRA_VISEME, viseme)
            .putExtra(RiveCandidateHostActivity.EXTRA_ACTION, action)
        if (trigger != null) intent.putExtra(RiveCandidateHostActivity.EXTRA_TRIGGER, trigger)
        return ActivityScenario.launch(intent)
    }

    private fun capture(
        rig: Rig, name: String, background: String = "dark", state: Int = 2,
        speaking: Boolean = false, listening: Boolean = false, attentionX: Float = 0f,
        attentionY: Float = 0f, mouthOpen: Float = 0f, urgency: Float = 0f,
        viseme: Int = 0, action: Int = 0, trigger: String? = null, sizeDp: Int = 320,
        settleMs: Long = 850L,
    ): Bitmap {
        launchScenario(rig, background, state, speaking, listening, attentionX, attentionY, mouthOpen, urgency, viseme, action, trigger, sizeDp).use {
            instrumentation.waitForIdleSync()
            SystemClock.sleep(settleMs)
            val screen = instrumentation.uiAutomation.takeScreenshot()
            val density = targetContext.resources.displayMetrics.density
            val size = min((sizeDp * density).toInt(), min(screen.width, screen.height))
            val x = ((screen.width - size) / 2).coerceAtLeast(0)
            val y = ((screen.height - size) / 2).coerceAtLeast(0)
            val crop = Bitmap.createBitmap(screen, x, y, size, size)
            val out = outputDir(rig).resolve("$name.png")
            out.parentFile?.mkdirs()
            FileOutputStream(out).use { crop.compress(Bitmap.CompressFormat.PNG, 100, it) }
            return crop
        }
    }

    private fun outputDir(rig: Rig): File {
        val additional = InstrumentationRegistry.getArguments().getString("additionalTestOutputDir")
        val root = additional?.let(::File) ?: targetContext.filesDir
        return File(root, "rive/${rig.mode.name.lowercase()}")
    }

    private fun shell(command: String): String {
        val fd: ParcelFileDescriptor = instrumentation.uiAutomation.executeShellCommand(command)
        return ParcelFileDescriptor.AutoCloseInputStream(fd).bufferedReader().use { it.readText() }
    }

    /**
     * Two IDLE captures differ by breathing/blink phase alone. A state or action only counts as
     * "different" when it clears that measured noise with margin, never a fixed 0.1 %.
     */
    private fun distinctThreshold(rig: Rig): Double {
        val a = capture(rig, "noise-idle-a", state = 2)
        val b = capture(rig, "noise-idle-b", state = 2)
        val noise = meanAbsRgb(a, b)
        val floor = threshold("min_distinct_rgb", MIN_DISTINCT_RGB)
        return maxOf(floor, 3.0 * noise)
    }

    private fun threshold(name: String, default: Double): Double = runCatching {
        JSONObject(testContext.assets.open("forge_thresholds.json").bufferedReader().use { it.readText() }).getDouble(name)
    }.getOrDefault(default)

    private fun channelDistance(a: Int, b: Int): Int = maxOf(
        abs(Color.red(a) - Color.red(b)),
        abs(Color.green(a) - Color.green(b)),
        abs(Color.blue(a) - Color.blue(b)),
    )

    private fun meanAbsRgb(a: Bitmap, b: Bitmap): Double {
        val w = min(a.width, b.width); val h = min(a.height, b.height)
        var total = 0.0; var count = 0L
        for (y in 0 until h step 4) for (x in 0 until w step 4) {
            val ca=a.getPixel(x,y); val cb=b.getPixel(x,y)
            total += abs(Color.red(ca)-Color.red(cb)) + abs(Color.green(ca)-Color.green(cb)) + abs(Color.blue(ca)-Color.blue(cb))
            count += 3
        }
        return if (count == 0L) 0.0 else total / (count * 255.0)
    }

    private fun looksBlank(bitmap: Bitmap): Boolean {
        val first = bitmap.getPixel(0, 0)
        var different = 0
        for (y in 0 until bitmap.height step 8) for (x in 0 until bitmap.width step 8) if (bitmap.getPixel(x,y) != first) different++
        return different < 4
    }


    private fun assertBusyCornersUnaffected(bitmap: Bitmap) {
        val patch = min(8, min(bitmap.width, bitmap.height))
        val points = listOf(
            0 to 0,
            bitmap.width - patch to 0,
            0 to bitmap.height - patch,
            bitmap.width - patch to bitmap.height - patch,
        )
        for ((sx, sy) in points) {
            for (y in sy until sy + patch) for (x in sx until sx + patch) {
                val c = bitmap.getPixel(x, y)
                val r = Color.red(c); val g = Color.green(c); val b = Color.blue(c)
                val neutral = abs(r - g) <= 8 && abs(g - b) <= 8
                val checker = r <= 12 || r >= 243
                assertTrue("busy-background corner was altered by the artboard", neutral && checker)
            }
        }
    }

    private fun assertCornersNear(bitmap: Bitmap, expected: Int) {
        val patch = min(8, min(bitmap.width, bitmap.height))
        val points = listOf(0 to 0, bitmap.width-patch to 0, 0 to bitmap.height-patch, bitmap.width-patch to bitmap.height-patch)
        for ((sx,sy) in points) for (y in sy until sy+patch) for (x in sx until sx+patch) {
            val c=bitmap.getPixel(x,y)
            assertTrue("corner not transparent over background",
                abs(Color.red(c)-Color.red(expected))<=12 &&
                abs(Color.green(c)-Color.green(expected))<=12 &&
                abs(Color.blue(c)-Color.blue(expected))<=12)
        }
    }
}
