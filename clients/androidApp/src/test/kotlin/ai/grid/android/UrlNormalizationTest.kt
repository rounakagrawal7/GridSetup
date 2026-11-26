package ai.grid.android

import kotlin.test.Test
import kotlin.test.assertEquals

class UrlNormalizationTest {
    @Test
    fun trimsWhitespaceAndTrailingSlash() {
        assertEquals(
            "http://192.168.1.73:8771",
            normalizeBaseUrl("  http://192.168.1.73:8771/  "),
        )
    }

    @Test
    fun addsMissingScheme() {
        assertEquals("http://192.168.1.73:8771", normalizeBaseUrl("192.168.1.73:8771"))
    }

    @Test
    fun keepsOnlyTheLastPastedScheme() {
        assertEquals(
            "http://192.168.1.73:8771",
            normalizeBaseUrl("http://10.0.2.2:8771http://192.168.1.73:8771"),
        )
        assertEquals(
            "http://192.168.1.73:8771",
            normalizeBaseUrl("/http://192.168.1.73:8771"),
        )
    }

    @Test
    fun preservesHttps() {
        assertEquals("https://grid.example", normalizeBaseUrl(" https://grid.example/ "))
    }

    @Test
    fun tokenStripsWhitespaceAndQuotes() {
        assertEquals("abcdef", normalizeToken("  \"abcdef\"  "))
        assertEquals("abcdef", normalizeToken("'ab cd ef'"))
        assertEquals("abcdef", normalizeToken("ab\ncd\ref"))
    }
}
