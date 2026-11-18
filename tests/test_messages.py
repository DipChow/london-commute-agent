"""Test formatting and saved-message separation without API calls."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from commute_agent import storage
from commute_agent.messages import (
    format_commute_message,
    save_commute_message,
)


class MessageTests(unittest.TestCase):
    def test_message_uses_source_times(self):
        journey = {
            "leave_home": "2026-11-19T08:03:00+00:00",
            "reach_destination": "2026-11-19T08:52:00+00:00",
            "duration_minutes": 49,
            "legs": [
                {
                    "mode": "walking",
                    "instruction": "Walk from home",
                },
                {
                    "mode": "bus",
                    "instruction": "172 bus to Elephant & Castle",
                },
            ],
        }

        message = format_commute_message(
            "No disruptions are currently reported.",
            [journey],
            "2026-11-19",
        )

        self.assertIn("Thursday 19 November", message)
        self.assertIn("Leave home 08:03", message)
        self.assertIn("arrive 08:52", message)
        self.assertIn("172 bus", message)
        self.assertNotIn("Walk from home", message)

    def test_saving_message_does_not_overwrite_another_commuter(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "test.db"

            with patch.object(storage, "DB", database):
                for person in ["tim", "noah"]:
                    save_commute_message(
                        {
                            "commuter_id": person,
                            "generated_at": "2026-11-19T07:30:00+00:00",
                            "message": f"Message for {person}",
                        }
                    )

                self.assertEqual(
                    storage.read(
                        "agent_message", commuter_id="tim"
                    )["message"],
                    "Message for tim",
                )
                self.assertEqual(
                    storage.read(
                        "agent_message", commuter_id="noah"
                    )["message"],
                    "Message for noah",
                )

                history = storage.events(None)
                self.assertEqual(len(history), 2)


if __name__ == "__main__":
    unittest.main()