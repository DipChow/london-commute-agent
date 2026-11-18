import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from commute_agent import storage
from commute_agent.commute import profile_key
from commute_agent.jobs import (
    claim_morning_job,
    finish_morning_job,
    read_morning_job,
)


class MorningJobTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)

        patcher = patch.object(
            storage,
            "DB",
            Path(self.temporary.name) / "test.db",
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        self.now = datetime.fromisoformat(
            "2026-11-19T07:30:00+00:00"
        )
        self.profile = {
            "id": "noah",
            "enabled": True,
        }
        self.schedule = self.schedule_for(self.profile)

    def schedule_for(self, profile):
        return {
            "commuter_id": profile["id"],
            "profile_key": profile_key(profile),
            "travel_date": "2026-11-19",
            "check_at": "2026-11-19T07:30:00+00:00",
            "first_departure": "2026-11-19T08:00:00+00:00",
        }

    def finish(self, job, outcome, now=None):
        return finish_morning_job(
            "noah",
            "2026-11-19",
            job["claim_token"],
            outcome,
            now or self.now,
        )

    def test_running_job_cannot_be_claimed_again(self):
        first = claim_morning_job(
            self.profile, self.schedule, self.now
        )
        second = claim_morning_job(
            self.profile, self.schedule, self.now
        )

        self.assertIsNotNone(first)
        self.assertIsNone(second)

    def test_completed_job_stays_completed(self):
        job = claim_morning_job(
            self.profile, self.schedule, self.now
        )
        self.finish(job, "completed")

        self.assertIsNone(
            claim_morning_job(
                self.profile, self.schedule, self.now
            )
        )
        self.assertEqual(
            read_morning_job("noah", "2026-11-19")["state"],
            "completed",
        )

    def test_commuters_have_separate_jobs(self):
        other = {"id": "lottie", "enabled": True}

        noah = claim_morning_job(
            self.profile, self.schedule, self.now
        )
        lottie = claim_morning_job(
            other, self.schedule_for(other), self.now
        )

        self.assertIsNotNone(noah)
        self.assertIsNotNone(lottie)

    def test_retry_waits_and_stops_after_three_attempts(self):
        for attempt in range(1, 4):
            current = self.now + timedelta(
                minutes=2 * (attempt - 1)
            )
            job = claim_morning_job(
                self.profile, self.schedule, current
            )
            self.assertEqual(job["attempts"], attempt)

            result = self.finish(job, "retry", current)

            self.assertIsNone(
                claim_morning_job(
                    self.profile,
                    self.schedule,
                    current + timedelta(seconds=30),
                )
            )

        self.assertEqual(result["state"], "failed")
        self.assertIsNone(
            claim_morning_job(
                self.profile,
                self.schedule,
                self.now + timedelta(minutes=10),
            )
        )

    def test_wrong_claim_cannot_finish_job(self):
        claim_morning_job(
            self.profile, self.schedule, self.now
        )

        with self.assertRaises(ValueError):
            finish_morning_job(
                "noah",
                "2026-11-19",
                "wrong-token",
                "completed",
                self.now,
            )

    def test_disabled_or_departed_job_cannot_start(self):
        disabled = {**self.profile, "enabled": False}

        self.assertIsNone(
            claim_morning_job(
                disabled,
                self.schedule_for(disabled),
                self.now,
            )
        )
        self.assertIsNone(
            claim_morning_job(
                self.profile,
                self.schedule,
                self.now + timedelta(minutes=30),
            )
        )

    def test_concurrent_workers_only_get_one_claim(self):
        def claim(_):
            return claim_morning_job(
                self.profile, self.schedule, self.now
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, range(2)))

        self.assertEqual(
            sum(result is not None for result in results),
            1,
        )

    def test_review_job_is_not_automatically_retried(self):
        job = claim_morning_job(
            self.profile, self.schedule, self.now
        )
        self.finish(job, "review")

        self.assertIsNone(
            claim_morning_job(
                self.profile,
                self.schedule,
                self.now + timedelta(minutes=5),
            )
        )


if __name__ == "__main__":
    unittest.main()