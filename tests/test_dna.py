import tempfile
import unittest
from pathlib import Path

from grid_dna import DnaError, DnaNotFound, DnaStore


class DnaStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = DnaStore(Path(self.tmp.name) / "dna")

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_list_and_messages(self):
        room = self.store.create_room("Evolution")
        self.assertTrue(room["id"].startswith("dna-"))
        self.assertEqual(room["status"], "idle")
        self.assertEqual(len(self.store.list_rooms()), 1)

        first = self.store.add_message(
            room["id"], "user", "chat", "hello"
        )
        second = self.store.add_message(
            room["id"], "opencode", "answer", "hi"
        )
        self.assertEqual(first["id"], 1)
        self.assertEqual(second["id"], 2)

        loaded, messages = self.store.get_room(room["id"])
        self.assertEqual(loaded["message_count"], 2)
        self.assertEqual([m["content"] for m in messages], ["hello", "hi"])

        _, newer = self.store.get_room(room["id"], after=1)
        self.assertEqual([m["id"] for m in newer], [2])

    def test_proposal_and_status_transitions(self):
        room = self.store.create_room()
        self.store.add_message(
            room["id"], "opencode", "proposal", "add a skill", {"files": 2}
        )
        loaded, _ = self.store.get_room(room["id"])
        self.assertEqual(loaded["status"], "proposed")

        self.store.add_message(
            room["id"], "grid", "verification", "ok", {"ok": True}
        )
        loaded, _ = self.store.get_room(room["id"])
        self.assertEqual(loaded["status"], "verified")

        status = self.store.set_status(room["id"], "adopted", 3)
        self.assertEqual(status["status"], "adopted")
        self.assertEqual(status["generation"], 3)

    def test_validation_and_missing_room(self):
        with self.assertRaises(DnaNotFound):
            self.store.get_room("dna-missing")
        with self.assertRaises(DnaError):
            self.store.add_message("bad id!", "user", "chat", "x")
        room = self.store.create_room()
        with self.assertRaises(DnaError):
            self.store.add_message(room["id"], "nobody", "chat", "x")
        with self.assertRaises(DnaError):
            self.store.add_message(room["id"], "user", "unknown", "x")
        with self.assertRaises(DnaError):
            self.store.add_message(room["id"], "user", "chat", "")


if __name__ == "__main__":
    unittest.main()
