package com.dial.van.browser

import android.content.Context
import android.text.Editable
import android.text.SpannableStringBuilder
import android.util.AttributeSet
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.inputmethod.BaseInputConnection
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputConnection
import org.webrtc.SurfaceViewRenderer

/**
 * Rev 1.5 §§8.4, 8.7 — the remote surface as a real Android view.
 *
 * A `SurfaceViewRenderer` with an `OnTouchListener` bolted on can draw frames and receive
 * taps, and that is where this started. It cannot do the two things a browser needs beyond
 * that:
 *
 *  * **text.** The IME will not open for a view that does not declare itself an editor, so
 *    every text field in the remote page is unreachable — the owner taps it, the caret
 *    appears on the far side, and no keyboard comes up on the phone. `onCheckIsTextEditor`
 *    and `onCreateInputConnection` are what make it an editor;
 *  * **anything that is not a finger.** A mouse wheel, a trackpad, or the S Pen arrive
 *    through `onGenericMotionEvent`, not `onTouchEvent`. Without it, a DeX session or a
 *    connected mouse scrolls nothing at all.
 *
 * The view owns no policy. Whether an event may become an actuation is
 * [BrowserSessionController.mayActuate], asked on every event rather than cached, and the
 * view refuses to hand anything on when it says no.
 */
class BrowserSurfaceView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : SurfaceViewRenderer(context, attrs) {

    /** Set once the controller exists. Null means nothing is connected yet. */
    var controller: BrowserSessionController? = null

    /**
     * §8.4 — composing text is not committed text.
     *
     * The buffer exists so that a composition the owner is still in the middle of ("kon" on
     * the way to "konnichiwa") is sent as a composition and replaced, rather than as three
     * separate commits the remote page then has to un-type. An IME that composes for five
     * keystrokes would otherwise put five wrong words into the page and correct them.
     */
    private val composing: Editable = SpannableStringBuilder()

    override fun onCheckIsTextEditor(): Boolean = true

    override fun onCreateInputConnection(outAttrs: EditorInfo): InputConnection {
        outAttrs.inputType = EditorInfo.TYPE_CLASS_TEXT
        outAttrs.imeOptions = EditorInfo.IME_ACTION_DONE or EditorInfo.IME_FLAG_NO_FULLSCREEN
        return RemoteInputConnection()
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        val active = controller ?: return false
        // Consumed either way. A touch that falls through to whatever is underneath is a
        // touch the owner aimed at the page, delivered somewhere else.
        if (!active.mayActuate()) return true
        active.onTouch(event, width, height)
        return true
    }

    override fun onGenericMotionEvent(event: MotionEvent): Boolean {
        val active = controller ?: return false
        if (event.actionMasked != MotionEvent.ACTION_SCROLL) {
            return super.onGenericMotionEvent(event)
        }
        if (!active.mayActuate()) return true
        active.onScroll(event, width, height)
        return true
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean {
        val active = controller ?: return false
        // Back is the owner leaving, not a key for the page. §8.7 keeps the phone's own
        // navigation working: a browser that swallowed Back would trap the owner in it.
        if (keyCode == KeyEvent.KEYCODE_BACK) return super.onKeyDown(keyCode, event)
        if (!active.mayActuate()) return true
        active.onKey(keyCode, event.unicodeChar, down = true)
        return true
    }

    override fun onKeyUp(keyCode: Int, event: KeyEvent): Boolean {
        val active = controller ?: return false
        if (keyCode == KeyEvent.KEYCODE_BACK) return super.onKeyUp(keyCode, event)
        if (!active.mayActuate()) return true
        active.onKey(keyCode, event.unicodeChar, down = false)
        return true
    }

    private inner class RemoteInputConnection :
        BaseInputConnection(this@BrowserSurfaceView, true) {

        override fun getEditable(): Editable = composing

        override fun setComposingText(text: CharSequence, newCursorPosition: Int): Boolean {
            controller?.takeIf { it.mayActuate() }?.onComposition(text.toString())
            return super.setComposingText(text, newCursorPosition)
        }

        override fun commitText(text: CharSequence, newCursorPosition: Int): Boolean {
            controller?.takeIf { it.mayActuate() }?.onTextCommit(text.toString())
            composing.clear()
            return super.commitText(text, newCursorPosition)
        }

        override fun deleteSurroundingText(beforeLength: Int, afterLength: Int): Boolean {
            // Sent as a key rather than as a text edit: the remote page has its own notion
            // of where the caret is, and a "delete two characters" instruction applied to a
            // field the owner has since moved out of deletes the wrong two.
            val active = controller?.takeIf { it.mayActuate() }
            repeat(beforeLength) {
                active?.onKey(KeyEvent.KEYCODE_DEL, 0, down = true)
                active?.onKey(KeyEvent.KEYCODE_DEL, 0, down = false)
            }
            return super.deleteSurroundingText(beforeLength, afterLength)
        }

        override fun sendKeyEvent(event: KeyEvent): Boolean {
            val active = controller?.takeIf { it.mayActuate() }
            when (event.action) {
                KeyEvent.ACTION_DOWN -> active?.onKey(event.keyCode, event.unicodeChar, true)
                KeyEvent.ACTION_UP -> active?.onKey(event.keyCode, event.unicodeChar, false)
            }
            return super.sendKeyEvent(event)
        }
    }
}
