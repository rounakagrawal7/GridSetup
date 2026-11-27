import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from text_stats import run


class TextStatsTest(unittest.TestCase):
    def test_counts_words_and_characters(self):
        stats = json.loads(run("Hello world!\nSecond line."))
        self.assertEqual(
            stats,
            {
                "characters": 25,
                "characters_no_whitespace": 22,
                "lines": 2,
                "unique_words": 4,
                "words": 4,
            },
        )

    def test_empty_input_is_all_zero(self):
        self.assertEqual(
            json.loads(run("")),
            {
                "characters": 0,
                "characters_no_whitespace": 0,
                "lines": 0,
                "unique_words": 0,
                "words": 0,
            },
        )

    def test_words_are_case_insensitive_and_keep_apostrophes(self):
        stats = json.loads(run("Don't stop; don't stop."))
        self.assertEqual(stats["words"], 4)
        self.assertEqual(stats["unique_words"], 2)
        self.assertEqual(stats["characters"], 23)
        self.assertEqual(stats["characters_no_whitespace"], 20)

    def test_non_string_input_is_rejected(self):
        with self.assertRaises(TypeError):
            run(None)


if __name__ == "__main__":
    unittest.main()
