import sys
import types
import unittest

from grid_context import compress_messages


class HeadroomTests(unittest.TestCase):
    def test_disabled_returns_same_messages(self):
        messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
        self.assertIs(compress_messages(messages, "m", False), messages)

    def test_missing_package_is_safe(self):
        old = sys.modules.pop("headroom", None)
        try:
            messages = [{"role": "user", "content": "hi"}]
            self.assertIs(compress_messages(messages, "m", True), messages)
        finally:
            if old is not None:
                sys.modules["headroom"] = old

    def test_system_messages_are_never_compressed(self):
        fake = types.ModuleType("headroom")

        class Result:
            messages = [{"role": "user", "content": "compressed"}]

        fake.compress = lambda messages, model: Result()
        old = sys.modules.get("headroom")
        sys.modules["headroom"] = fake
        try:
            messages = [
                {"role": "system", "content": "TOOL_SCHEMA"},
                {"role": "user", "content": "long history"},
            ]
            result = compress_messages(messages, "m", True)
            self.assertEqual(result[0], {"role": "system", "content": "TOOL_SCHEMA"})
            self.assertEqual(result[1]["content"], "compressed")
        finally:
            if old is None:
                sys.modules.pop("headroom", None)
            else:
                sys.modules["headroom"] = old

    def test_compression_error_falls_back(self):
        fake = types.ModuleType("headroom")

        def fail(messages, model):
            raise RuntimeError("boom")

        fake.compress = fail
        old = sys.modules.get("headroom")
        sys.modules["headroom"] = fake
        try:
            messages = [{"role": "user", "content": "hi"}]
            self.assertIs(compress_messages(messages, "m", True), messages)
        finally:
            if old is None:
                sys.modules.pop("headroom", None)
            else:
                sys.modules["headroom"] = old


if __name__ == "__main__":
    unittest.main()
