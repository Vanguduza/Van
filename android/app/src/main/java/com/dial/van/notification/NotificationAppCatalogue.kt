package com.dial.van.notification

enum class AppNotificationPolicy {
    NORMAL,
    PRIORITY,
    MUTE,
}

/** Notification sources are discoverable without making a policy decision for the owner. */
object NotificationAppCatalogue {
    fun merge(
        observedPackages: Set<String>,
        explicitPolicies: Map<String, AppNotificationPolicy>,
    ): Map<String, AppNotificationPolicy> =
        (observedPackages + explicitPolicies.keys).filter { it.isNotBlank() }.associateWith {
            explicitPolicies[it] ?: AppNotificationPolicy.NORMAL
        }
}
