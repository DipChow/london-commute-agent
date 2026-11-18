"""Persistent ownership and completion records for morning messages."""

import json
from datetime import datetime, timedelta
from uuid import uuid4

from commute_agent import storage
from commute_agent.commute import profile_key


MAX_ATTEMPTS = 3
RETRY_MINUTES = 2


def job_key(travel_date):
    # One morning job per commuter per travel date.
    # Settings changes do not create another job for the same day.
    datetime.strptime(travel_date, "%Y-%m-%d")
    return f"morning_job:{travel_date}"


def read_morning_job(commuter_id, travel_date):
    return storage.read(
        job_key(travel_date),
        {},
        commuter_id=commuter_id,
    )


def claim_morning_job(profile, schedule, now):
    """Atomically claim a due job. Return None if it must not run."""
    if not profile.get("enabled", False):
        return None

    if (
        schedule["commuter_id"] != profile["id"]
        or schedule["profile_key"] != profile_key(profile)
    ):
        raise ValueError("Schedule does not match the commuter's settings.")

    check_at = datetime.fromisoformat(schedule["check_at"])
    departure = datetime.fromisoformat(schedule["first_departure"])

    # Recheck the actual clock rather than trusting a saved state label.
    if not check_at <= now < departure:
        return None

    stored_key = storage.record_key(
        job_key(schedule["travel_date"]),
        profile["id"],
    )

    # storage.connect uses BEGIN IMMEDIATE, so two workers cannot
    # successfully claim the same job at the same time.
    with storage.connect() as connection:
        row = connection.execute(
            "SELECT body FROM records WHERE key = ?",
            (stored_key,),
        ).fetchone()
        existing = json.loads(row[0]) if row else {}

        if existing:
            # Completed, running, failed and review jobs stay blocked.
            if existing["state"] != "retry":
                return None

            if existing["attempts"] >= MAX_ATTEMPTS:
                return None

            retry_at = datetime.fromisoformat(existing["retry_at"])
            if now < retry_at:
                return None

        job = {
            "commuter_id": profile["id"],
            "travel_date": schedule["travel_date"],
            "profile_key": profile_key(profile),
            "state": "running",
            "attempts": existing.get("attempts", 0) + 1,
            "claim_token": uuid4().hex,
            "started_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        connection.execute(
            "INSERT OR REPLACE INTO records (key, body) VALUES (?, ?)",
            (stored_key, json.dumps(job)),
        )

    return job


def finish_morning_job(
    commuter_id,
    travel_date,
    claim_token,
    outcome,
    now,
):
    """Finish only the job owned by this claim.

    outcome:
      completed — message was generated and saved
      retry — failure occurred before starting AI generation
      review — AI may have run; do not automatically repeat it
    """
    if outcome not in {"completed", "retry", "review", "missed"}:
        raise ValueError("Unknown morning-job outcome.")

    stored_key = storage.record_key(
        job_key(travel_date),
        commuter_id,
    )

    with storage.connect() as connection:
        row = connection.execute(
            "SELECT body FROM records WHERE key = ?",
            (stored_key,),
        ).fetchone()
        job = json.loads(row[0]) if row else {}

        if (
            job.get("state") != "running"
            or job.get("claim_token") != claim_token
        ):
            raise ValueError("This process does not own the running job.")

        job["state"] = outcome
        job["updated_at"] = now.isoformat()

        if outcome == "retry":
            if job["attempts"] >= MAX_ATTEMPTS:
                job["state"] = "failed"
            else:
                job["retry_at"] = (
                    now + timedelta(minutes=RETRY_MINUTES)
                ).isoformat()

        connection.execute(
            "UPDATE records SET body = ? WHERE key = ?",
            (json.dumps(job), stored_key),
        )

    return job