package com.dial.van.command

import android.os.Bundle
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.viewmodel.compose.viewModel
import com.dial.van.VanApplication
import com.dial.van.command.modules.ActivityModule
import com.dial.van.command.modules.BrowserAutomationModule
import com.dial.van.command.modules.BrowserEscalationsPage
import com.dial.van.command.modules.BrowserPolicyPage
import com.dial.van.command.modules.BrowserSessionsPage
import com.dial.van.command.modules.BrowserTasksPage
import com.dial.van.command.modules.ChatModule
import com.dial.van.command.modules.ConnectionsModule
import com.dial.van.command.modules.DecisionsModule
import com.dial.van.command.modules.OverviewModule
import com.dial.van.command.modules.ProjectsModule
import com.dial.van.command.modules.SettingsModule
import com.dial.van.command.modules.SystemsModule
import com.dial.van.command.modules.TasksModule
import com.dial.van.visual.VanGlassTokens
import com.dial.van.visual.VanLiveVisualState
import com.dial.van.visual.VanPresence
import com.dial.van.visual.VanTheme
import com.dial.van.visual.rememberVanEffectBudget

/**
 * The Command Centre shell: the Activity, the theme, and navigation between modules.
 *
 * P3-AND-009 — what is left here is what an Activity is for. The modules live in
 * `command/modules/` and the pieces they draw with in `CommandCentreComponents.kt`.
 */

class CommandCentreActivity : FragmentActivity() {
    @OptIn(ExperimentalMaterial3Api::class)
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val app = application as VanApplication
        val initial = CommandModule.fromId(intent.getStringExtra(EXTRA_MODULE))

        setContent {
            // P3-AND-008 — one theme, following the owner's system setting, instead of a
            // `darkColorScheme` built inline here and again in two other activities.
            VanTheme {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(MaterialTheme.colorScheme.background),
                ) {
                    Scaffold(
                        containerColor = Color.Transparent,
                        topBar = {
                            TopAppBar(
                                title = { Text("Van Command Centre") },
                                colors = TopAppBarDefaults.topAppBarColors(
                                    containerColor = Color.Transparent,
                                    titleContentColor = MaterialTheme.colorScheme.onBackground,
                                ),
                            )
                        },
                    ) { padding ->
                        CommandCentreScreen(padding, app, initial)
                    }
                }
            }
        }
    }

    companion object {
        const val EXTRA_MODULE = "module"
    }
}

@Composable
internal fun CommandCentreScreen(
    padding: PaddingValues,
    app: VanApplication,
    initial: CommandModule,
) {
    // P3-AND-007 — was `remember { mutableStateOf(initial) }`, so a rotation or an
    // overnight process death put the owner back on Home.
    val model: CommandCentreViewModel = viewModel()
    LaunchedEffect(initial) { model.start(initial) }
    val selected by model.selected.collectAsState()
    val degraded by app.degradedModeStore.state.collectAsState()
    val live = VanLiveVisualState.frame
    val cue = VanPresence.cue(degraded, live = live)
    val budget = rememberVanEffectBudget()
    val glass = VanGlassTokens.forState(
        state = cue.durableState,
        panel = true,
        liveBlurAvailable = false,
        budget = budget,
    )

    fun navigate(module: CommandModule) = model.navigate(module)

    BackHandler(enabled = CommandNav.handlesBack(selected)) { model.back() }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(padding),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            CommandNav.PRIMARY.forEach { module ->
                val isSelected = selected == module
                Button(
                    onClick = { navigate(module) },
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (isSelected) {
                            MaterialTheme.colorScheme.primary.copy(alpha = 0.24f)
                        } else {
                            MaterialTheme.colorScheme.surfaceVariant
                        },
                        contentColor = if (isSelected) {
                            MaterialTheme.colorScheme.primary
                        } else {
                            MaterialTheme.colorScheme.onSurfaceVariant
                        },
                    ),
                    shape = RoundedCornerShape(10.dp),
                    contentPadding = PaddingValues(horizontal = 5.dp, vertical = 5.dp),
                ) {
                    Text(module.title, fontSize = 10.sp, maxLines = 1)
                }
            }
        }

        when (selected) {
            CommandModule.OVERVIEW -> OverviewModule(app, glass, ::navigate)
            CommandModule.CHAT -> ChatModule(app, glass)
            CommandModule.DECISIONS -> DecisionsModule(app, glass)
            CommandModule.TASKS -> TasksModule(app, glass) { navigate(CommandModule.CHAT) }
            CommandModule.PROJECTS -> ProjectsModule(app, glass) { projectId ->
                app.commandController.selectProject(projectId)
                navigate(CommandModule.CHAT)
            }
            CommandModule.ACTIVITY -> ActivityModule(app, glass)
            CommandModule.BROWSER_AUTOMATION -> BrowserAutomationModule(app, glass, ::navigate)
            CommandModule.BROWSER_TASKS -> BrowserTasksPage(app, glass) { navigate(CommandModule.BROWSER_AUTOMATION) }
            CommandModule.BROWSER_ESCALATIONS -> BrowserEscalationsPage(app, glass) { navigate(CommandModule.BROWSER_AUTOMATION) }
            CommandModule.BROWSER_SESSIONS -> BrowserSessionsPage(app, glass) { navigate(CommandModule.BROWSER_AUTOMATION) }
            CommandModule.BROWSER_POLICY -> BrowserPolicyPage(app, glass) { navigate(CommandModule.BROWSER_AUTOMATION) }
            CommandModule.SYSTEMS -> SystemsModule(app, glass)
            CommandModule.CONNECTIONS -> ConnectionsModule(app, glass)
            CommandModule.SETTINGS -> SettingsModule(app, glass)
        }
    }
}
