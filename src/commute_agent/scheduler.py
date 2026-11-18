"""Calculate and preview schedules without generating AI messages."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from commute_agent import storage
from commute_agent.commute import (
    get_plan,
    local_time,
    profile_key,
    travel_date,
)


def schedule_from_plan(profile, now, plan):
    """Calculate one schedule from matching journey evidence."""
    zone = ZoneInfo(profile["timezone"])
    current = now.astimezone(zone)
    day = travel_date(profile, current)

    if (
        plan.get("key") != profile_key(profile)
        or plan.get("date") != str(day)
    ):
        raise ValueError("Journey plan does not match the next commute.")

    departures = [
        local_time(journey["startDateTime"], zone)
        for journey in plan.get("journeys", [])
    ]

    if not departures:
        raise ValueError("No journeys available for the next commute.")

    first_departure = min(departures)
    check_at = first_departure - timedelta(
        minutes=profile["advance_warning_minutes"]
    )

    if current < check_at:
        state = "waiting"
    elif current < first_departure:
        state = "due"
    else:
        state = "departure_passed"

    return {
        "commuter_id": profile["id"],
        "commuter_name": profile["name"],
        "profile_key": profile_key(profile),
        "travel_date": str(day),
        "check_at": check_at.isoformat(),
        "first_departure": first_departure.isoformat(),
        "state": state,
        # Missing enabled settings default to off.
        "enabled": profile.get("enabled", False),
    }


def preview_schedule(profile, now):
    """Use a matching baseline or fetch the next day's journey plan."""
    commuter_id = profile["id"]
    settings_key = profile_key(profile)
    current = now.astimezone(ZoneInfo(profile["timezone"]))
    day = str(travel_date(profile, current))

    base = storage.read("baseline", {}, commuter_id=commuter_id)

    if base.get("key") != settings_key:
        raise ValueError("Save a baseline for the current settings first.")

    daily = storage.read("daily_plan", {}, commuter_id=commuter_id)

    def matches(plan):
        return (
            plan.get("key") == settings_key
            and plan.get("date") == day
            and bool(plan.get("journeys"))
        )

    if matches(daily):
        plan = daily
    elif matches(base):
        plan = base
    else:
        plan = get_plan(profile, travel_date(profile, current))

        # Do not save results against settings changed during the request.
        latest = storage.load_profile(commuter_id)
        if profile_key(latest) != settings_key:
            raise ValueError("Settings changed. Run the preview again.")

        storage.write("daily_plan", plan, commuter_id=commuter_id)

    return schedule_from_plan(profile, current, plan)


def main():
    print("SCHEDULE PREVIEW — automatic AI generation is off\n")

    for profile in storage.load_profiles():
        print(f"{profile['name']} ({profile['id']})")

        try:
            now = datetime.now(ZoneInfo(profile["timezone"]))
            schedule = preview_schedule(profile, now)
            check_at = datetime.fromisoformat(schedule["check_at"])
            departure = datetime.fromisoformat(
                schedule["first_departure"]
            )

            print(f"  Travel date: {schedule['travel_date']}")
            print(f"  Check at: {check_at:%H:%M %Z}")
            print(f"  Earliest leave-home time: {departure:%H:%M %Z}")
            print(f"  Timing state: {schedule['state']}")
            print(
                "  Profile enabled: "
                + ("yes" if schedule["enabled"] else "no")
            )

        except ValueError as error:
            print(f"  Not ready: {error}")

        except Exception as error:
            # Avoid printing request URLs that may contain API keys.
            print(f"  Preview failed: {type(error).__name__}")

        print()


if __name__ == "__main__":
    main()