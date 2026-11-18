import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from commute_agent import storage, worker
from commute_agent.commute import profile_key
from commute_agent.jobs import read_morning_job


class WorkerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)

        self.profile = {"id": "noah", "enabled": True}
        self.now = datetime.fromisoformat(
            "2026-11-19T07:30:00+00:00"
        )
        self.schedule = {
            "commuter_id": "noah",
            "profile_key": profile_key(self.profile),
            "travel_date": "2026-11-19",
            "check_at": "2026-11-19T07:30:00+00:00",
            "first_departure": "2026-11-19T08:00:00+00:00",
            "state": "due",
        }

        patches = {
            "clock": patch.object(worker, "now_for", return_value=self.now),
            "schedule": patch.object(
                worker, "preview_schedule", return_value=self.schedule
            ),
            "check": patch.object(
                worker, "check", return_value={"state": "clear"}
            ),
            "status": patch.object(
                worker, "get_service_status", return_value={"status": "ok"}
            ),
            "agent": patch.object(worker, "run_agent"),
            "profile": patch.object(
                storage, "load_profile", return_value=self.profile
            ),
            "db": patch.object(
                storage, "DB", Path(temporary.name) / "test.db"
            ),
        }

        self.mocks = {}
        for name, patcher in patches.items():
            self.mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)

    def job(self):
        return read_morning_job("noah", "2026-11-19")

    def test_disabled_commuter_does_not_run(self):
        worker.process_commuter(
            {**self.profile, "enabled": False},
            generate=True,
        )

        self.mocks["schedule"].assert_not_called()
        self.mocks["agent"].assert_not_called()

    def test_monitor_only_mode_never_calls_agent(self):
        worker.process_commuter(self.profile, generate=False)

        self.mocks["check"].assert_called_once()
        self.mocks["agent"].assert_not_called()
        self.assertEqual(self.job(), {})

    def test_completed_job_is_not_generated_twice(self):
        worker.process_commuter(self.profile, generate=True)
        worker.process_commuter(self.profile, generate=True)

        self.mocks["agent"].assert_called_once_with(
            "noah",
            mode="scheduled",
            expected_travel_date="2026-11-19",
        )
        self.assertEqual(self.job()["state"], "completed")

    def test_incomplete_service_evidence_retries_before_ai(self):
        self.mocks["status"].return_value = {"status": "partial"}

        worker.process_commuter(self.profile, generate=True)

        self.mocks["agent"].assert_not_called()
        self.assertEqual(self.job()["state"], "retry")

    def test_agent_error_requires_review(self):
        self.mocks["agent"].side_effect = RuntimeError("Test failure")

        worker.process_commuter(self.profile, generate=True)
        worker.process_commuter(self.profile, generate=True)

        self.mocks["agent"].assert_called_once()
        self.assertEqual(self.job()["state"], "review")


if __name__ == "__main__":
    unittest.main()