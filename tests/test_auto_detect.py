import unittest

from grid_agent import GridOrchestrator, Tools, strip_markdown


class FakeBackend:
    type = "ollama"
    model = "test-model"

    def chat(self, messages, temperature=0.3):
        return "summary"


class AutoDetectTests(unittest.TestCase):
    def setUp(self):
        self.orch = GridOrchestrator(FakeBackend(), None)

    def assert_call(self, text, tool, tool_input):
        result = self.orch._auto_detect_tool(text, "")
        self.assertIsNotNone(result, text)
        self.assertEqual(result[0], tool, text)
        self.assertEqual(result[1], tool_input, text)

    def test_ping_extracts_only_the_host(self):
        self.assert_call("Ping 8.8.8.8 and tell me the result.", "ping", "8.8.8.8")

    def test_dns_lookup_skips_for_and_punctuation(self):
        self.assert_call(
            "Do a DNS lookup for example.com.", "dns_lookup", "example.com"
        )

    def test_weather_strips_time_filler(self):
        self.assert_call(
            "What is the weather in Kathmandu right now?",
            "weather",
            "Kathmandu",
        )

    def test_capability_question_is_not_a_tool_call(self):
        self.assertIsNone(
            self.orch._auto_detect_tool(
                "What radio and satellite tools do you have?", ""
            )
        )

    def test_web_search_drops_summarize_instruction(self):
        self.assert_call(
            "Search the web for the latest Ollama release and summarize it in two sentences.",
            "web_search",
            "the latest Ollama release",
        )

    def test_satellite_tools_routes_to_help(self):
        self.assert_call("satellite tools", "satellite", "help")

    def test_social_history_routes_to_social(self):
        self.assert_call("show me my social history", "social", "history")
        self.assert_call("review full history of social activities", "social", "history")
        self.assert_call("search social history", "social", "history")

    def test_social_input_strips_tool_name(self):
        self.assertEqual(
            self.orch._clean_tool_input("social", "social history"),
            "history",
        )
        self.assertEqual(
            self.orch._clean_tool_input("social", "social persona set Tina"),
            "persona set Tina",
        )

    def test_parse_tool_call_accepts_inline_argument(self):
        self.assertEqual(
            Tools.parse_tool_call("TOOL_CALL: social history\nINPUT: (ignored)"),
            ("social", "history"),
        )
        self.assertEqual(
            Tools.parse_tool_call("TOOL_CALL: social\nINPUT: social history"),
            ("social", "social history"),
        )

    def test_strip_markdown_for_plain_clients(self):
        clean = strip_markdown(
            "**Projects & Setup:**\n"
            "*   Item one\n"
            "*   Item two\n"
            "### Heading\n"
            "`code`\n"
            "_Durable facts_"
        )
        self.assertNotIn("**", clean)
        self.assertNotIn("*   ", clean)
        self.assertNotIn("###", clean)
        self.assertNotIn("`", clean)
        self.assertNotIn("_Durable", clean)
        self.assertIn("Projects & Setup:", clean)
        self.assertIn("- Item one", clean)
        self.assertIn("Heading", clean)
        self.assertIn("code", clean)
        self.assertIn("Durable facts", clean)

    def test_synthesis_intent(self):
        self.assertTrue(
            self.orch._wants_synthesis(
                "Search the web for the latest Ollama release and summarize it."
            )
        )
        self.assertTrue(
            self.orch._wants_synthesis("Ping 8.8.8.8 and tell me the result.")
        )
        self.assertFalse(self.orch._wants_synthesis("Show me my system info."))

    def test_parse_tool_call_accepts_hyphenated_skill_names(self):
        self.assertEqual(
            Tools.parse_tool_call("TOOL_CALL: daily-brief INPUT: (ignored)"),
            ("daily-brief", "(ignored)"),
        )


if __name__ == "__main__":
    unittest.main()
