"""Check commuter separation using a temporary database."""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from commute_agent import storage


class CommuterStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "test.db"

        self.database_patch = patch.object(
            storage, "DB", self.database
        )
        self.database_patch.start()

    def tearDown(self):
        self.database_patch.stop()
        self.temporary.cleanup()

    def test_records_are_separate(self):
        storage.write("baseline", {"owner": "tim"})
        storage.write(
            "baseline",
            {"owner": "alex"},
            commuter_id="alex",
        )

        self.assertEqual(
            storage.read("baseline"),
            {"owner": "tim"},
        )
        self.assertEqual(
            storage.read("baseline", commuter_id="alex"),
            {"owner": "alex"},
        )

    def test_missing_record_does_not_return_another_persons_data(self):
        storage.write("snapshot", {"state": "clear"})

        self.assertIsNone(
            storage.read("snapshot", commuter_id="alex")
        )

    def test_history_can_be_filtered_or_combined(self):
        storage.event("2026-11-18T07:30:00+00:00", {"message": "Tim"})
        storage.event(
            "2026-11-18T08:00:00+00:00",
            {"message": "Alex"},
            commuter_id="alex",
        )

        self.assertEqual(len(storage.events()), 1)
        self.assertEqual(len(storage.events("alex")), 1)
        self.assertEqual(len(storage.events(None)), 2)

    def test_original_history_is_preserved(self):
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "CREATE TABLE events "
                "(id INTEGER PRIMARY KEY, at TEXT, body TEXT)"
            )
            connection.execute(
                "INSERT INTO events (at, body) VALUES (?, ?)",
                ("2026-11-17T08:00:00+00:00", '{"message": "Original"}'),
            )

        history = storage.events()

        self.assertEqual(history[0]["message"], "Original")
        self.assertEqual(history[0]["commuter_id"], "tim")


if __name__ == "__main__":
    unittest.main()