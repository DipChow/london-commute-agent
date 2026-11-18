"""Monitor commuters and optionally generate scheduled morning messages."""

import argparse
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from commute_agent import storage
from commute_agent.agent import run_agent
from commute_agent.agent_tools import get_service_status
from commute_agent.commute import check, profile_key
from commute_agent.jobs import (
    claim_morning_job,
    finish_morning_job,
)
from commute_agent.scheduler import preview_schedule


def now_for(profile):
    return datetime.now(ZoneInfo(profile["timezone"]))


def save_worker_state(profile, state, *, generate=False, **details):
    result = {
        "at": now_for(profile).isoformat(),
        "state": state,
        "automatic_messages": generate,
        **details,
    }
    storage.write("worker", result, commuter_id=profile["id"])
    return result


def process_commuter(profile, *, generate=False):
    commuter_id = profile["id"]

    if not profile.get("enabled", False):
        return save_worker_state(
            profile,
            "disabled",
            generate=generate,
        )

    schedule = preview_schedule(profile, now_for(profile))
    storage.write("schedule", schedule, commuter_id=commuter_id)

    details = {"check_from": schedule["check_at"]}

    if schedule["state"] == "waiting":
        return save_worker_state(
            profile,
            "waiting",
            generate=generate,
            **details,
        )

    job = None
    if generate and schedule["state"] == "due":
        job = claim_morning_job(
            profile,
            schedule,
            now_for(profile),
        )

    def finish(outcome):
        return finish_morning_job(
            commuter_id,
            schedule["travel_date"],
            job["claim_token"],
            outcome,
            now_for(profile),
        )

    # Service monitoring continues even after today's message is completed.
    try:
        service_result = check(profile, now_for(profile))
    except Exception as error:
        if job:
            departure = datetime.fromisoformat(
                schedule["first_departure"]
            )
            finish(
                "retry"
                if now_for(profile) < departure
                else "missed"
            )

        return save_worker_state(
            profile,
            "service_check_failed",
            generate=generate,
            error=type(error).__name__,
            **details,
        )

    if not job:
        return save_worker_state(
            profile,
            service_result["state"],
            generate=generate,
            **details,
        )

    # These checks happen before starting AI generation.
    try:
        current_profile = storage.load_profile(commuter_id)

        if (
            not current_profile.get("enabled", False)
            or profile_key(current_profile) != schedule["profile_key"]
        ):
            raise ValueError("Settings changed or automatic messages disabled.")

        departure = datetime.fromisoformat(
            schedule["first_departure"]
        )
        if now_for(profile) >= departure:
            finish("missed")
            return save_worker_state(
                profile,
                "message_window_missed",
                generate=generate,
                **details,
            )

        if get_service_status(commuter_id)["status"] != "ok":
            raise ValueError("Fresh, complete service evidence is required.")

    except Exception as error:
        finish("retry")
        return save_worker_state(
            profile,
            "message_preflight_failed",
            generate=generate,
            error=type(error).__name__,
            **details,
        )

    save_worker_state(
        profile,
        "generating_message",
        generate=generate,
        **details,
    )

    # Once we enter the agent, an error may follow a paid request or
    # a saved message. Do not automatically repeat an uncertain attempt.
    try:
        run_agent(
            commuter_id,
            mode="scheduled",
            expected_travel_date=schedule["travel_date"],
        )
    except Exception as error:
        finish("review")
        return save_worker_state(
            profile,
            "message_needs_review",
            generate=generate,
            error=type(error).__name__,
            **details,
        )

    finish("completed")
    return save_worker_state(
        profile,
        "message_saved",
        generate=generate,
        **details,
    )


def tick(*, generate=False):
    started = datetime.now(ZoneInfo("Europe/London"))
    storage.write(
        "worker_process",
        {
            "at": started.isoformat(),
            "state": "running",
            "automatic_messages": generate,
        },
    )

    for profile in storage.load_profiles():
        try:
            result = process_commuter(profile, generate=generate)
        except Exception as error:
            result = save_worker_state(
                profile,
                "error",
                generate=generate,
                error=type(error).__name__,
            )

        print(
            f"{result['at']} · {profile['name']} · {result['state']}",
            flush=True,
        )

    storage.write(
        "worker_process",
        {
            "at": datetime.now(ZoneInfo("Europe/London")).isoformat(),
            "state": "waiting_for_next_tick",
            "automatic_messages": generate,
        },
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Allow scheduled OpenAI message generation.",
    )
    args = parser.parse_args()

    print(
        "Worker started · automatic AI generation "
        + ("ON" if args.generate else "OFF"),
        flush=True,
    )

    while True:
        try:
            tick(generate=args.generate)
        except Exception as error:
            # Exception strings can contain request URLs and API keys.
            print(
                f"Worker tick failed: {type(error).__name__}",
                flush=True,
            )

        if args.once:
            return

        time.sleep(120)


if __name__ == "__main__":
    main()