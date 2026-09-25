package com.dial.van.onboarding

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.os.Bundle
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.unit.dp
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.dial.van.design.LocalVanTokens
import com.dial.van.visual.VanAvatar
import com.dial.van.visual.VanDurableState
import com.dial.van.visual.VanPresentation
import com.dial.van.visual.VanTheme
import com.dial.van.visual.VanVisualState

/**
 * VAN asking for one permission, in his own words, on his own screen.
 *
 * Opened only when a feature needs the permission (owner direction, 2026-09-25): no
 * checklist. It finishes `RESULT_OK` once the device reports the grant — re-read on every
 * resume, because Android grants several of these on its own settings pages — and
 * `RESULT_CANCELED` on "not now", which is remembered so VAN does not ask again unprompted.
 */
class VanAskActivity : FragmentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val permission = VanPermission.fromId(intent.getStringExtra(EXTRA_PERMISSION)) ?: run {
            finish()
            return
        }
        if (VanAsks.isGranted(this, permission)) {
            setResult(Activity.RESULT_OK)
            finish()
            return
        }
        setContent {
            VanTheme(dark = true) {
                VanAskScreen(
                    ask = VanAskPlan.ask(permission),
                    isGranted = { VanAsks.isGranted(this, permission) },
                    settingsIntent = VanAsks.settingsIntent(this, permission),
                    runtimePermission = VanAsks.runtimePermission(permission),
                    onGranted = {
                        setResult(Activity.RESULT_OK)
                        finish()
                    },
                    onLater = {
                        VanAsks.markDeclined(this, permission)
                        setResult(Activity.RESULT_CANCELED)
                        finish()
                    },
                )
            }
        }
    }

    companion object {
        const val EXTRA_PERMISSION = "van_permission"

        fun intent(context: Context, permission: VanPermission): Intent =
            Intent(context, VanAskActivity::class.java).putExtra(EXTRA_PERMISSION, permission.id)
    }
}

@Composable
private fun VanAskScreen(
    ask: VanAsk,
    isGranted: () -> Boolean,
    settingsIntent: Intent?,
    runtimePermission: String?,
    onGranted: () -> Unit,
    onLater: () -> Unit,
) {
    val tokens = LocalVanTokens.current
    val context = LocalContext.current
    // A grant made on a settings page is noticed when the owner comes back.
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME && isGranted()) onGranted()
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }
    val prompt = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        // Android's own "Don't allow" is the owner's answer; VAN takes it as a "not now".
        if (granted || isGranted()) onGranted() else onLater()
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(tokens.color.bgCanvas),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 28.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            VanAvatar(
                state = VanVisualState(durableState = VanDurableState.ATTENTIVE, speaking = true),
                modifier = Modifier.size(280.dp),
                presentation = VanPresentation.EXPANDED,
            )
            // VAN's speech: a bubble, not a card of instructions.
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(tokens.color.surface1, RoundedCornerShape(20.dp))
                    .padding(horizontal = 20.dp, vertical = 16.dp),
            ) {
                Text(ask.line, style = tokens.type.body, color = tokens.color.textPrimary)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                TextButton(onClick = onLater) { Text(ask.later, color = tokens.color.textSecondary) }
                Button(onClick = {
                    when {
                        runtimePermission != null -> prompt.launch(runtimePermission)
                        settingsIntent != null -> context.startActivity(settingsIntent)
                        else -> if (isGranted()) onGranted()
                    }
                }) { Text(ask.allow) }
            }
        }
    }
}
