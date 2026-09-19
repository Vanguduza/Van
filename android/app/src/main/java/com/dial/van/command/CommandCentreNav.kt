package com.dial.van.command

/**
 * Where "back" goes, and what survives a rotation.
 *
 * P3-AND-007 — there was no state restoration anywhere in the app: every screen held its
 * state in `remember`, so rotating the phone, changing the font size, or having Android
 * reclaim the process while the owner was reading a notification dropped them back on the
 * home module with their typed text gone. On a floating assistant that is meant to stay
 * resident, process death is not an edge case; it is what happens overnight.
 *
 * The navigation model is pure so it can be executed in `android/verification` rather than
 * rotated by hand: the back stack is the part that is easy to get wrong, and a back button
 * that leaves the owner somewhere they did not come from is the defect nobody reports.
 */
internal object CommandNav {

    /** The modules that get a top-level button. */
    val PRIMARY: List<CommandModule> = listOf(
        CommandModule.OVERVIEW,
        CommandModule.CHAT,
        CommandModule.TASKS,
        CommandModule.ACTIVITY,
    )

    /** The browser pages, which are children of the automation module rather than of home. */
    val BROWSER_CHILDREN: Set<CommandModule> = setOf(
        CommandModule.BROWSER_TASKS,
        CommandModule.BROWSER_ESCALATIONS,
        CommandModule.BROWSER_SESSIONS,
        CommandModule.BROWSER_POLICY,
    )

    /**
     * Where back goes from [module], or null when back should leave the Command Centre.
     *
     * One level, not a history: a back stack that remembers the route the owner took is a
     * back stack that can send them somewhere they cannot get out of.
     */
    fun back(module: CommandModule): CommandModule? = when (module) {
        CommandModule.OVERVIEW -> null
        in BROWSER_CHILDREN -> CommandModule.BROWSER_AUTOMATION
        else -> CommandModule.OVERVIEW
    }

    fun handlesBack(module: CommandModule): Boolean = back(module) != null

    /** What is written into saved state. An id, never an ordinal. */
    fun save(module: CommandModule): String = module.id

    /**
     * What comes back.
     *
     * Ordinals would restore the wrong screen the first time a module is inserted into the
     * enum, and it would do so silently, to an owner who had been on that screen when
     * Android killed the process — which is precisely when they least expect to be moved.
     */
    fun restore(id: String?): CommandModule = CommandModule.fromId(id)
}
