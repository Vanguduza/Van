package com.dial.van.notification

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse

class NotificationAppCatalogueTest {
    @Test
    fun arrivingAppIsVisibleWithoutAnExplicitDecision() {
        val apps = NotificationAppCatalogue.merge(setOf("org.example.chat"), emptyMap())
        assertEquals(AppNotificationPolicy.NORMAL, apps["org.example.chat"])
    }

    @Test
    fun observationsPreserveMutePriorityAndPreconfiguredApps() {
        val apps = NotificationAppCatalogue.merge(
            setOf("org.example.muted", "org.example.priority", ""),
            mapOf(
                "org.example.muted" to AppNotificationPolicy.MUTE,
                "org.example.priority" to AppNotificationPolicy.PRIORITY,
                "org.example.notSeen" to AppNotificationPolicy.MUTE,
            ),
        )
        assertEquals(AppNotificationPolicy.MUTE, apps["org.example.muted"])
        assertEquals(AppNotificationPolicy.PRIORITY, apps["org.example.priority"])
        assertEquals(AppNotificationPolicy.MUTE, apps["org.example.notSeen"])
        assertFalse(apps.containsKey(""))
    }
}
