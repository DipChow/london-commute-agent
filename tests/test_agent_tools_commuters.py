"""Verify AI tools read evidence for the selected commuter."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from commute_agent import agent_tools, commute, storage


class AgentToolCommuterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()

        self.database_patch = patch.object(
            storage,
            "DB",
            Path(self.temporary.name) / "test.db",
        )
        self.database_patch.start()

        self.profiles = {
            person: {
                "id": person,
                "timezone": "Europe/London",
                "travel_days": commute.DAYS,
                "time_window": {
                    "type": "arrival",
                    "start": "08:50",
                    "end": "09:10",
                },
            }
            for person in ["tim", "alex"]
        }

        self.profile_patch = patch.object(
            storage,
            "load_profile",
            side_effect=lambda commuter_id="tim": (
                self.profiles[commuter_id]
            ),
        )
        self.profile_patch.start()

    def tearDown(self):
        self.profile_patch.stop()
        self.database_patch.stop()
        self.temporary.cleanup()

    def test_saved_routes_belong_to_selected_commuter(self):
        for person, bus in [("tim", "453"), ("alex", "172")]:
            storage.write(
                "baseline",
                {
                    "key": commute.profile_key(self.profiles[person]),
                    "journeys": [],
                    "discovery": {
                        "candidates": [{"line": bus}],
                        "failures": [],
                    },
                },
                commuter_id=person,
            )

        result = agent_tools.get_saved_routes("alex")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["commuter_id"], "alex")
        self.assertEqual(result["candidate_bus_ids"], ["172"])

    def test_missing_status_does_not_use_tims_snapshot(self):
        storage.write(
            "snapshot",
            {
                "profile_key": commute.profile_key(
                    self.profiles["tim"]
                ),
                "state": "clear",
            },
            commuter_id="tim",
        )

        result = agent_tools.get_service_status("alex")

        self.assertEqual(result["status"], "unavailable")

    def test_journey_tool_passes_selected_profile_to_planner(self):
        with patch.object(
            agent_tools,
            "get_plan",
            return_value={"journeys": []},
        ) as planner:
            result = agent_tools.get_journey_options("alex")

        supplied_profile = planner.call_args.args[0]

        self.assertEqual(supplied_profile["id"], "alex")
        self.assertEqual(result["status"], "no_options")


if __name__ == "__main__":
    unittest.main()