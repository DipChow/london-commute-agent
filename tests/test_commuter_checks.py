"""Verify commute functions use the selected person's storage."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from commute_agent import commute, storage


class CommuterCheckTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database_patch = patch.object(
            storage,
            "DB",
            Path(self.temporary.name) / "test.db",
        )
        self.database_patch.start()

        self.now = datetime(
            2026, 11, 18, 8, 0,
            tzinfo=ZoneInfo("Europe/London"),
        )

        self.profile = {
            "id": "alex",
            "timezone": "Europe/London",
            "travel_days": ["wednesday"],
            "time_window": {
                "type": "arrival",
                "start": "08:50",
                "end": "09:10",
            },
            "rail_line_ids": ["bakerloo"],
        }

        self.plan = {
            "date": "2026-11-18",
            "key": commute.profile_key(self.profile),
            "check_from": "2026-11-18T07:30:00+00:00",
            "journeys": [{"legs": []}],
        }

        self.discovery = {
            "candidates": [],
            "failures": [],
        }

    def tearDown(self):
        self.database_patch.stop()
        self.temporary.cleanup()

    def test_baseline_is_saved_for_selected_commuter(self):
        with (
            patch.object(
                commute, "get_plan", return_value=self.plan
            ),
            patch.object(
                commute, "discover", return_value=self.discovery
            ),
        ):
            commute.baseline(self.profile, self.now)

        self.assertIsNone(storage.read("baseline"))

        alex_baseline = storage.read(
            "baseline", commuter_id="alex"
        )
        self.assertEqual(
            alex_baseline["key"],
            commute.profile_key(self.profile),
        )

    def test_check_does_not_overwrite_tims_snapshot(self):
        storage.write("snapshot", {"owner": "tim"})

        storage.write(
            "baseline",
            {**self.plan, "discovery": self.discovery},
            commuter_id="alex",
        )
        storage.write(
            "daily_plan",
            self.plan,
            commuter_id="alex",
        )

        good_service = [
            {
                "id": "bakerloo",
                "lineStatuses": [
                    {"statusSeverityDescription": "Good Service"}
                ],
            }
        ]

        with patch.object(
            commute.api,
            "get_line_status",
            return_value=good_service,
        ):
            commute.check(
                self.profile, self.now, manual=True
            )

        self.assertEqual(
            storage.read("snapshot"),
            {"owner": "tim"},
        )
        self.assertEqual(
            storage.read("snapshot", commuter_id="alex")["state"],
            "clear",
        )


if __name__ == "__main__":
    unittest.main()