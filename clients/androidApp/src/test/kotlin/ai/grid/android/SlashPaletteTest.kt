package ai.grid.android

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class SlashPaletteTest {
    private val toolCommands = listOf(
        SlashCommand(
            name = "/rea",
            description = "Authorized teardown",
            template = "/rea ",
            subcommands = listOf(
                SlashSubcommand("authorized", "One-off authorization", "authorized "),
                SlashSubcommand("authorize", "Add a host", "authorize "),
                SlashSubcommand("revoke", "Remove a host", "revoke "),
                SlashSubcommand("list", "List authorized hosts"),
                SlashSubcommand("status", "Show REA status"),
                SlashSubcommand("help", "Show REA help"),
            ),
        ),
        SlashCommand("/satellite", "Satellite tracking", template = "/satellite "),
        SlashCommand("/read_file", "Read a file", template = "/read_file "),
    )

    private fun palette(input: String): SlashPalette? =
        buildSlashPalette(input, mergeSlashCommands(APP_COMMANDS, toolCommands))

    @Test
    fun plainTextHasNoPalette() {
        assertNull(palette("hello"))
        assertNull(palette(""))
    }

    @Test
    fun slashFiltersCommands() {
        val result = assertNotNull(palette("/re"))
        assertTrue(result.header.startsWith("COMMANDS"))
        assertEquals(listOf("/rea", "/read_file", "/ref"), result.suggestions.map { it.label })
    }

    @Test
    fun commandWithSubcommandsAppliesTrailingSpace() {
        val result = assertNotNull(palette("/rea"))
        val rea = result.suggestions.first { it.label == "/rea" }
        assertEquals("/rea ", rea.applyText)
    }

    @Test
    fun subcommandsAreFilteredAndTemplated() {
        val result = assertNotNull(palette("/rea "))
        assertEquals("SUBCOMMANDS · /rea · 6", result.header)
        val authorized = result.suggestions.first { it.label == "authorized" }
        assertEquals("/rea authorized ", authorized.applyText)
    }

    @Test
    fun subcommandFilterNarrowsResults() {
        val result = assertNotNull(palette("/rea rev"))
        assertEquals(listOf("revoke"), result.suggestions.map { it.label })
        assertEquals("/rea revoke ", result.suggestions.single().applyText)
    }

    @Test
    fun argsAfterSubcommandHideThePalette() {
        assertNull(palette("/rea authorized https://example.com"))
        assertNull(palette("/memory status extra"))
    }

    @Test
    fun appSubcommandsSurviveMerge() {
        val result = assertNotNull(palette("/memory "))
        assertEquals("SUBCOMMANDS · /memory · 7", result.header)
        val add = result.suggestions.first { it.label == "add" }
        assertEquals("/memory add ", add.applyText)
    }

    @Test
    fun serverSubcommandsFillAppCommandsWithoutTheirs() {
        val result = assertNotNull(palette("/rea "))
        assertTrue(result.suggestions.any { it.label == "authorized" })
    }

    @Test
    fun mergingDeduplicatesToolNames() {
        val merged = mergeSlashCommands(APP_COMMANDS, toolCommands)
        assertEquals(merged.size, merged.map { it.name.lowercase() }.distinct().size)
        val rea = merged.first { it.name == "/rea" }
        assertEquals("Authorized passive teardown: /rea authorized <url>", rea.description)
        assertEquals(6, rea.subcommands.size)
    }
}
