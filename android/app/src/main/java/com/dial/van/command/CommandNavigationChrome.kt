package com.dial.van.command

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Chat
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.MenuBook
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.ShowChart
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationRail
import androidx.compose.material3.NavigationRailItem
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import com.dial.van.command.nav.VanRoute
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.VanPressable

private data class NavDestination(val route: String, val label: String, val icon: androidx.compose.ui.graphics.vector.ImageVector)

private val PRIMARY_DESTINATIONS = listOf(
    NavDestination(VanRoute.HOME, "Home", Icons.Filled.Home),
    NavDestination(VanRoute.ATTENTION, "Attention", Icons.Filled.Notifications),
    NavDestination(VanRoute.WORK, "Work", Icons.Filled.Chat),
    NavDestination(VanRoute.TRADING, "Trading", Icons.Filled.ShowChart),
    NavDestination(VanRoute.MEMORY, "Memory", Icons.Filled.MenuBook),
)

@Composable
internal fun CommandBottomBar(currentRoute: String, onSelect: (String) -> Unit, onMore: () -> Unit) {
    val tokens = LocalVanTokens.current
    NavigationBar(containerColor = tokens.color.surface1) {
        PRIMARY_DESTINATIONS.forEach { destination ->
            NavigationBarItem(
                selected = currentRoute == destination.route,
                onClick = { onSelect(destination.route) },
                icon = { Icon(destination.icon, contentDescription = destination.label) },
                label = { Text(destination.label, style = tokens.type.label) },
            )
        }
        NavigationBarItem(
            selected = currentRoute in VanRoute.MORE,
            onClick = onMore,
            icon = { Icon(Icons.Filled.MoreVert, contentDescription = "More") },
            label = { Text("More", style = tokens.type.label) },
        )
    }
}

@Composable
internal fun CommandSideRail(currentRoute: String, onSelect: (String) -> Unit, onMore: () -> Unit) {
    val tokens = LocalVanTokens.current
    NavigationRail(containerColor = tokens.color.surface1, modifier = Modifier.fillMaxHeight()) {
        PRIMARY_DESTINATIONS.forEach { destination ->
            NavigationRailItem(
                selected = currentRoute == destination.route,
                onClick = { onSelect(destination.route) },
                icon = { Icon(destination.icon, contentDescription = destination.label) },
                label = { Text(destination.label, style = tokens.type.label) },
            )
        }
        NavigationRailItem(
            selected = currentRoute in VanRoute.MORE,
            onClick = onMore,
            icon = { Icon(Icons.Filled.MoreVert, contentDescription = "More") },
            label = { Text("More", style = tokens.type.label) },
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun MoreSheet(onDismiss: () -> Unit, onSelect: (String) -> Unit) {
    val tokens = LocalVanTokens.current
    val sheetState = rememberModalBottomSheetState()
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = tokens.color.surfaceAcrylic,
        contentColor = tokens.color.textPrimary,
    ) {
        Column(modifier = Modifier.fillMaxWidth().padding(horizontal = tokens.space.space5, vertical = tokens.space.space3)) {
            SectionHeader("More")
            listOf(
                Triple(VanRoute.PROJECTS, "Projects", "Health, phase, blockers, next actions"),
                Triple(VanRoute.CONNECTED, "Connected", "Google planes, Hermes, knowledge readiness"),
                Triple(VanRoute.SETTINGS, "Settings & Devices", "Devices, permissions, voice, notifications"),
            ).forEach { (route, title, detail) ->
                VanPressable(
                    onClick = { onSelect(route) },
                    modifier = Modifier.fillMaxWidth().padding(vertical = tokens.space.space2),
                    contentDescription = "$title. $detail.",
                ) {
                    Column(modifier = Modifier.fillMaxWidth()) {
                        Text(title, style = tokens.type.headline, color = tokens.color.textPrimary)
                        Text(detail, style = tokens.type.body, color = tokens.color.textSecondary)
                    }
                }
            }
        }
    }
}

