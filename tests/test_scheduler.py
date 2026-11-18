import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from commute_agent.commute import profile_key
from commute_agent.scheduler import schedule_from_plan


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.zone = ZoneInfo("Europe/London")
        self.profile = {
            "id": "noah",
            "name": "Noah",
            "timezone": "Europe/London",
            "travel_days": ["wednesday"],
            "time_window": {
                "type": "arrival",
                "start": "08:50",
                "end": "09:10",
            },
            "advance_warning_minutes": 30,
            "enabled": False,
        }
        self.plan = {
            "key": profile_key(self.profile),
            "date": "2026-11-18",
            # Deliberately place the later departure first.
            "journeys": [
                {"startDateTime": "2026-11-18T08:12:00"},
                {"startDateTime": "2026-11-18T08:00:00"},
            ],
        }

    def at(self, clock):
        return datetime.fromisoformat(
            f"2026-11-18T{clock}"
        ).replace(tzinfo=self.zone)

    def test_warning_uses_earliest_departure(self):
        result = schedule_from_plan(
            self.profile, self.at("07:00"), self.plan
        )

        self.assertEqual(
            result["check_at"],
            "2026-11-18T07:30:00+00:00",
        )
        self.assertEqual(result["state"], "waiting")
        self.assertFalse(result["enabled"])

    def test_due_at_warning_time(self):
        result = schedule_from_plan(
            self.profile, self.at("07:30"), self.plan
        )

        self.assertEqual(result["state"], "due")

    def test_window_closes_at_first_departure(self):
        result = schedule_from_plan(
            self.profile, self.at("08:00"), self.plan
        )

        self.assertEqual(result["state"], "departure_passed")

    def test_old_travel_date_is_rejected(self):
        self.plan["date"] = "2026-11-11"

        with self.assertRaises(ValueError):
            schedule_from_plan(
                self.profile, self.at("07:00"), self.plan
            )


if __name__ == "__main__":
    unittest.main()